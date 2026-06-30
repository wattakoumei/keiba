#!/usr/bin/env python3
"""観点I（リスク/割引要因）の決定論層 seed-enricher。

fetch_racecard.py の race 出力（seed JSON）だけから、web 調査なしで確定できる
**着順の取りこぼし要因**を符号付き減点フラグにする。obs-i-risk へ spawn 注入し、
web は「非決定論層」＝脚部不安・気性難・競走中止歴の実測だけに絞らせる（K の前走騎手と同型）。

決定論で出すフラグ（seed だけで完結＝コース知識不要・I10 のワンソース seed 群に属す）:
  - old        高齢（性齢）           7歳=-0.5 / 8歳以上=-1.0
  - decline    下降基調（recent 着順率） 前走大敗=-0.5 / 直近2走連続大敗=-1.0
  - class_jump 大幅昇級（class_move.delta） 当該比+2以上の昇級=-0.5
  - layoff     休み明け（前走→当日間隔）  120日超=-0.5 / 300日超=-1.0
合計を 0..-2 に clamp。コース依存の「不利枠」は course-geometry の領域＝ここでは出さない（I10）。
距離替わり（dist_shift）は観点D（コース/距離適性）の領分＝二重カウント回避で v1.1 で削除。
斤量は weight_adjust.py の I チャンネルが担当＝二重化しない。

これは**一次フラグ**＝obs-i が web 文脈で上書きできる（下降基調が距離/展開敗因なら割引・故障明けの斤量事情等）。
決定論で「下ごしらえ」し、web は実測だけ＝Kと同じ「決定論をエージェントの外に出す」設計。

使い方:
  python3 tools/risk_flags.py data/races/<race-id>/seed.json --json          # spawn 注入用 JSON
  python3 tools/fetch_racecard.py race <rid> --json | python3 tools/risk_flags.py - --json   # パイプ
  python3 tools/risk_flags.py <seed.json>                                     # human 表
  python3 tools/risk_flags.py --self-check                                    # 健全性検査
設計: 標準ライブラリのみ（pip 不要）。%・市場語は一切出さない（純粋情報）。
"""
import sys, json, re, argparse

# ---- 閾値の正本（ここだけ直す） ----
OLD_AGE_1   = 7     # この歳から軽い減点
OLD_AGE_2   = 8     # この歳から重い減点
BAD_RATIO   = 0.65  # 着順率 pos/field がこれ超で「大敗」
LAYOFF_1    = 120   # 日。これ超で休み明け軽
LAYOFF_2    = 300   # 日。これ超で休み明け重（≒1年以上）
CLASS_JUMP  = 2     # 現級比これ以上の昇級で減点
## dist_shift は観点D（コース/距離適性）の領分。Iとの二重カウントを避けるため削除（v1.1）


def parse_age(sex_age):
    """'牡7/鹿' 'せん5' → 7,5。失敗は None。"""
    m = re.search(r'(\d+)', sex_age or '')
    return int(m.group(1)) if m else None


def _days_between(d1, d2):
    """ISO 'YYYY-MM-DD' 2つの差日数（d2-d1）。標準ライブラリの datetime を使わず手計算で堅牢に。"""
    def ord_days(s):
        y, mo, da = (int(x) for x in s.split('-'))
        # 通算日数（プロレプティックっぽい簡易版・差分用途なので絶対値でなく相対で十分）
        m = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
             31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        return y * 365 + y // 4 - y // 100 + y // 400 + sum(m[:mo - 1]) + da
    try:
        return ord_days(d2) - ord_days(d1)
    except Exception:
        return None


def assess_horse(h, race_date, race_dist=None):
    """1頭の seed dict → {no,name,flags:[{tag,delta,note}], risk_delta(0..-2)}。"""
    flags = []
    recent = h.get("recent") or []

    # old: 高齢
    age = parse_age(h.get("sex_age"))
    if age is not None:
        if age >= OLD_AGE_2:
            flags.append({"tag": "old", "delta": -1.0, "note": f"{age}歳=高齢（能力余力の低下リスク）"})
        elif age >= OLD_AGE_1:
            flags.append({"tag": "old", "delta": -0.5, "note": f"{age}歳=やや高齢"})

    # decline: 下降基調（着順率 pos/field）
    def bad(r):
        p, f = r.get("pos"), r.get("field")
        return (p is not None and f and (p / f) > BAD_RATIO)
    if recent:
        last_bad = bad(recent[0])
        prev_bad = len(recent) >= 2 and bad(recent[1])
        if last_bad and prev_bad:
            flags.append({"tag": "decline", "delta": -1.0,
                          "note": f"直近2走連続大敗（前走{recent[0].get('pos')}/{recent[0].get('field')}・前々走{recent[1].get('pos')}/{recent[1].get('field')}）＝下降基調"})
        elif last_bad:
            flags.append({"tag": "decline", "delta": -0.5,
                          "note": f"前走大敗（{recent[0].get('pos')}/{recent[0].get('field')}）"})

    # class_jump: 大幅昇級（delta=当該rank - 前走rank。正=昇級）
    cm = h.get("class_move") or {}
    d = cm.get("delta")
    if isinstance(d, (int, float)) and d >= CLASS_JUMP:
        flags.append({"tag": "class_jump", "delta": -0.5, "note": f"現級比{d}段の昇級＝相手強化"})

    # layoff: 休み明け（前走→当日）
    if recent and recent[0].get("date") and race_date:
        gap = _days_between(recent[0]["date"], race_date)
        if gap is not None:
            if gap > LAYOFF_2:
                flags.append({"tag": "layoff", "delta": -1.0, "note": f"前走から約{gap}日＝長期休み明け"})
            elif gap > LAYOFF_1:
                flags.append({"tag": "layoff", "delta": -0.5, "note": f"前走から{gap}日＝休み明け"})

    total = max(-2.0, sum(f["delta"] for f in flags))   # 0..-2 に clamp
    return {"no": h.get("no"), "name": h.get("name"), "flags": flags, "risk_delta": round(total, 1)}


def build(seed, race_date=None):
    rd = race_date
    if not rd:
        rid = seed.get("race_id") or ""
        if len(rid) >= 8 and rid[:8].isdigit():
            rd = f"{rid[:4]}-{rid[4:6]}-{rid[6:8]}"
    race_dist = seed.get("distance")
    rows = [assess_horse(h, rd, race_dist) for h in seed.get("horses", [])]
    return {"race_date": rd, "race_dist": race_dist, "note": "決定論I（非重量・コース非依存）の一次フラグ。obs-iがwebの実測で文脈上書き可（敗因が距離/展開なら割引）。", "horses": rows}


def render_human(out):
    lines = [f"# 観点I 決定論リスク（race_date {out.get('race_date')}）  ※一次フラグ・webが文脈上書き"]
    for r in out["horses"]:
        tags = " ".join(f"[{f['tag']}{f['delta']:+}]{f['note']}" for f in r["flags"]) or "（決定論リスクなし）"
        lines.append(f"  {r['no']:>2} {r['name'][:10]:11} 計{r['risk_delta']:+}  {tags}")
    return "\n".join(lines)


def self_check():
    sample = {"race_id": "20260628-x-10", "distance": 1700, "horses": [
        {"no": 1, "name": "高齢馬", "sex_age": "牡8/鹿", "recent": [{"pos": 3, "field": 16, "date": "2026-06-01", "dist": 1700}], "class_move": {}},
        {"no": 2, "name": "下降連敗", "sex_age": "牡4", "recent": [{"pos": 15, "field": 16, "date": "2026-06-01", "dist": 1700}, {"pos": 13, "field": 16, "date": "2026-05-01", "dist": 1700}], "class_move": {}},
        {"no": 3, "name": "休み明け", "sex_age": "牝5", "recent": [{"pos": 1, "field": 12, "date": "2025-06-01", "dist": 1700}], "class_move": {}},
        {"no": 4, "name": "健康馬", "sex_age": "牡5", "recent": [{"pos": 2, "field": 14, "date": "2026-06-14", "dist": 1700}], "class_move": {"vs_current": "同級", "delta": 0}},
        {"no": 5, "name": "距離短縮", "sex_age": "牡5", "recent": [{"pos": 4, "field": 14, "date": "2026-06-14", "dist": 2100}], "class_move": {}},  # dist_shift は削除済（観点D領分）
        {"no": 6, "name": "大幅昇級馬", "sex_age": "牡4", "recent": [{"pos": 1, "field": 12, "date": "2026-06-14", "dist": 1700}], "class_move": {"vs_current": "昇級", "delta": 3}},
    ]}
    out = build(sample, race_date="2026-06-28")
    g = {r["no"]: r for r in out["horses"]}
    assert any(f["tag"] == "old" and f["delta"] == -1.0 for f in g[1]["flags"]), "8歳=old -1.0 が出ない"
    assert g[2]["risk_delta"] == -1.0, f"連続大敗=-1.0 のはず: {g[2]['risk_delta']}"
    assert any(f["tag"] == "layoff" and f["delta"] == -1.0 for f in g[3]["flags"]), "約1年=layoff -1.0 が出ない"
    assert g[4]["risk_delta"] == 0.0 and not g[4]["flags"], "健康馬は0・フラグ無し"
    assert not any(f["tag"] == "dist_shift" for f in g[5]["flags"]), "dist_shift は削除済（観点D領分）"
    assert g[5]["risk_delta"] == 0.0, "距離短縮のみの馬はリスク0"
    assert any(f["tag"] == "class_jump" and f["delta"] == -0.5 for f in g[6]["flags"]), "3段昇級=class_jump -0.5 が出ない"
    # %・市場語が出力に混入しないこと
    blob = json.dumps(out, ensure_ascii=False) + render_human(out)
    for w in ["%", "％", "人気", "オッズ", "配当", "払戻"]:
        assert w not in blob, f"禁止語 {w} が出力に混入"
    print("self-check OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seed", nargs="?", help="fetch_racecard.py race の出力 JSON ファイル（'-' で stdin）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--race-date", default=None, help="YYYYMMDD（省略時は seed の race_id から）")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        self_check(); return
    if not a.seed:
        ap.error("seed JSON のパスが必要（または --self-check）")
    raw = sys.stdin.read() if a.seed == "-" else open(a.seed, encoding="utf-8").read()
    seed = json.loads(raw)
    rd = a.race_date and f"{a.race_date[:4]}-{a.race_date[4:6]}-{a.race_date[6:8]}"
    out = build(seed, race_date=rd)
    print(json.dumps(out, ensure_ascii=False) if a.json else render_human(out))


if __name__ == "__main__":
    main()
