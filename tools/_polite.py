#!/usr/bin/env python3
"""web取得の礼儀ヘルパー（実装の正本）— robots.txt 尊重・ホスト別レート制限・簡易キャッシュ・UA一元管理。

法的リスク低減の実装を一箇所に集める（散文ポリシーは references/scraping.md「取得ポリシー」節）:
  1. robots.txt 尊重: ホストごとに1回取得してキャッシュし、Disallow のパスは RefusedByRobots で拒否。
     取得結果の扱いは RFC 9309 準拠＝4xx（404等）は「制限なし」＝fail-open、
     **5xx/ネットワーク断は「全面 Disallow」＝fail-closed**（1回リトライしても取れなければ拒否。
     各 fetch_* は貼り付け経路へフォールバックする契約）。Crawl-delay / Request-rate も尊重（上限30s）。
  2. レート制限: ホスト別に最終リクエスト時刻を持ち、min_interval 秒（既定 1.5s）未満の連続アクセスは sleep。
     並列プロセスには効かない＝一括取得は必ず単一プロセスの逐次ループで行う（backfill 手順の規律）。
  3. 簡易キャッシュ: cache_ttl 指定時は data/cache/ に保存し TTL 内はネットに出ない（確定結果など不変ページ向け。
     パース失敗時は cache_evict() で無効化＝未確定ページを掴んだまま固まらない）。
  4. UA 一元管理: 一般的なブラウザ UA を定数で一箇所に（モバイル最適化/文字化け回避の互換目的。
     アクセスを隠す意図ではない＝負荷対策の本質は間隔・キャッシュ・対象ページの最小化）。
  5. リトライの正本: 一過性の失敗（接続断・タイムアウト・不完全応答・HTTP 429/5xx）は**ここで1回だけ**
     リトライする（Retry-After 尊重・上限30s）。呼び出し側は自前 retry ループを持たない＝二重リトライしない。
     429以外の 4xx は恒久エラー＝即 raise（リトライは負荷になるだけ）。

stdlib のみ。使い方:
  from _polite import polite_get, polite_post, cache_evict, RefusedByRobots, UA
  raw = polite_get(url)                        # robots + レート制限つき GET（bytes）
  raw = polite_get(url, cache_ttl=7*86400)     # 不変ページはキャッシュ再利用
  raw = polite_post(url, data)                 # POST（レート制限のみ。robots は GET 対象）

self-check: python3 tools/_polite.py --self-check（ネットワーク不要）
"""
import sys
import time
import hashlib
import pathlib
import http.client
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

MIN_INTERVAL = 1.5   # 秒。人間の閲覧より遅い頻度を保つ下限（各ツールはこれ未満に縮めない）
TIMEOUT = 25
RETRY_SLEEP = 1.5            # 一過性エラーのリトライ前待機（Retry-After が無いとき）
RETRY_STATUS = {429, 500, 502, 503, 504}   # リトライしてよい HTTP ステータス
RETRY_AFTER_CAP = 30.0       # Retry-After / Crawl-delay を尊重する上限秒（それ以上は諦めて人間に返す）
CACHE_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "cache"

_last_hit = {}   # host -> time.monotonic() of last request
_robots = {}     # host -> RobotFileParser | None(4xx=制限なし) | _UNREACHABLE(5xx/断=全面Disallow)

# robots.txt が 5xx/ネットワーク断で取得不能＝RFC 9309 §2.3.1.4「全面 Disallow とみなす」の目印
_UNREACHABLE = object()


class RefusedByRobots(Exception):
    """robots.txt が Disallow するパスへのアクセス要求（取得せず中止）。"""


def _robots_for(host, scheme="https"):
    if host in _robots:
        return _robots[host]
    rp = _UNREACHABLE
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(f"{scheme}://{host}/robots.txt",
                                         headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=10).read()
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(raw.decode("utf-8", "replace").splitlines())
            rp = parser
            break
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                rp = None            # 404等の4xx = robots 無し＝「制限なし」が標準解釈（fail-open）
                break
            if attempt == 1:         # 5xx = 一過性の可能性 → 1回だけリトライ
                time.sleep(RETRY_SLEEP)
        except Exception:
            if attempt == 1:         # ネットワーク断も同様に1回リトライ
                time.sleep(RETRY_SLEEP)
    _robots[host] = rp               # 2回とも失敗 = _UNREACHABLE（polite_get が拒否する）
    return rp


def _crawl_delay(rp):
    """robots.txt の Crawl-delay / Request-rate（秒/リクエスト）。未指定は 0。上限 RETRY_AFTER_CAP。"""
    if rp is None or rp is _UNREACHABLE:
        return 0.0
    try:
        d = float(rp.crawl_delay(UA) or 0)
        rr = rp.request_rate(UA)
        if rr and rr.requests:
            d = max(d, rr.seconds / rr.requests)
        return min(d, RETRY_AFTER_CAP)
    except Exception:
        return 0.0


def _open_with_retry(req, timeout, retry_sleep=RETRY_SLEEP):
    """urlopen + read() を一過性の失敗に限り1回だけリトライ（リトライ方針の正本）。

    リトライ対象: 接続断/タイムアウト/不完全応答（ConnectionReset・RemoteDisconnected・
    IncompleteRead・BadStatusLine 等 = OSError/http.client.HTTPException）と HTTP 429/5xx
    （Retry-After ヘッダを尊重・上限 RETRY_AFTER_CAP）。429以外の 4xx は恒久エラー＝即 raise。"""
    for attempt in (1, 2):
        try:
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if attempt == 2 or e.code not in RETRY_STATUS:
                raise
            try:
                wait = min(float(e.headers.get("Retry-After", "")), RETRY_AFTER_CAP)
            except (ValueError, TypeError, AttributeError):
                wait = retry_sleep
            time.sleep(max(wait, retry_sleep))
        except (OSError, http.client.HTTPException):
            if attempt == 2:
                raise
            time.sleep(retry_sleep)


def _throttle(host, min_interval):
    last = _last_hit.get(host)
    if last is not None:
        wait = min_interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_hit[host] = time.monotonic()


def _cache_path(url):
    return CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".cache")


def cache_evict(url):
    """キャッシュ無効化（パース失敗＝未確定/変則ページを掴んだときに呼ぶ）。"""
    p = _cache_path(url)
    if p.exists():
        p.unlink()


def polite_get(url, min_interval=MIN_INTERVAL, timeout=TIMEOUT, cache_ttl=None, headers=None):
    """robots 尊重＋ホスト別レート制限＋一過性リトライ＋任意キャッシュの GET。bytes を返す。"""
    pu = urllib.parse.urlsplit(url)
    if cache_ttl:
        cp = _cache_path(url)
        if cp.exists() and (time.time() - cp.stat().st_mtime) < cache_ttl:
            return cp.read_bytes()
    rp = _robots_for(pu.netloc, pu.scheme or "https")
    if rp is _UNREACHABLE:
        raise RefusedByRobots(
            f"robots.txt が取得不能(5xx/接続断): {pu.netloc} → RFC 9309 に従い全面 Disallow 扱い"
            f"（時間をおいて再実行 or 貼り付け経路へ）: {url}")
    if rp is not None and not rp.can_fetch(UA, url):
        raise RefusedByRobots(f"robots.txt disallows: {url}")
    _throttle(pu.netloc, max(min_interval, MIN_INTERVAL, _crawl_delay(rp)))
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "ja", **(headers or {})})
    data = _open_with_retry(req, timeout)
    if cache_ttl:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_bytes(data)
    return data


def polite_post(url, data, min_interval=MIN_INTERVAL, timeout=TIMEOUT, headers=None):
    """POST（JRA トークン連鎖等）。robots は GET 資源向けなのでレート制限＋リトライのみ適用。"""
    pu = urllib.parse.urlsplit(url)
    _throttle(pu.netloc, max(min_interval, MIN_INTERVAL))
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": UA, "Accept-Language": "ja", **(headers or {})})
    return _open_with_retry(req, timeout)


def self_check():
    """ネットワーク非依存の検査: レート制限の実測・robots 拒否・キャッシュ往復。"""
    import tempfile
    failures = []

    # 1) throttle: 同一ホスト2連続で min_interval 以上空く
    _last_hit.clear()
    t0 = time.monotonic()
    _throttle("check.test", 0.3)
    _throttle("check.test", 0.3)
    elapsed = time.monotonic() - t0
    if elapsed < 0.3:
        failures.append(f"throttle: 2連続の間隔 {elapsed:.3f}s < 0.3s")
    # 別ホストは待たない
    t0 = time.monotonic()
    _throttle("other.test", 5.0)
    if time.monotonic() - t0 > 0.5:
        failures.append("throttle: 初回アクセスなのに待機した")

    # 2) robots: Disallow パスを拒否（fixture を注入・ネット不要）
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(["User-agent: *", "Disallow: /private/"])
    _robots["robots.test"] = parser
    try:
        polite_get("https://robots.test/private/x")
        failures.append("robots: Disallow パスが拒否されなかった")
    except RefusedByRobots:
        pass
    except Exception as e:
        failures.append(f"robots: RefusedByRobots 以外の例外 {type(e).__name__}")
    if not parser.can_fetch(UA, "https://robots.test/db/race/1/"):
        failures.append("robots: Allow パスが誤って拒否された")
    # robots 取得不能（5xx/断）= 全面 Disallow 扱い（fixture を注入・ネット不要）
    _robots["down.test"] = _UNREACHABLE
    try:
        polite_get("https://down.test/x")
        failures.append("robots: 取得不能ホストが拒否されなかった（RFC 9309 違反）")
    except RefusedByRobots:
        pass

    # 2b) crawl-delay: robots.txt の Crawl-delay を実効間隔に反映（上限 RETRY_AFTER_CAP）
    cd = urllib.robotparser.RobotFileParser()
    cd.parse(["User-agent: *", "Crawl-delay: 7"])
    if _crawl_delay(cd) != 7.0:
        failures.append(f"crawl-delay: 7 を読めていない（{_crawl_delay(cd)}）")
    cd2 = urllib.robotparser.RobotFileParser()
    cd2.parse(["User-agent: *", "Crawl-delay: 999"])
    if _crawl_delay(cd2) != RETRY_AFTER_CAP:
        failures.append(f"crawl-delay: 上限 {RETRY_AFTER_CAP} でキャップされていない（{_crawl_delay(cd2)}）")
    if _crawl_delay(None) != 0.0 or _crawl_delay(_UNREACHABLE) != 0.0:
        failures.append("crawl-delay: 未指定/取得不能で 0 になっていない")

    # 2c) retry: 一過性の接続断は1回リトライ・恒久4xxは即 raise（urlopen をスタブ差し替え）
    real_urlopen = urllib.request.urlopen
    try:
        calls = {"n": 0}

        class _OK:
            def read(self):
                return b"ok"

        def flaky(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionResetError("simulated disconnect")
            return _OK()
        urllib.request.urlopen = flaky
        req = urllib.request.Request("https://retry.test/x")
        if _open_with_retry(req, 5, retry_sleep=0.01) != b"ok":
            failures.append("retry: 接続断1回後の成功を返せていない")
        if calls["n"] != 2:
            failures.append(f"retry: リトライ回数が想定外（{calls['n']}回）")
        calls["n"] = 0

        def notfound(req, timeout=None):
            calls["n"] += 1
            raise urllib.error.HTTPError("https://retry.test/x", 404, "NF", {}, None)
        urllib.request.urlopen = notfound
        try:
            _open_with_retry(req, 5, retry_sleep=0.01)
            failures.append("retry: 404 が例外にならなかった")
        except urllib.error.HTTPError:
            if calls["n"] != 1:
                failures.append(f"retry: 恒久4xxをリトライした（{calls['n']}回）")
    finally:
        urllib.request.urlopen = real_urlopen

    # 3) cache: 事前に書いたキャッシュが TTL 内でヒット（ネットに出ない）
    global CACHE_DIR
    orig = CACHE_DIR
    with tempfile.TemporaryDirectory() as td:
        CACHE_DIR = pathlib.Path(td)
        url = "https://cache.test/page"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_bytes(b"cached-bytes")
        got = polite_get(url, cache_ttl=3600)
        if got != b"cached-bytes":
            failures.append("cache: TTL 内キャッシュがヒットしなかった")
        cache_evict(url)
        if _cache_path(url).exists():
            failures.append("cache_evict: 削除されなかった")
    CACHE_DIR = orig

    if failures:
        print("SELF-CHECK FAIL:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)
    print("self-check OK (throttle / robots-refuse / robots-unreachable / crawl-delay / retry / cache roundtrip)")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        print(__doc__)
