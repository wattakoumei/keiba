#!/usr/bin/env python3
"""出走表・脚質・血統・当日レースカードを取得する（JRA優先・競馬ラボはフォールバック）。

このハーネスの核データ（馬名・性齢・斤量・騎手・脚質・枠・血統・当日参考R）取得用。
WebFetch/WebSearch は WAF/JS/ログインで弾かれ小型モデルが捏造する箇所を、決定論的スクレイプで置換。
仕様の詳細は .claude/skills/analyze-race/references/scraping.md を参照。

取得優先順位（ユーザー指定）: ① JRA公式 → ② 競馬ラボ。netkeiba は完全CSR＋ログインで stdlib 不可＝web調査専用。
- **JRA**: 出馬表1ページにスパイン(馬名/性齢/斤量/騎手/血統 父母父/枠)＋近走コーナー通過順(=精密脚質)が全部入る。
  Shift_JIS・POST連鎖(安定index pw01dli00→開催選択→レース選択→出馬表)でトークンを収穫。**今週開催のみ**。
  ★市場ゼロ: このビューは単勝オッズ・人気を含む → parse_jra_full 冒頭で物理除去し以降一切触れない。
- **競馬ラボ**: 任意日付OK・SSR。JRAが今週外(過去/未来週)や障害のときのフォールバック。脚質は粗い傾向バー。
- 設計: **標準ライブラリのみ**（urllib+正規表現、pip不要＝Python3.14で壊れない）。WAFは実ブラウザUAで正規通過。

使い方:
  python3 tools/fetch_racecard.py race <race_id> [--json] [--self-check]   # JRA優先→競馬ラボ
  python3 tools/fetch_racecard.py day  <YYYYMMDD> <場2桁> [--json]          # 当日全Rカード(§0-1用)
  python3 tools/fetch_racecard.py jra  <YYYYMMDD> <場2桁> [<R>] [--json]    # JRA直接(R省略でトークン一覧)
  python3 tools/fetch_racecard.py <race_id>        # 12桁数字なら race にディスパッチ（後方互換）

race_id = YYYYMMDD + 場2桁 + R2桁（東京=05。例 安田11R=202606070511、8R=202606070508）。
出力の source フィールドで JRA / 競馬ラボ のどちらが使われたか分かる。

エラー時は {"error","stage","url"} を stderr に出して非ゼロ終了する
（SKILL 側はこれを検知して WebFetch/貼り付けにフォールバックする契約）。
"""
import sys
import re
import json
import time
import html
import urllib.request
import urllib.error
import urllib.parse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
RANK = {'◎': 4, '○': 3, '▲': 2, '△': 1, '': 0}   # dbrunstyle の傾向記号の強さ
LEG = ['逃', '先', '差', '追']                       # dbrunstyle の li は左から[逃,先,差,追]

# --- 競馬ラボ DOM の依存箇所を一箇所に集約（レイアウト変化はここだけ直す） ---
PATTERNS = {
    # race ページ: 各馬ブロック = data-hsnm(馬名) ... <ul class="dbrunstyle2 legs">(脚質バー)
    "horse_block": re.compile(
        r'data-hsnm="([^"]+)">(.*?)<ul class="dbrunstyle2 legs">(.*?)</ul>', re.S),
    "leg_li": re.compile(r'<li>([^<]*)</li>'),
    # 血統: <dd class="chichi|haha ...">...<span ...>...</span> 父名(or 母名)
    "blood": lambda cls: re.compile(
        r'class="' + cls + r'[^"]*"[^>]*>\s*<span[^>]*>[^<]*</span>\s*([^<\s　]+)'),
    # user_mark セレクト: name=馬名 data-umano data-wakno（枠順確定後に値が入る）
    "mark_select": re.compile(
        r'<select class="user_mark" name="([^"]+)"[^>]*data-umano="([^"]*)"[^>]*data-wakno="([^"]*)"'),
    "title": re.compile(r'<title>([^<]*)</title>'),
    # day ページ: raceNum セル = rCorner(turf|dirt) + /db/race/<id>/ + R番号 + 直後の発走時刻
    "day_racenum": re.compile(
        r'rCorner[^"]*\b(turf|dirt)\b[^>]*>\s*<a href="/db/race/(\d+)/">(\d+)R</a>'
        r'.*?<span class="std11">(\d{1,2}:\d{2})</span>', re.S),
    # day ページ: レース名（itemprop="url"）と 距離・頭数（芝1600m&nbsp;17頭）
    "day_name": re.compile(r'href="/db/race/(\d+)/" itemprop="url">([^<]+)</a>'),
    "day_dist": re.compile(r'(芝|ダ)(\d{3,4})m(?:&nbsp;|\s)*(\d+)頭'),
    # --- JRA出馬表（Shift_JIS・POST連鎖。スパイン＋通過順=精密脚質を1ページで取る） ---
    # ★市場ゼロ: このビューは単勝オッズ・人気を含む → jra_strip_odds で物理除去し、以降一切触れない
    "jra_strip_odds": re.compile(r'<div class="odds">.*?</div>\s*</div>', re.S),    # オッズ塊を丸ごと削除
    "jra_horse": re.compile(r'<td class="waku(.*?)(?=<td class="waku|</tbody>)', re.S),  # 枠セル基点=1馬ぶん
    "jra_waku": re.compile(r'alt="枠(\d)'),                                          # 枠（画像alt。未確定なら無し）
    "jra_num": re.compile(r'<td class="num">\s*(?:<[^>]+>)*\s*(\d+)'),              # 馬番
    "jra_name": re.compile(r'<div class="name">(?:<span[^>]*>.*?</span>)?\s*<a[^>]*accessU[^>]*>([^<]+)</a>', re.S),  # 馬名（マル外アイコン許容）
    "jra_age": re.compile(r'<p class="age">([^<]+)</p>'),                            # 性齢/毛色
    "jra_weight": re.compile(r'<p class="weight">\s*([\d.]+)<span>kg'),              # 負担重量
    "jra_jockey": re.compile(r'<p class="jockey"><a[^>]*accessK[^>]*>([^<]+)</a>'),  # 騎手（当該レース）
    "jra_sire": re.compile(r'class="sire">.*?父：</span>([^<]+)<', re.S),            # 父
    "jra_damsire": re.compile(r'母の父：([^)）]+)'),                                  # 母父
    "jra_past": re.compile(r'<td class="past[^"]*"[^>]*>(.*?)</td>', re.S),          # 近走1走ぶん
    "jra_corner": re.compile(r'通過順位">(\d+)</li>'),                                # コーナー通過順位
    "jra_field": re.compile(r'class="max">(\d+)<span>頭'),                           # その近走の頭数
    "jra_agari": re.compile(r'3F\s*([\d.]+)'),                                        # 上がり3F
}
TIMEOUT = 30
PLACE = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
         "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
# JRA出馬表ナビ: 安定インデックス → 開催選択(drl) → レース選択(dde) を POST で辿る
JRA_BASE = "https://www.jra.go.jp/JRADB/accessD.html"
JRA_INDEX = "pw01dli00/F3"   # 「出馬表」インデックス（今週開催・安定トークン）


def fetch(url):
    """実ブラウザ UA で取得。一過性エラーは1回だけリトライ。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(1.5)


def _blood(block, cls):
    m = PATTERNS["blood"](cls).search(block)
    return html.unescape(m.group(1)).strip() if m else None


def parse_race(h):
    """race ページHTML → 馬名・脚質傾向・血統・(確定後)枠/馬番。"""
    title = PATTERNS["title"].search(h)
    draw_fixed = 'data-wakno=""' not in h     # 未確定なら全 data-wakno が空
    # 馬名 → (馬番, 枠番)。確定後のみ値が入る。
    draws = {}
    for name, umano, wakno in PATTERNS["mark_select"].findall(h):
        draws[html.unescape(name).strip()] = (umano or None, wakno or None)
    seen, horses = set(), []
    for name, block, ul in PATTERNS["horse_block"].findall(h):
        name = html.unescape(name).strip()
        if name in seen:                       # 競馬ラボは横/縦テーブルで重複表示する
            continue
        seen.add(name)
        syms = [s.strip() for s in PATTERNS["leg_li"].findall(ul)][:4]
        syms += [''] * (4 - len(syms))
        vals = [RANK.get(s, 0) for s in syms]
        mx = max(vals)
        styles = [LEG[i] for i, v in enumerate(vals) if v == mx and v > 0]
        umano, wakno = draws.get(name, (None, None))
        horses.append({
            "no": int(umano) if umano and umano.isdigit() else None,
            "waku": int(wakno) if wakno and wakno.isdigit() else None,
            "name": name,
            "style": "/".join(styles),
            "style_bars": dict(zip(LEG, syms)),
            "sire": _blood(block, "chichi"),
            "dam": _blood(block, "haha"),
        })
    return {
        "title": html.unescape(title.group(1)) if title else None,
        "draw_fixed": draw_fixed,
        "n": len(horses),
        "horses": horses,
    }


def parse_day(h, place):
    """day 一覧HTML → その競馬場の全レース [{r,post_time,surface,distance,headcount,race_name}]。"""
    names, dists = {}, {}
    for rid, nm in PATTERNS["day_name"].findall(h):
        names.setdefault(rid, html.unescape(nm).strip())
    # 距離・頭数は raceNum セル直後に来るので、レース名の出現順に対応づける
    name_ids = [rid for rid, _ in PATTERNS["day_name"].findall(h)]
    dist_hits = PATTERNS["day_dist"].findall(h)
    for rid, (surf, dist, head) in zip(name_ids, dist_hits):
        dists[rid] = (surf, int(dist), int(head))
    races = []
    for surface_cls, rid, rno, post in PATTERNS["day_racenum"].findall(h):
        if rid[8:10] != place:
            continue
        surf, dist, head = dists.get(rid, (None, None, None))
        races.append({
            "race_id": rid,
            "r": int(rno),
            "post_time": post,
            "surface": "芝" if surface_cls == "turf" else "ダ",
            "distance": dist,
            "headcount": head,
            "turn": None,                      # 内/外回りは day 一覧に無い（race条件側で補う）
            "race_name": names.get(rid),
        })
    races.sort(key=lambda x: x["r"])
    return races


# ---------------- JRA 通過順（--deep / jra サブコマンド） ----------------

def jra_post(cname):
    """JRA accessD に cname を POST して Shift_JIS ページを取る。"""
    data = urllib.parse.urlencode({"cname": cname}).encode()
    req = urllib.request.Request(JRA_BASE, data=data,
                                 headers={"User-Agent": UA, "Accept-Language": "ja"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read().decode("shift_jis", "ignore")
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(1.5)


def jra_race_tokens(date, place):
    """date(YYYYMMDD)+place(2桁) の全レース出馬表トークン {R番号: dde_cname} を収穫。"""
    idx = jra_post(JRA_INDEX)                                   # インデックス → 開催選択
    drl = re.search(rf'pw01drl00{place}\d{{8}}{date}/[0-9A-F]{{2}}', idx)
    if not drl:
        raise ValueError(f"JRA: {date} 場{place} の開催が今週インデックスに無い（過去/未来週は非対応）")
    rl = jra_post(drl.group(0))                                 # 開催選択 → レース選択（全Rのddeトークン）
    toks = {}
    for m in re.finditer(rf'pw01dde\d{{4}}\d{{8}}(\d{{2}}){date}/[0-9A-F]{{2}}', rl):
        toks[m.group(1)] = m.group(0)
    if not toks:
        raise ValueError(f"JRA: {date} 場{place} のレース一覧から出馬表トークンを収穫できず")
    return toks


def _style_from_corner(first_corner, field):
    r = first_corner / max(field, 1)
    return '逃' if first_corner <= 1 else '先' if r <= 0.30 else '差' if r <= 0.65 else '追'


def parse_jra_full(h):
    """JRA出馬表HTML → 全馬のスパイン(馬名/性齢/斤量/騎手/血統/枠/馬番)＋通過順由来の脚質・テン速。
    ★市場ゼロ: 先頭でオッズ塊を物理除去し、以降オッズ/人気には一切触れない（純粋情報のみ）。"""
    h = PATTERNS["jra_strip_odds"].sub("", h)
    from collections import Counter
    horses = []
    for c in PATTERNS["jra_horse"].findall(h):
        nm = PATTERNS["jra_name"].search(c)
        if not nm:
            continue
        recent, legs, ratios, agari = [], [], [], []
        for p in PATTERNS["jra_past"].findall(c)[:5]:
            corners = [int(x) for x in PATTERNS["jra_corner"].findall(p)]
            if not corners:
                continue
            fm = PATTERNS["jra_field"].search(p)
            field = int(fm.group(1)) if fm else 18
            fc = corners[0]
            legs.append(_style_from_corner(fc, field))
            ratios.append(fc / max(field, 1))
            am = PATTERNS["jra_agari"].search(p)
            if am:
                agari.append(float(am.group(1)))
            recent.append({"first_corner": fc, "field": field,
                           "agari": float(am.group(1)) if am else None})
        style = Counter(legs).most_common(1)[0][0] if legs else None
        ten = None
        if ratios:
            avg = sum(ratios) / len(ratios)
            ten = "速" if avg <= 0.20 else "中" if avg <= 0.50 else "遅"

        def g(key):
            m = PATTERNS[key].search(c)
            return html.unescape(m.group(1)).strip() if m else None
        waku, num = g("jra_waku"), g("jra_num")
        horses.append({
            "no": int(num) if num else None,
            "waku": int(waku) if waku else None,
            "name": html.unescape(nm.group(1)).strip(),
            "sex_age": g("jra_age"),
            "weight": g("jra_weight"),
            "jockey": g("jra_jockey"),
            "sire": g("jra_sire"),
            "damsire": g("jra_damsire"),
            "style": style,                 # 近走通過順から（粗バーより精密）
            "ten_speed": ten,
            "agari_best": min(agari) if agari else None,
            "recent": recent,
        })
    horses.sort(key=lambda x: x["no"] or 999)
    return horses


def jra_fetch_race(date, place, rno):
    """JRA出馬表を取得して全馬スパイン＋通過順を返す。失敗は例外。"""
    toks = jra_race_tokens(date, place)
    if rno not in toks:
        raise ValueError(f"JRA: {date} 場{place} に {int(rno)}R が無い")
    horses = parse_jra_full(jra_post(toks[rno]))
    if not horses:
        raise ValueError(f"JRA: {date} 場{place} {int(rno)}R の出馬表をパースできず")
    return horses


def self_check(data):
    """HTML ドリフト検知。失敗で AssertionError（呼び出し側が非ゼロ終了）。"""
    assert data["n"] > 0, "頭数が0（パース失敗の疑い）"
    for hh in data["horses"]:
        assert hh["name"], "空の馬名"
    if data.get("source") == "keibalab":
        for hh in data["horses"]:
            assert len(hh.get("style_bars", {})) == 4, f"脚質バーが4本でない: {hh['name']}"
    elif data.get("source") == "jra":           # 通過順がどの馬かに付いている（全馬未取得=構造変化の疑い）
        assert any(h.get("style") for h in data["horses"]), "JRA通過順が1頭も取れず（構造変化の疑い）"


def cmd_race(rid, as_json, do_check):
    """JRA優先で出馬表を取得。JRAが今週外/障害なら競馬ラボにフォールバック。"""
    date, place, rno = rid[:8], rid[8:10], rid[10:12]
    try:                                        # ① JRA（公式・完全・スパイン＋通過順を1ページ）
        horses = jra_fetch_race(date, place, rno)
        data = {"race_id": rid, "source": "jra", "n": len(horses),
                "draw_fixed": any(h["waku"] for h in horses), "horses": horses}
    except Exception as e:                       # ② 競馬ラボ（任意日付OK・過去/未来週やJRA障害時）
        url = f"https://www.keibalab.jp/db/race/{rid}/"
        data = parse_race(fetch(url))
        data["race_id"], data["url"], data["source"], data["jra_failed"] = rid, url, "keibalab", str(e)
        if data["n"] == 0:
            raise ValueError(f"出走馬0頭（JRA: {e} ／ 競馬ラボも race_id={rid} 不正/未掲載）")
    if do_check:
        self_check(data)
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    title = data.get("title") or f"{date} {PLACE.get(place, place)}{int(rno)}R"
    print(f"# {title}  [source={data['source']}]")
    if data.get("jra_failed"):
        print(f"  ※JRA不可→競馬ラボにフォールバック: {data['jra_failed']}")
    print(f"  race_id={rid}  頭数={data['n']}  枠順={'確定' if data['draw_fixed'] else '未確定'}")
    leaders = [h["name"] for h in data["horses"] if (h.get("style") or "") and ("逃" in h["style"] or "先" in h["style"])]
    print(f"  ハナ・先行候補: {', '.join(leaders) or '不明'}")
    for h in data["horses"]:
        head = f"{h['waku']}-{h['no']}" if h.get("no") else "?-?"
        if data["source"] == "jra":
            print(f"  {head:>5} {h['name']:<12} {h.get('sex_age') or '':<7}{h.get('weight') or '':>4}kg "
                  f"{h.get('jockey') or '':<8} → {h.get('style') or '?'}・テン{h.get('ten_speed') or '?'}"
                  f"  (父{h.get('sire') or '?'}/母父{h.get('damsire') or '?'})")
        else:
            b = h["style_bars"]
            print(f"  {head:>5} {h['name']:<12} 逃{b['逃'] or '·'}先{b['先'] or '·'}差{b['差'] or '·'}追{b['追'] or '·'}"
                  f"  → {h['style']:<6} (父{h.get('sire') or '?'}/母{h.get('dam') or '?'})")


def cmd_day(ymd, place, as_json):
    url = f"https://www.keibalab.jp/db/race/{ymd}/"
    races = parse_day(fetch(url), place)
    if not races:
        raise ValueError(f"{ymd} に場コード {place}({PLACE.get(place,'?')}) のレースが見つからない")
    if as_json:
        print(json.dumps({"date": ymd, "place": place, "place_name": PLACE.get(place),
                          "races": races}, ensure_ascii=False, indent=2))
        return
    print(f"# {ymd} {PLACE.get(place, place)} 全{len(races)}R")
    for r in races:
        print(f"  {r['r']:>2}R {r['post_time']}  {r['surface']}{r['distance']}m "
              f"{r['headcount']}頭  {r['race_name']}")


def cmd_jra(date, place, race_no, as_json):
    """JRA出馬表を直接取る（スパイン＋通過順）。R省略でトークン一覧。"""
    toks = jra_race_tokens(date, place)
    if not race_no:
        print(json.dumps({"date": date, "place": place, "tokens": toks}, ensure_ascii=False, indent=2)); return
    rno = race_no.zfill(2)
    horses = parse_jra_full(jra_post(toks[rno]))
    if as_json:
        print(json.dumps({"date": date, "place": place, "r": int(rno), "source": "jra",
                          "n": len(horses), "horses": horses}, ensure_ascii=False, indent=2)); return
    print(f"# {date} {PLACE.get(place, place)}{int(rno)}R JRA出馬表（{len(horses)}頭）")
    for h in horses:
        head = f"{h['waku']}-{h['no']}" if h["no"] else "?-?"
        corners = " ".join(f"{r['first_corner']}/{r['field']}" for r in h["recent"])
        print(f"  {head:>5} {h['name']:<12} {h.get('sex_age') or '':<7}{h.get('weight') or '':>4}kg "
              f"{h.get('jockey') or '':<8} → {h.get('style') or '?'}・テン{h.get('ten_speed') or '?'}  近走1角[{corners}]")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__); sys.exit(1)
    cmd = args[0]
    # 後方互換: 12桁数字を直接渡したら race 扱い
    if cmd.isdigit() and len(cmd) == 12:
        cmd, args = "race", ["race"] + args
    try:
        if cmd == "race":
            cmd_race(args[1], "--json" in flags, "--self-check" in flags)
        elif cmd == "day":
            cmd_day(args[1], args[2], "--json" in flags)
        elif cmd == "jra":
            cmd_jra(args[1], args[2], args[3] if len(args) > 3 else None, "--json" in flags)
        else:
            print(f"unknown command: {cmd}\n", __doc__, file=sys.stderr); sys.exit(2)
    except AssertionError as e:
        print(json.dumps({"error": str(e), "stage": "self-check"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        stage = "fetch" if isinstance(e, (urllib.error.URLError, TimeoutError)) else "parse"
        print(json.dumps({"error": str(e), "stage": stage}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
