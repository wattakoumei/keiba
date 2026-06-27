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
  python3 tools/fetch_racecard.py race <race_id> [--class=<クラス>] [--json] [--self-check]  # JRA優先→競馬ラボ
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
import unicodedata
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
    # day ページ: 1レース=1<tr>行を“行単位”でまとめて取る（位置zipしない＝障害戦が混じってもズレない）。
    # 行内の並び: rCorner(種別) → /db/race/<id>/ + R番号 → 発走時刻span → レース名(itemprop) → 距離span(芝|ダ|障 + m + 頭)
    # ★旧実装はレース名リストと距離リストを別取り→位置zipしており、障害戦の「障Nm」を距離正規表現(芝|ダのみ)が
    #   拾えず1件欠けると、以降の全レースが“次のレースの距離・頭数”を受け取る off-by-one を起こした。
    "day_row": re.compile(
        r'rCorner[^"]*\b(?:turf|dirt|failure)\b[^>]*>\s*'
        r'<a href="/db/race/(\d+)/">(\d+)R</a></div>\s*'
        r'<span class="std11[^"]*">(\d{1,2}:\d{2})</span>'   # 発走時刻span（bgRedL等の追加クラス許容）
        r'.*?itemprop="url">([^<]+)</a>'
        r'.*?<span class="std11[^"]*">(芝|ダ|障)(\d{3,4})m(?:&nbsp;|\s)*(\d+)頭</span>', re.S),
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
    "jra_trainer": re.compile(r'<p class="trainer">(?:<span[^>]*>[^<]*</span>)?\s*<a[^>]*>([^<]+)</a>'),  # 調教師（先頭span=美浦/栗東は捨て名前のみ。VERIFY: 次のJRA取得で要確認）
    "jra_sire": re.compile(r'class="sire">.*?父：</span>([^<]+)<', re.S),            # 父
    "jra_damsire": re.compile(r'母の父：([^)）]+)'),                                  # 母父
    "jra_past": re.compile(r'<td class="past[^"]*"[^>]*>(.*?)</td>', re.S),          # 近走1走ぶん
    "jra_corner": re.compile(r'通過順位">(\d+)</li>'),                                # コーナー通過順位
    "jra_field": re.compile(r'class="max">(\d+)<span>頭'),                           # その近走の頭数
    "jra_agari": re.compile(r'3F\s*([\d.]+)'),                                        # 上がり3F
    # 近走のレース特定（h2h 直接対戦用）。★市場ゼロ: 同ブロック内の「番人気」は抽出しない
    "jra_past_date": re.compile(r'<div class="date">(\d+)年(\d+)月(\d+)日</div>'),    # 近走の施行日
    "jra_past_rc": re.compile(r'<div class="rc">([^<]+)</div>'),                      # 近走の競馬場
    "jra_past_race": re.compile(r'<div class="name"><a[^>]*>([^<]+)</a>'),            # 近走のレース名
    "jra_past_pos": re.compile(r'<div class="place">(\d+)<span>着'),                  # 近走の着順
    "jra_past_jockey": re.compile(r'<div class="jockey">([^<]+)</div>'),             # 近走の騎手（前走騎手＝観点K乗替判定の seed。同セル内・追加fetch不要）
    "jra_past_dist": re.compile(r'<span class="dist">(ダ|芝|障)?([\d,]+)(ダ|芝)?</span>'),  # 近走の距離（距離替わり判定の seed。同セル内）
    "jra_past_time": re.compile(r'<p class="time">([\d:.]+)</p>'),                   # 近走の走破時計（観点A時計の seed。同セル内）
    "jra_past_bw": re.compile(r'<p class="h_weight">(\d+)<span>kg'),                 # 近走の馬体重（観点G馬体トレンドの seed。同セル内）
    # JRA出馬表のレース条件: race_title 内 <td class="dist">ダート1,800<span>メートル</span>（権威ソース）
    "jra_dist": re.compile(r'class="dist">(ダート|芝|障害)([\d,]+)<span>(?:メートル|ｍ)'),
    # 新マークアップ（2026-06 確認）: コース：</span>1,800<span class="unit">メートル</span><span class="detail">（芝・左）
    "jra_dist2": re.compile(r'コース：</span>([\d,]+)<span[^>]*>(?:メートル|ｍ)</span>\s*<span[^>]*>（(ダート|芝|障害)'),
}
TIMEOUT = 30
PLACE = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
         "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
# JRA出馬表ナビ: 安定インデックス → 開催選択(drl) → レース選択(dde) を POST で辿る
JRA_BASE = "https://www.jra.go.jp/JRADB/accessD.html"
JRA_INDEX = "pw01dli00/F3"   # 「出馬表」インデックス（今週開催・安定トークン）

# ── クラス序列タグ（過去走/当該レース。昇降級を機械的に効かせる・静的データ I10）──
# rank: 1=新馬/未勝利 2=1勝 3=2勝 4=3勝 5=OP特別 6=L 7=GⅢ 8=GⅡ 9=GⅠ（JRA中央のみ）。
# 序列が決まる＝当該レース rank と各馬の過去 rank を引き算するだけで昇級/同級/降級が出る。
# NAR(地方)のC/B/A・地方重賞はこの尺度に乗らない → rank=None・certain=False を返し obs-b が web 補強。
CLASS_LABEL = {1: "未勝利級", 2: "1勝クラス", 3: "2勝クラス", 4: "3勝クラス",
               5: "オープン", 6: "リステッド", 7: "GⅢ", 8: "GⅡ", 9: "GⅠ"}
# 名前付きレース（○○特別/○○S/○○賞）は文字列から格が出ない（特別=1勝〜OP・賞/Sは1勝〜GⅠまで様々）。
# ＝ human 承認で追記する curated カタログ（lazy・grade は JRA 公式準拠）。未登録は obs-b が web で確定し追記候補を上げる。
STAKES_CATALOG = {
    "ファルコンS": 7,   # GⅢ（中京・芝1400・3歳）
    "ヒヤシンスS": 6,   # L（東京・ダ1600・3歳）
    "大須特別": 3,      # 2勝クラス（中京・ダ）
}


def classify_class(name):
    """レース名 → クラス序列タグ {rank, label, certain[, band]}。
    keyword(新馬/未勝利/N勝/OP/L/GⅠ-Ⅲ) で確定→certain=True。
    名前付きで文字列から取れないものは curated catalog を引き、無ければ rank=None・certain=False＋粗バンド band。
    band=[lo,hi] は obs-b が web で 1 点に確定するまでの当て幅（特別=条件戦なので [2,5] に限定できる）。"""
    if not name:
        return {"rank": None, "label": None, "certain": False}
    raw = name.strip()
    s = unicodedata.normalize("NFKC", raw)        # 全角→半角・ローマ数字Ⅲ→III
    if raw in STAKES_CATALOG:                       # curated（名前付き重賞/特別を最優先で確定）
        r = STAKES_CATALOG[raw]
        return {"rank": r, "label": CLASS_LABEL[r], "certain": True}
    rank = None                                     # 明示グレード/条件キーワード（specific→general）
    if re.search(r"G\s*III\b", s) or re.search(r"\bG3\b", s):
        rank = 7
    elif re.search(r"G\s*II\b", s) or re.search(r"\bG2\b", s):
        rank = 8
    elif re.search(r"G\s*I\b", s) or re.search(r"\bG1\b", s):
        rank = 9
    elif "(L)" in s or "リステッド" in s:
        rank = 6
    elif "オープン" in s or re.search(r"\bOP\b", s):
        rank = 5
    elif "3勝" in s or "1600万" in s:
        rank = 4
    elif "2勝" in s or "1000万" in s:
        rank = 3
    elif "1勝" in s or "500万" in s:
        rank = 2
    elif "未勝利" in s:
        rank = 1
    elif "新馬" in s or "メイクデビュー" in s:
        return {"rank": 1, "label": "新馬", "certain": True}
    if rank is not None:
        label = "未勝利" if rank == 1 else CLASS_LABEL[rank]
        return {"rank": rank, "label": label, "certain": True}
    if "特別" in s:                                  # 名前付き条件戦（catalog未登録）＝1勝〜OP に限定できる
        return {"rank": None, "label": raw, "certain": False, "band": [2, 5]}
    return {"rank": None, "label": raw, "certain": False}   # ○○S/賞 等＝格不定。obs-b が web 確定


def class_move(last, top, race_rank):
    """各馬の過去クラスと当該レース rank から昇降級を機械判定 {last, top, vs_current}。
    last=前走 rank・top=近走最高 rank・vs_current=当該比較ラベル（rank 不明の側は None）。"""
    vs = None
    if race_rank is not None and last is not None:
        vs = "昇級" if race_rank > last else "降級" if race_rank < last else "同級"
    return {"last": last, "top": top, "vs_current": vs}


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
    """day 一覧HTML → その競馬場の全レース [{r,post_time,surface,distance,headcount,race_name}]。
    各レースを1つの<tr>行ブロックからまとめて取り出す（コース・距離・頭数・発走・レース名を
    “行単位”で対応づける）ので、障害戦など一部行のフィールド形が違っても位置ズレしない。"""
    surf_map = {"芝": "芝", "ダ": "ダ", "障": "障"}
    races = []
    for rid, rno, post, name, surf, dist, head in PATTERNS["day_row"].findall(h):
        if rid[8:10] != place:
            continue
        races.append({
            "race_id": rid,
            "r": int(rno),
            "post_time": post,
            "surface": surf_map.get(surf, surf),
            "distance": int(dist),
            "headcount": int(head),
            "turn": None,                      # 内/外回りは day 一覧に無い（race条件側で補う）
            "race_name": html.unescape(name).strip(),
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
    """JRA出馬表HTML → 全馬のスパイン(馬名/性齢/斤量/騎手/調教師/血統/枠/馬番)＋通過順由来の脚質・テン速。
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
            dm = PATTERNS["jra_past_date"].search(p)
            rcm = PATTERNS["jra_past_rc"].search(p)
            rnm = PATTERNS["jra_past_race"].search(p)
            pom = PATTERNS["jra_past_pos"].search(p)
            jkm = PATTERNS["jra_past_jockey"].search(p)
            dstm = PATTERNS["jra_past_dist"].search(p)
            tmm = PATTERNS["jra_past_time"].search(p)
            bwm = PATTERNS["jra_past_bw"].search(p)
            race_name = html.unescape(rnm.group(1)).strip() if rnm else None
            cls = classify_class(race_name)
            entry = {"first_corner": fc, "field": field,
                     "agari": float(am.group(1)) if am else None,
                     "date": (f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
                              if dm else None),
                     "venue": html.unescape(rcm.group(1)).strip() if rcm else None,
                     "race": race_name,
                     "jockey": html.unescape(jkm.group(1)).strip() if jkm else None,  # 前走騎手＝観点K乗替判定の seed
                     "dist": int(dstm.group(2).replace(",", "")) if dstm else None,   # 近走距離＝距離替わり判定の seed
                     "time": tmm.group(1) if tmm else None,                           # 走破時計＝観点A時計の seed
                     "body_weight": int(bwm.group(1)) if bwm else None,               # 馬体重＝観点G馬体トレンドの seed
                     "class_rank": cls["rank"], "class_label": cls["label"],
                     "class_certain": cls["certain"],
                     "pos": int(pom.group(1)) if pom else None}
            if cls.get("band"):
                entry["class_band"] = cls["band"]
            recent.append(entry)
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
            "trainer": g("jra_trainer"),
            "sire": g("jra_sire"),
            "damsire": g("jra_damsire"),
            "style": style,                 # 近走通過順から（粗バーより精密）
            "ten_speed": ten,
            "agari_best": min(agari) if agari else None,
            "recent": recent,
        })
    horses.sort(key=lambda x: x["no"] or 999)
    return horses


def compute_h2h(horses):
    """近走の直接対戦＝同一過去レースに今回の出走馬2頭以上が出ていた事実を抽出（JRA経路のみ）。
    観点E用: 先行争い当事者が対戦した時「実際にどちらが前だったか」をラベルや推測でなく決定論で出す。
    1角順に並べる＝先頭が「前を取った側」。★市場ゼロ: 人気は抽出しない。"""
    seen = {}
    for h in horses:
        for r in (h.get("recent") or []):
            key = (r.get("date"), r.get("venue"), r.get("race"))
            if not all(key):
                continue
            seen.setdefault(key, []).append(
                {"no": h["no"], "name": h["name"],
                 "first_corner": r["first_corner"], "pos": r.get("pos")})
    out = [{"date": d, "venue": v, "race": rn,
            "horses": sorted(lst, key=lambda x: x["first_corner"])}
           for (d, v, rn), lst in seen.items() if len(lst) >= 2]
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def parse_jra_cond(h):
    """JRA出馬表HTML → レース条件(コース種別・距離)。距離は権威ソース（race_title 内）。
    頭数は出走馬数から別途数える。取れなければ None。
    マークアップ2世代に対応: 旧 `class="dist">芝1,800<span>メートル` ／ 新 `コース：</span>1,800…（芝・左）`。"""
    m = PATTERNS["jra_dist"].search(h)
    if m:
        surf = {"ダート": "ダ", "芝": "芝", "障害": "障"}.get(m.group(1), m.group(1))
        return {"surface": surf, "distance": int(m.group(2).replace(",", ""))}
    m = PATTERNS["jra_dist2"].search(h)
    if m:
        surf = {"ダート": "ダ", "芝": "芝", "障害": "障"}.get(m.group(2), m.group(2))
        return {"surface": surf, "distance": int(m.group(1).replace(",", ""))}
    return {"surface": None, "distance": None}


def jra_fetch_race(date, place, rno):
    """JRA出馬表を取得して (全馬スパイン＋通過順, レース条件) を返す。失敗は例外。"""
    toks = jra_race_tokens(date, place)
    if rno not in toks:
        raise ValueError(f"JRA: {date} 場{place} に {int(rno)}R が無い")
    h = jra_post(toks[rno])
    horses = parse_jra_full(h)
    if not horses:
        raise ValueError(f"JRA: {date} 場{place} {int(rno)}R の出馬表をパースできず")
    cond = parse_jra_cond(h)
    cond["headcount"] = len(horses)
    return horses, cond


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
        assert data.get("distance"), "JRA距離が取れず（race_title の dist セル構造変化の疑い）"


def cmd_race(rid, as_json, do_check, class_override=None):
    """JRA優先で出馬表を取得。JRAが今週外/障害なら競馬ラボにフォールバック。"""
    date, place, rno = rid[:8], rid[8:10], rid[10:12]
    try:                                        # ① JRA（公式・完全・スパイン＋通過順＋距離を1ページ）
        horses, cond = jra_fetch_race(date, place, rno)
        data = {"race_id": rid, "source": "jra", "n": len(horses),
                "surface": cond["surface"], "distance": cond["distance"], "headcount": cond["headcount"],
                "draw_fixed": any(h["waku"] for h in horses), "horses": horses,
                "h2h": compute_h2h(horses)}
    except Exception as e:                       # ② 競馬ラボ（任意日付OK・過去/未来週やJRA障害時）
        url = f"https://www.keibalab.jp/db/race/{rid}/"
        data = parse_race(fetch(url))
        data["race_id"], data["url"], data["source"], data["jra_failed"] = rid, url, "keibalab", str(e)
        if data["n"] == 0:
            raise ValueError(f"出走馬0頭（JRA: {e} ／ 競馬ラボも race_id={rid} 不正/未掲載）")
        try:                                     # 競馬ラボ race ページは距離を持たない → day 一覧(行単位)から補完
            drow = [r for r in parse_day(fetch(f"https://www.keibalab.jp/db/race/{date}/"), place)
                    if r["r"] == int(rno)]
            if drow:
                data["surface"], data["distance"], data["headcount"] = (
                    drow[0]["surface"], drow[0]["distance"], drow[0]["headcount"])
        except Exception:
            pass
    # 距離は最重要かつ取り違えやすい → JRA(権威) と 競馬ラボ(day一覧) を突き合わせて食い違いを警告
    if data.get("source") == "jra" and data.get("distance"):
        try:
            drow = [r for r in parse_day(fetch(f"https://www.keibalab.jp/db/race/{date}/"), place)
                    if r["r"] == int(rno)]
            if drow and drow[0]["distance"] != data["distance"]:
                data["dist_mismatch"] = (f"JRA={data['surface']}{data['distance']}m"
                                         f" / 競馬ラボ={drow[0]['surface']}{drow[0]['distance']}m（JRA優先）")
        except Exception:
            pass
    # クラス序列: 当該レースの rank（--class= か title 由来）＋各馬の昇降級デルタ（昇級/同級/降級）。
    # JRA経路は title 無し→--class= 必須（SKILL が出走表条件を渡す）。競馬ラボ経路は title から拾える。
    rcs = class_override or data.get("title")
    rc = classify_class(rcs)
    data["race_class"], data["race_class_rank"], data["race_class_label"] = rcs, rc["rank"], rc["label"]
    for h in data["horses"]:
        rec = h.get("recent") or []
        ranks = [r["class_rank"] for r in rec if r.get("class_rank") is not None]
        last = rec[0].get("class_rank") if rec else None       # 前走（recent は新しい順）
        h["class_move"] = class_move(last, max(ranks) if ranks else None, rc["rank"])
    if do_check:
        self_check(data)
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    title = data.get("title") or f"{date} {PLACE.get(place, place)}{int(rno)}R"
    cond = f"  {data.get('surface') or ''}{data['distance']}m" if data.get("distance") else ""
    print(f"# {title}{cond}  [source={data['source']}]")
    if data.get("jra_failed"):
        print(f"  ※JRA不可→競馬ラボにフォールバック: {data['jra_failed']}")
    if data.get("dist_mismatch"):
        print(f"  ⚠ 距離が食い違っています: {data['dist_mismatch']}")
    rclabel = (f"{data.get('race_class_label')}(rank{data['race_class_rank']})" if data.get("race_class_rank")
               else (data.get("race_class") or "?") + "(未確定)")
    print(f"  race_id={rid}  クラス={rclabel}  頭数={data.get('headcount') or data['n']}  枠順={'確定' if data['draw_fixed'] else '未確定'}")
    leaders = [h["name"] for h in data["horses"] if (h.get("style") or "") and ("逃" in h["style"] or "先" in h["style"])]
    print(f"  ハナ・先行候補: {', '.join(leaders) or '不明'}")
    for m in (data.get("h2h") or [])[:10]:
        order = " → ".join((f"#{x['no']}" if x['no'] else "") + x['name'] + f"(1角{x['first_corner']}位"
                           + (f"・{x['pos']}着" if x['pos'] else "") + ")" for x in m["horses"])
        print(f"  対戦歴 {m['date']} {m['venue']}{m['race']}: {order}")
    for h in data["horses"]:
        head = f"{h['waku']}-{h['no']}" if h.get("no") else "?-?"
        if data["source"] == "jra":
            mv = h.get("class_move") or {}
            move = f"  {mv['vs_current']}" if mv.get("vs_current") else ""
            print(f"  {head:>5} {h['name']:<12} {h.get('sex_age') or '':<7}{h.get('weight') or '':>4}kg "
                  f"{h.get('jockey') or '':<8} → {h.get('style') or '?'}・テン{h.get('ten_speed') or '?'}{move}"
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
    h = jra_post(toks[rno])
    horses = parse_jra_full(h)
    cond = parse_jra_cond(h)
    if as_json:
        print(json.dumps({"date": date, "place": place, "r": int(rno), "source": "jra",
                          "surface": cond["surface"], "distance": cond["distance"],
                          "n": len(horses), "horses": horses}, ensure_ascii=False, indent=2)); return
    print(f"# {date} {PLACE.get(place, place)}{int(rno)}R JRA出馬表"
          f"（{cond['surface'] or ''}{cond['distance'] or '?'}m {len(horses)}頭）")
    for h in horses:
        head = f"{h['waku']}-{h['no']}" if h["no"] else "?-?"
        corners = " ".join(f"{r['first_corner']}/{r['field']}" for r in h["recent"])
        print(f"  {head:>5} {h['name']:<12} {h.get('sex_age') or '':<7}{h.get('weight') or '':>4}kg "
              f"{h.get('jockey') or '':<8} → {h.get('style') or '?'}・テン{h.get('ten_speed') or '?'}  近走1角[{corners}]")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    # --class=<当該レースのクラス文字列> 昇降級デルタの基準（例 --class=3歳上1勝クラス）
    class_override = next((a[len("--class="):] for a in sys.argv[1:] if a.startswith("--class=")), None)
    if not args:
        print(__doc__); sys.exit(1)
    cmd = args[0]
    # 後方互換: 12桁数字を直接渡したら race 扱い
    if cmd.isdigit() and len(cmd) == 12:
        cmd, args = "race", ["race"] + args
    try:
        if cmd == "race":
            cmd_race(args[1], "--json" in flags, "--self-check" in flags, class_override)
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
