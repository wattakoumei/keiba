#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weight_adjust.py — 斤量・馬格(馬体重)の有利不利を決定論で重みづけする seed-enrichment ツール。

仕様の正本: .claude/skills/analyze-race/references/pace-synthesis.md（先行勢の質＝斤量×A_early/消耗）
            ＋ observation-points.md（馬格×芝ダ/馬場の相別マッピング）。本コードはその決定論ミラー。

設計思想（なぜ web 観点でなくツールか）:
  斤量=出走表 seed で既知、芝ダ・距離・馬場=レース条件で既知＝web 調査ゼロ。
  かつ効くのは「重い先行が"誰と"競るか」の交互作用＝展開合成の領域。孤立スコアにすると
  福島3R(20260627)の失敗（観点I で減点はしたがティアに反映されず）を再生産する。
  よって本ツールは per-horse スコアでなく**符号付きタグ**を出し、3チャンネルへ spawn 注入で配る:
    - pace : 斤量×先行 → A_early(二の脚)↓・消耗↑ → 共倒れ(γ系)ティアの増幅入力（PaceSynthesis へ）
    - I    : 斤量増の負担（観点I の減点材料）
    - D/G  : 馬格×芝ダ/馬場のパワー適性（観点D 適性・観点G 馬体）

不変則の遵守:
  - % は一切出さない（I2）。強弱は符号(+/−)とタグ語のみ。
  - コース物理（坂・小回り）はここで持たない＝course-geometry.md が正本(I10)。
    本ツールは seed で取れる斤量/馬格/芝ダ/距離/馬場までを担当し、坂・小回りの増幅は
    タグの注記に回して PaceSynthesis 側（course-geometry 注入済み）で適用する。

使い方:
  python3 tools/weight_adjust.py data/races/<race-id>/出走表.md                 # 人間可読の表
  python3 tools/weight_adjust.py data/races/<race-id>/出走表.md --json          # spawn 注入用 JSON
  python3 tools/weight_adjust.py <出走表.md> --going 重 --weights 9:498,12:512  # 当日（馬場・馬体重）反映
  python3 tools/weight_adjust.py --self-check                                    # 健全性検査(%混入なし・符号整合)

入力:
  出走表.md（必須。表から 馬番/性齢/斤量/脚質 を機械抽出。ヘッダ行の **コース** から芝ダ・距離を抽出）
  --going  良|稍重|重|不良   分析時は未確定が多い＝既定 良(想定)。当日に上書き（§0 当日可変）
  --weights no:kg,...        当日発表の馬体重。無ければ馬格タグは「当日更新」で保留
  --surface turf|dirt / --distance N   コース行が読めない貼り付け出走表での明示上書き
"""
import sys, json, re, argparse, statistics

# === 決定論の閾値（ワンソース＝ここだけ直す） ===
# 基準は出走馬の**中央値**（最軽量は減量騎手1頭に歪むので使わない＝福島3Rで55kg勢が全部「重」化した不具合の是正）。
# 効くのは「同レースの標準斤量(=中央値)からどれだけ上振れているか」。定量戦なら 3歳標準55 が中央値→古馬58 が +3 で立つ。
KG_HEAVY = 2.5   # 中央値から +2.5kg 以上 = 明確に重い
KG_MID   = 1.5   # +1.5〜2.5 = やや重い
KG_LIGHT = -2.0  # 中央値から -2.0kg 以下 = 軽い(利)
BIG_BODY   = 500  # ≥500kg = 大型（パワー＝ダ/道悪向き）
SMALL_BODY = 448  # ≤448kg = 小柄（軽い高速芝で機動・ダで非力寄り）

GOING_AMP = {"良": 0, "稍重": 1, "重": 2, "不良": 2}  # タフ馬場ほど斤量の負担が増す段数
LEAD_STYLES = ("逃", "先")  # 先行当事者になりうる脚質（斤量×二の脚/消耗が効く）

STY_HEAD = {"逃げ": "逃", "先行": "先", "差し": "差", "追込": "追", "自在": "先"}


def norm_style(s):
    s = (s or "").strip()
    if s in STY_HEAD:
        return STY_HEAD[s]
    return s[:1] if s else "?"


COL_KEYS = {"馬番": "no", "馬名": "name", "性齢": "sei", "斤量": "kg", "脚質": "style"}
COL_FALLBACK = {"no": 0, "name": 2, "sei": 3, "kg": 4, "style": 9}  # ヘッダ未検出時の旧固定（父|母父=2列レイアウト）


def _resolve_columns(cells):
    """ヘッダ行のセル名→列index。父|母父が1列(父×母父)/2列でレイアウトが変わり脚質位置がずれるので固定indexにしない。"""
    idx = {}
    for i, c in enumerate(cells):
        key = COL_KEYS.get(c.replace(" ", ""))
        if key and key not in idx:
            idx[key] = i
    return idx


def parse_racecard(path):
    """出走表.md からレース条件と各馬(no,name,sei,kg,style)を機械抽出。"""
    return parse_racecard_text(open(path, encoding="utf-8").read())


def parse_racecard_text(txt):
    surface, distance = None, None
    # コース行を優先（**コース** / **競馬場/コース** 等のラベル揺れに耐える）。「特記」行の直線長は距離に拾わない。
    for line in txt.splitlines():
        if "コース" in line and "特記" not in line:
            m = re.search(r"(芝|ダート|ダ)\s*(\d{3,4})\s*m", line)
            if m:
                surface = "dirt" if m.group(1) in ("ダート", "ダ") else "turf"
                distance = int(m.group(2))
                break
    horses = []
    cols = None
    for line in txt.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        names = [c.replace(" ", "") for c in cells]
        if cols is None and "馬番" in names and "脚質" in names:  # ヘッダ行で列名→indexを確定
            cols = _resolve_columns(cells)
            continue
        if not cells or not re.fullmatch(r"\d+", cells[0]):  # 区切り/非データ行は弾く
            continue
        c = cols or COL_FALLBACK

        def cell(key):
            i = c.get(key)
            return cells[i] if i is not None and i < len(cells) else ""
        try:
            no = int(cell("no"))
            kg = float(cell("kg"))
        except ValueError:
            continue
        horses.append({"no": no, "name": cell("name"), "sei": cell("sei"),
                       "kg": kg, "style": norm_style(cell("style"))})
    return surface, distance, horses


def is_old(sei):
    """性齢から古馬(4歳以上)か。3歳は斤量恩恵側。"""
    m = re.search(r"(\d+)", sei or "")
    return bool(m) and int(m.group(1)) >= 4


def build(horses, surface, distance, going, body):
    kgs = [h["kg"] for h in horses]
    kmin, kmed = min(kgs), statistics.median(kgs)
    amp = GOING_AMP.get(going, 0)
    going_word = {0: "", 1: "（タフ馬場で負担増）", 2: "（道悪で負担さらに増）"}[amp]
    dirt = surface == "dirt"

    out = []
    leads_heavy = []
    leads_light = []
    for h in horses:
        rel = round(h["kg"] - kmed, 1)  # 中央値=同レース標準斤量からの上振れ（これが効く量）
        sg = f"+{rel:g}" if rel >= 0 else f"{rel:g}"
        if rel >= KG_HEAVY:
            level = "重"
        elif rel >= KG_MID:
            level = "やや重"
        elif rel <= KG_LIGHT:
            level = "軽"
        else:
            level = "並"
        tags = []
        is_lead = h["style"] in LEAD_STYLES
        old = is_old(h["sei"])

        # --- pace チャンネル: 斤量×先行 → 二の脚↓・消耗↑（最重要＝ティアを動かす） ---
        if is_lead and level in ("重", "やや重"):
            note = f"斤量{h['kg']:g}={'古馬で標準' if old else '標準'}{sg}kg×{h['style']}"
            tags.append({"ch": "pace", "sign": "-",
                         "text": f"{note}: 二の脚で抜け出しにくく競ると消耗大→共倒れ寄与"
                                 f"{going_word}（先行当事者が複数なら差し台頭γのティアを上げる）"})
            leads_heavy.append(h["no"])
        elif is_lead and level == "軽":
            leads_light.append(h)

        # --- I チャンネル: 斤量増の負担（観点I 減点材料） ---
        if level in ("重", "やや重"):
            tags.append({"ch": "I", "sign": "-",
                         "text": f"斤量{h['kg']:g}=標準{sg}kg{('・古馬で3歳勢に斤量負担' if old else '')}{going_word}"})

        # --- D/G チャンネル: 馬格×芝ダ/馬場（馬体重があるときだけ。無い馬は race.body_weight_status の一文に集約＝冗長回避） ---
        bw = body.get(h["no"])
        if bw is not None:
            if bw >= BIG_BODY and (dirt or amp):
                tags.append({"ch": "D/G", "sign": "+",
                             "text": f"馬体重{bw}=大型×{'ダート' if dirt else ''}{going_word or '良'}: パワー優位で斤量を相殺"})
            elif bw <= SMALL_BODY:
                sign, t = ("-", "ダで非力寄り") if dirt else ("+", "軽い高速芝で機動")
                tags.append({"ch": "D/G", "sign": sign, "text": f"馬体重{bw}=小柄: {t}"})

        out.append({"no": h["no"], "name": h["name"], "sei": h["sei"], "kg": h["kg"],
                    "style": h["style"], "rel": rel, "level": level, "tags": tags})

    # 軽量の先行は「重ハンデ先行が複数いて競り潰れる流れ」でのみ相対浮上＝条件付きで後付け（無条件に+を撒かない）
    if len(leads_heavy) >= 2:
        by_no = {r["no"]: r for r in out}
        for h in leads_light:
            by_no[h["no"]]["tags"].insert(0, {"ch": "pace", "sign": "+",
                "text": f"斤量{h['kg']:g}=軽量×{h['style']}: 重ハンデ先行{leads_heavy}が競り潰れる流れなら相対浮上"})

    leads = [h for h in horses if h["style"] in LEAD_STYLES]
    if len(leads_heavy) >= 2:
        front_verdict = (f"先行当事者の重ハンデが{len(leads_heavy)}頭(馬番{leads_heavy})＝"
                         f"競れば共倒れ。差し台頭(γ系)パターンのティアを上げる増幅入力。"
                         f"※単騎で楽に行ければ前残りは残る（『重い馬が競るか』条件付き）")
    elif len(leads_heavy) == 1:
        front_verdict = (f"重ハンデの先行は馬番{leads_heavy}の1頭のみ＝単騎なら前残り維持、"
                         f"他の先行に競られると消耗。ティアは先行争いの頭数しだい")
    else:
        front_verdict = "先行勢に明確な重ハンデなし＝斤量はティアを動かさない（脚質/能力で読む）"

    race = {
        "surface": surface, "distance": distance, "going": going,
        "kg_min": kmin, "kg_median": kmed,
        "front_runners": [{"no": h["no"], "kg": h["kg"], "style": h["style"]} for h in leads],
        "front_verdict": front_verdict,
        "body_weight_status": "取得済み" if body else "未取得＝当日更新（馬格タグは保留）",
    }
    return race, out


def render_human(race, rows):
    lines = []
    lines.append(f"# 重量重みづけ  {race['surface']} {race['distance']}m  馬場:{race['going']}  "
                 f"(最軽量{race['kg_min']:g} / 中央{race['kg_median']:g})")
    lines.append(f"先行勢の質: {race['front_verdict']}")
    lines.append(f"馬体重: {race['body_weight_status']}\n")
    lines.append("no  斤量  脚 相対  段階  タグ")
    for r in rows:
        tg = " / ".join(f"[{t['ch']}{t['sign']}]{t['text']}" for t in r["tags"]) or "—"
        sg = f"+{r['rel']:g}" if r["rel"] >= 0 else f"{r['rel']:g}"
        lines.append(f"{r['no']:>2}  {r['kg']:>4g}  {r['style']}  {sg:<4} {r['level']:<3}  {tg}")
    return "\n".join(lines)


def parse_weights(s):
    body = {}
    if not s:
        return body
    s = s.strip()
    if s.startswith("{"):
        return {int(k): int(v) for k, v in json.loads(s).items()}
    for part in s.split(","):
        if ":" in part:
            no, kg = part.split(":")
            body[int(no)] = int(kg)
    return body


def self_check():
    # 福島3R を縮約（中央値=55 になるよう 3歳55 を複数置く）。⑨⑫=58先行 / ⑤=55先行 / ①=50先行 / 差し勢
    sample = [
        {"no": 9, "name": "A", "sei": "牡4", "kg": 58.0, "style": "先"},
        {"no": 12, "name": "B", "sei": "牡4", "kg": 58.0, "style": "逃"},
        {"no": 5, "name": "C", "sei": "牡3", "kg": 55.0, "style": "先"},
        {"no": 1, "name": "D", "sei": "牝3", "kg": 50.0, "style": "先"},
        {"no": 2, "name": "E", "sei": "牡3", "kg": 55.0, "style": "追"},
        {"no": 3, "name": "F", "sei": "牡3", "kg": 55.0, "style": "差"},
        {"no": 4, "name": "G", "sei": "牡3", "kg": 55.0, "style": "追"},
    ]
    race, rows = build(sample, "dirt", 1700, "良", {})
    by = {r["no"]: r for r in rows}
    blob = json.dumps({"race": race, "horses": rows}, ensure_ascii=False)
    assert "%" not in blob and "％" not in blob, "出力に%混入(I2違反)"
    for r in rows:
        for t in r["tags"]:
            assert t["sign"] in ("+", "-", "?"), "符号不正"
    assert race["kg_median"] == 55, "中央値が標準斤量(55)にならない＝基準ズレ"
    # 58kg先行2頭(⑨⑫)だけが重判定＝共倒れ増幅入力に立つ（福島3R の機序を再現）
    assert by[9]["level"] == "重" and by[12]["level"] == "重"
    assert "γ" in race["front_verdict"] and "9" in race["front_verdict"] and "12" in race["front_verdict"]
    # 是正の核: 55kg先行⑤(実際に3着で残った)は「並」＝共倒れ側に立たせない。50kg①も重でない。
    assert by[5]["level"] == "並", "55kg先行が重判定＝最軽量基準ノイズの再発"
    assert by[1]["level"] != "重"
    # パーサ回帰ガード: 父×母父が1列の出走表で脚質列がずれない（福島9Rの不具合）＋ラベル揺れ/特記行汚染のコース抽出
    md = (
        "- **競馬場/コース**: 福島・ダート1150m（右回り・小回り）\n"
        "- **コース特記**: ダ直線295.7m、芝スタート約100m\n"
        "| 馬番 | 枠 | 馬名 | 性齢 | 斤量 | 騎手 | 調教師 | 父×母父 | 脚質 | テン速 | 上り最速 | 昇降級 |\n"
        "|---:|---:|---|---|---:|---|---|---|---|---|---:|---|\n"
        "| 1 | 1 | テスト馬 | 牡4 | 58.0 | 騎手 | 厩舎 | 父×母父 | 先 | 中 | 36.9 | 同級 |\n"
    )
    sfc, dist, hs = parse_racecard_text(md)
    assert sfc == "dirt" and dist == 1150, f"コース抽出失敗 surface={sfc} dist={dist}（ラベル揺れ/特記行汚染）"
    assert hs and hs[0]["style"] == "先", f"脚質列ズレ＝テン速を誤読 style={hs and hs[0]['style']}"
    print("self-check OK: 中央値基準・%非混入・符号整合・58kg先行2頭のみ共倒れ増幅・55kg先行⑤は並判定・列名パーサ(父×母父1列)健全")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("racecard", nargs="?", help="data/races/<race-id>/出走表.md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--going", default="良", choices=list(GOING_AMP))
    ap.add_argument("--weights", default=None, help="当日馬体重 no:kg,... または JSON")
    ap.add_argument("--surface", default=None, choices=["turf", "dirt"])
    ap.add_argument("--distance", type=int, default=None)
    a = ap.parse_args()

    if a.self_check:
        self_check()
        return
    if not a.racecard:
        ap.error("出走表.md のパスが必要（または --self-check）")

    surface, distance, horses = parse_racecard(a.racecard)
    surface = a.surface or surface
    distance = a.distance or distance
    if not horses:
        ap.error("出走表から馬を抽出できず（表の体裁を確認）")
    race, rows = build(horses, surface, distance, a.going, parse_weights(a.weights))

    if a.json:
        print(json.dumps({"race": race, "horses": rows}, ensure_ascii=False))
    else:
        print(render_human(race, rows))


if __name__ == "__main__":
    main()
