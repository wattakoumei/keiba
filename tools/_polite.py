#!/usr/bin/env python3
"""web取得の礼儀ヘルパー（実装の正本）— robots.txt 尊重・ホスト別レート制限・簡易キャッシュ・UA一元管理。

法的リスク低減の実装を一箇所に集める（散文ポリシーは references/scraping.md「取得ポリシー」節）:
  1. robots.txt 尊重: ホストごとに1回取得してキャッシュし、Disallow のパスは RefusedByRobots で拒否
     （robots.txt が無い/取得不能なサイトは fail-open＝制限記述なしとみなす。404 は「制限なし」が標準解釈）。
  2. レート制限: ホスト別に最終リクエスト時刻を持ち、min_interval 秒（既定 1.5s）未満の連続アクセスは sleep。
     並列プロセスには効かない＝一括取得は必ず単一プロセスの逐次ループで行う（backfill 手順の規律）。
  3. 簡易キャッシュ: cache_ttl 指定時は data/cache/ に保存し TTL 内はネットに出ない（確定結果など不変ページ向け。
     パース失敗時は cache_evict() で無効化＝未確定ページを掴んだまま固まらない）。
  4. UA 一元管理: 一般的なブラウザ UA を定数で一箇所に（モバイル最適化/文字化け回避の互換目的。
     アクセスを隠す意図ではない＝負荷対策の本質は間隔・キャッシュ・対象ページの最小化）。

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
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

MIN_INTERVAL = 1.5   # 秒。人間の閲覧より遅い頻度を保つ下限（各ツールはこれ未満に縮めない）
TIMEOUT = 25
CACHE_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "cache"

_last_hit = {}   # host -> time.monotonic() of last request
_robots = {}     # host -> RobotFileParser | None（None=取得不能・fail-open）


class RefusedByRobots(Exception):
    """robots.txt が Disallow するパスへのアクセス要求（取得せず中止）。"""


def _robots_for(host, scheme="https"):
    if host in _robots:
        return _robots[host]
    rp = None
    try:
        req = urllib.request.Request(f"{scheme}://{host}/robots.txt",
                                     headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=10).read()
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(raw.decode("utf-8", "replace").splitlines())
        rp = parser
    except Exception:
        rp = None   # robots 無し/取得不能 = fail-open
    _robots[host] = rp
    return rp


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
    """robots 尊重＋ホスト別レート制限＋任意キャッシュの GET。bytes を返す。"""
    pu = urllib.parse.urlsplit(url)
    if cache_ttl:
        cp = _cache_path(url)
        if cp.exists() and (time.time() - cp.stat().st_mtime) < cache_ttl:
            return cp.read_bytes()
    rp = _robots_for(pu.netloc, pu.scheme or "https")
    if rp is not None and not rp.can_fetch(UA, url):
        raise RefusedByRobots(f"robots.txt disallows: {url}")
    _throttle(pu.netloc, max(min_interval, MIN_INTERVAL))
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "ja", **(headers or {})})
    data = urllib.request.urlopen(req, timeout=timeout).read()
    if cache_ttl:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_bytes(data)
    return data


def polite_post(url, data, min_interval=MIN_INTERVAL, timeout=TIMEOUT, headers=None):
    """POST（JRA トークン連鎖等）。robots は GET 資源向けなのでレート制限のみ適用。"""
    pu = urllib.parse.urlsplit(url)
    _throttle(pu.netloc, max(min_interval, MIN_INTERVAL))
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": UA, "Accept-Language": "ja", **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read()


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
    print("self-check OK (throttle / robots-refuse / cache roundtrip)")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        print(__doc__)
