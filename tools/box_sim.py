#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""box_sim.py — 箱戦略バックテスト（馬連・三連複の的中率と回収率）。I1-R トラック。

何をするか:
  過去レースの「記録済み予測」（report.json の 印・rank_order・box_reverse・pattern_fit＝後知恵ゼロ）から
  機械的に箱（買い目候補）を組み、results.jsonl の finish＋record:"payout"（確定払戻）と突合して
  戦略ごとの 的中率・回収率（総払戻÷総点数×100円）・払戻分布 を集計する。

規律（I1-R）:
  - 結果層の事実検証ツール。出力は端末のみ＝予想成果物（report.json/predictions.jsonl/research-*.json）
    と /review-prediction の精度採点には一切流さない（回収率を採点に混ぜない）。
  - 金額最適化（Kelly・資金配分）はしない。どの箱をいくら買うかは人間判断。
  - 読み取り専用＝results.jsonl / report.json を書き換えない。

STRATEGIES はここが正本（ev_board.py が import して同じ箱候補を EV 表示に使う＝ワンソース）。

使い方:
  python3 tools/box_sim.py                       # 全戦略×全コーパスの集計表
  python3 tools/box_sim.py --strategy trio_box4  # 1戦略＋レース明細
  python3 tools/box_sim.py --since 20260620      # 日付でフィルタ
  python3 tools/box_sim.py --races 20260628-kokura-10,20260628-kokura-11
  python3 tools/box_sim.py --json
  python3 tools/box_sim.py --self-check          # 合成 fixture で既知ROIを検算（ネット不要）
"""
import sys, os, json, glob, argparse, itertools, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "data", "results.jsonl")
RACES = os.path.join(ROOT, "data", "races")

MARK_1 = ("◎",)
MARK_2 = ("◯", "○")
MARK_3 = ("▲",)


# ---------------- 箱の組み立て（源＝記録済み予測のみ・後知恵ゼロ） ----------------

def _no_by_mark(rank, syms):
    for r in rank:
        if r.get("mark") in syms:
            return r.get("no")
    return None


def _no_by_order(rank, k):
    for r in rank:
        if r.get("rank_order") == k:
            return r.get("no")
    return None


def build_umaren_hon(report):
    """馬連 ◎-○ 1点。"""
    a = _no_by_mark(report["rank"], MARK_1)
    b = _no_by_mark(report["rank"], MARK_2)
    if a is None or b is None:
        return []
    return [tuple(sorted((a, b)))]


def build_umaren_nagashi(report):
    """馬連 ◎-{rank_order 2..4} 3点。"""
    a = _no_by_mark(report["rank"], MARK_1)
    if a is None:
        return []
    outs = []
    for k in (2, 3, 4):
        b = _no_by_order(report["rank"], k)
        if b is not None and b != a:
            outs.append(tuple(sorted((a, b))))
    return sorted(set(outs))


def build_trio_marks1(report):
    """三連複 ◎◯▲ 1点。"""
    nos = [_no_by_mark(report["rank"], m) for m in (MARK_1, MARK_2, MARK_3)]
    if any(n is None for n in nos) or len(set(nos)) < 3:
        return []
    return [tuple(sorted(nos))]


def build_trio_box4(report):
    """三連複 rank_order 上位4頭 BOX（4点）。"""
    nos = [_no_by_order(report["rank"], k) for k in (1, 2, 3, 4)]
    nos = [n for n in nos if n is not None]
    if len(nos) < 4:
        return []
    return sorted(tuple(sorted(c)) for c in itertools.combinations(nos, 3))


def build_trio_boxrev(report, cap=20, floor=None):
    """三連複 本線 box_reverse の center 軸-inside 流し（inside から C(n,2)・20点cap）。
    floor 指定時は inside を place_prob≥floor で間引く（center は残す）。"""
    brs = (report.get("pace") or {}).get("box_reverse") or []
    br = next((b for b in brs if "本線" in str(b.get("tier", ""))), brs[0] if brs else None)
    if not br:
        return []
    pp = {r.get("no"): (r.get("place_prob") or 0) for r in report.get("rank", [])}
    centers = [n for n in (br.get("center") or []) if n is not None]
    inside = [n for n in (br.get("inside") or []) if n is not None
              and (floor is None or pp.get(n, 0) >= floor)]
    if not centers or len(set(centers + inside)) < 3:
        return []
    outs = set()
    for c in centers:
        pool = [n for n in centers + inside if n != c]
        for pair in itertools.combinations(sorted(set(pool)), 2):
            outs.add(tuple(sorted((c,) + pair)))
    return sorted(outs)[:cap]


def build_trio_boxrev_p20(report):
    """三連複 本線box_reverse流し＋inside place_prob≥20%（薄い相手を間引く）。
    実測(2026-07-06・27R): 床なし173.5%(除最大67.3%)→床20%で343.8%(除最大126.4%)・的中5全維持。
    keiba-web/src/components/RaceView.jsx「三連複の箱」が同値ミラー＝床/capを変えたら両方直す。"""
    return build_trio_boxrev(report, floor=0.20)


def build_wide_marks(report):
    """ワイド ◎-印(◯/▲/△)全流し。"""
    a = _no_by_mark(report["rank"], MARK_1)
    if a is None:
        return []
    outs = []
    for r in report["rank"]:
        if r.get("mark") in ("◯", "○", "▲", "△") and r.get("no") not in (None, a):
            outs.append(tuple(sorted((a, r["no"]))))
    return sorted(set(outs))


def build_wide_pairfit(report, cap=8):
    """ワイド 同一パターン◎ペア（各パターンで展開列◎の馬同士・パターン横断で重複統合）。"""
    pats = [p.get("id") for p in (report.get("pace") or {}).get("patterns", []) if p.get("id")]
    outs = set()
    for p in pats:
        nos = sorted({r["no"] for r in report["rank"]
                      if r.get("no") is not None and (r.get("pattern_fit") or {}).get(p) == "◎"})
        for c in itertools.combinations(nos, 2):
            outs.add(c)
    return sorted(outs)[:cap]


def build_wide_pairfit_p15(report, cap=8, floor=0.15):
    """ワイド 同一パターン◎ペア＋両頭 place_prob≥floor（エンジン床で薄いペアを間引く）。
    ここが抽出条件の正本。keiba-web/src/components/RaceView.jsx「箱組みガイド」が同値ミラー＝floor/cap を変えたら両方直す。"""
    pats = [p.get("id") for p in (report.get("pace") or {}).get("patterns", []) if p.get("id")]
    outs = set()
    for p in pats:
        nos = sorted({r["no"] for r in report["rank"]
                      if r.get("no") is not None and (r.get("pattern_fit") or {}).get(p) == "◎"
                      and (r.get("place_prob") or 0) >= floor})
        for c in itertools.combinations(nos, 2):
            outs.add(c)
    return sorted(outs)[:cap]


def build_wide_pairfit_p20(report):
    """ワイド 同一パターン◎ペア＋両頭 place_prob≥20%（p15 の床強化版・追跡用）。
    正本の床は p15（web ミラー対象）＝こちらは測定トラックのみ。床0.22 に崖あり（的中を落とす）。"""
    return build_wide_pairfit_p15(report, floor=0.20)


def build_trio_allfit(report):
    """三連複 展開列が全パターン◎/○（△無し・欠落無し）の馬 BOX（3〜6頭時のみ）。"""
    pats = [p.get("id") for p in (report.get("pace") or {}).get("patterns", []) if p.get("id")]
    if not pats:
        return []
    nos = []
    for r in report["rank"]:
        pf = r.get("pattern_fit") or {}
        if all(pf.get(p) in ("◎", "○", "◯") for p in pats):
            nos.append(r.get("no"))
    nos = [n for n in nos if n is not None]
    if not (3 <= len(nos) <= 6):
        return []
    return sorted(tuple(sorted(c)) for c in itertools.combinations(sorted(set(nos)), 3))


# 正本（ev_board.py が import）。bet: payouts のキー（umaren=馬連 / sanrenpuku=三連複）
STRATEGIES = {
    "umaren_hon":     {"bet": "umaren",     "label": "馬連 ◎-○ 1点",                "build": build_umaren_hon},
    "umaren_nagashi": {"bet": "umaren",     "label": "馬連 ◎-上位2..4位 流し3点",     "build": build_umaren_nagashi},
    "trio_marks1":    {"bet": "sanrenpuku", "label": "三連複 ◎◯▲ 1点",              "build": build_trio_marks1},
    "trio_box4":      {"bet": "sanrenpuku", "label": "三連複 上位4頭BOX 4点",         "build": build_trio_box4},
    "trio_boxrev":    {"bet": "sanrenpuku", "label": "三連複 本線box_reverse 軸流し",  "build": build_trio_boxrev},
    "trio_boxrev_p20": {"bet": "sanrenpuku", "label": "三連複 boxrev流し p≥20%",      "build": build_trio_boxrev_p20},
    "trio_allfit":    {"bet": "sanrenpuku", "label": "三連複 展開列オール圏内BOX",     "build": build_trio_allfit},
    "wide_hon":       {"bet": "wide",       "label": "ワイド ◎-○ 1点",              "build": build_umaren_hon},
    "wide_nagashi":   {"bet": "wide",       "label": "ワイド ◎-上位2..4位 流し3点",   "build": build_umaren_nagashi},
    "wide_marks":     {"bet": "wide",       "label": "ワイド ◎-印(◯▲△)全流し",     "build": build_wide_marks},
    "wide_pairfit":   {"bet": "wide",       "label": "ワイド 同一パターン◎ペア",      "build": build_wide_pairfit},
    "wide_pairfit_p15": {"bet": "wide",     "label": "ワイド 同パターン◎ペア p≥15%",  "build": build_wide_pairfit_p15},
    "wide_pairfit_p20": {"bet": "wide",     "label": "ワイド 同パターン◎ペア p≥20%",  "build": build_wide_pairfit_p20},
}
K_OF_BET = {"umaren": 2, "sanrenpuku": 3, "wide": 3}  # wide の k=3 は的中判定（両頭が3着内）用


# ---------------- コーパス突合 ----------------

def load_corpus(results_path=RESULTS, races_dir=RACES):
    """finish＋payout＋report.json が揃うレース（payout 無しは hit のみ算出）。"""
    finish, payouts = {}, {}
    if os.path.exists(results_path):
        for line in open(results_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            rid = d.get("race_id")
            if not rid:
                continue
            if "finish" in d:
                finish[rid] = {h["no"]: h.get("pos") for h in d["finish"] if h.get("no")}
            if d.get("record") == "payout":
                payouts[rid] = d.get("payouts") or {}
    corpus = []
    for rid, fin in sorted(finish.items()):
        rp = os.path.join(races_dir, rid, "report.json")
        if not os.path.exists(rp):
            continue
        report = json.load(open(rp, encoding="utf-8"))
        if not report.get("rank"):
            continue
        corpus.append({"race_id": rid, "report": report, "finish": fin,
                       "payouts": payouts.get(rid)})
    return corpus


def eval_race(strategy, race):
    """1レース×1戦略 → {points, hit, payoff(円・100円あたり×点), cost, skip理由}。"""
    spec = STRATEGIES[strategy]
    combos = spec["build"](race["report"])
    if not combos:
        return {"skip": "箱を組めない（印/展開列/box_reverse 不足）"}
    bet, k = spec["bet"], K_OF_BET[spec["bet"]]
    topk = {no for no, pos in race["finish"].items() if pos is not None and pos <= k}
    pay_entries = (race["payouts"] or {}).get(bet) if race["payouts"] is not None else None
    hit_combos, payoff = [], 0
    for c in combos:
        if pay_entries is not None:
            for e in pay_entries:
                if sorted(e["comb"]) == list(c):
                    hit_combos.append(c)
                    payoff += e["yen"]
                    break
        else:
            if set(c) <= topk:
                hit_combos.append(c)
    out = {"points": len(combos), "combos": combos, "hit": bool(hit_combos),
           "hit_combos": hit_combos, "cost": len(combos) * 100}
    if race["payouts"] is not None:
        if pay_entries is None:
            return {"skip": f"{bet} の払戻記録なし（不発売/欠落）"}
        out["payoff"] = payoff
    else:
        out["payoff"] = None   # 配当未収集＝的中のみ
    return out


def run(corpus, strategies=None):
    strategies = strategies or list(STRATEGIES)
    agg = {}
    for sid in strategies:
        races_used, skipped, details = [], [], []
        for race in corpus:
            r = eval_race(sid, race)
            if "skip" in r:
                skipped.append({"race_id": race["race_id"], "reason": r["skip"]})
                continue
            races_used.append((race["race_id"], r))
            details.append({"race_id": race["race_id"], "points": r["points"],
                            "hit": r["hit"], "payoff": r["payoff"],
                            "combos": [list(c) for c in r["combos"]],
                            "hit_combos": [list(c) for c in r["hit_combos"]]})
        n = len(races_used)
        hits = [r for _, r in races_used if r["hit"]]
        with_pay = [r for _, r in races_used if r["payoff"] is not None]
        cost = sum(r["cost"] for r in with_pay)
        payoff = sum(r["payoff"] for r in with_pay)
        hit_payoffs = [r["payoff"] for r in with_pay if r["hit"] and r["payoff"]]
        agg[sid] = {
            "label": STRATEGIES[sid]["label"], "bet": STRATEGIES[sid]["bet"],
            "races": n, "skipped": len(skipped), "skip_detail": skipped,
            "points_total": sum(r["points"] for _, r in races_used),
            "hit_races": len(hits), "hit_rate": round(len(hits) / n, 3) if n else None,
            "roi_races": len(with_pay), "cost_yen": cost, "payoff_yen": payoff,
            "roi": round(payoff / cost, 3) if cost else None,
            "hit_payoff_dist": ({"min": min(hit_payoffs), "median": int(statistics.median(hit_payoffs)),
                                 "max": max(hit_payoffs)} if hit_payoffs else None),
            "details": details,
        }
    return agg


def human(agg, detail_for=None):
    lines = ["# 箱戦略バックテスト（I1-R・回収率=総払戻÷総点数×100円）", ""]
    lines.append(f"{'戦略':<16} {'券種':<10} {'R数':>4} {'skip':>4} {'点':>5} {'的中R':>5} "
                 f"{'的中率':>7} {'回収率':>7} {'払戻(的中時 min/med/max)':<24}")
    for sid, a in agg.items():
        hr = f"{a['hit_rate']*100:5.1f}%" if a["hit_rate"] is not None else "    -"
        roi = f"{a['roi']*100:5.1f}%" if a["roi"] is not None else "    -"
        d = a["hit_payoff_dist"]
        dist = f"{d['min']}/{d['median']}/{d['max']}円" if d else "-"
        lines.append(f"{sid:<16} {a['label'][:10]:<10} {a['races']:>4} {a['skipped']:>4} "
                     f"{a['points_total']:>5} {a['hit_races']:>5} {hr:>7} {roi:>7} {dist:<24}")
    if detail_for and detail_for in agg:
        lines.append("")
        lines.append(f"## 明細: {detail_for}（{agg[detail_for]['label']}）")
        for d in agg[detail_for]["details"]:
            mark = "○" if d["hit"] else "×"
            pay = f"{d['payoff']}円" if d["payoff"] is not None else "配当未収集"
            lines.append(f"  {mark} {d['race_id']}  {d['points']}点  {pay}  hit={d['hit_combos']}")
        for s in agg[detail_for]["skip_detail"]:
            lines.append(f"  skip {s['race_id']}: {s['reason']}")
    lines.append("")
    lines.append("※ 事実の検証トラック（買い目・金額の推奨ではない）。券種・金額・実ベットは人間判断。")
    return "\n".join(lines)


# ---------------- self-check（合成 fixture・ネット不要） ----------------

def self_check():
    errs = []
    report = {
        "rank": [
            {"no": 1, "mark": "◎", "rank_order": 1, "pattern_fit": {"α": "◎", "β": "○"}, "place_prob": 0.55},
            {"no": 2, "mark": "◯", "rank_order": 2, "pattern_fit": {"α": "○", "β": "◎"}, "place_prob": 0.40},
            {"no": 3, "mark": "▲", "rank_order": 3, "pattern_fit": {"α": "○", "β": "○"}, "place_prob": 0.30},
            {"no": 4, "mark": "△", "rank_order": 4, "pattern_fit": {"α": "△"}, "place_prob": 0.15},
            {"no": 5, "mark": "—", "rank_order": 5, "pattern_fit": {}, "place_prob": 0.05},
        ],
        "pace": {"patterns": [{"id": "α"}, {"id": "β"}],
                 "box_reverse": [{"pattern": "α", "tier": "本線★★★",
                                  "center": [1], "inside": [2, 3], "spot": [4], "drop": [5]}]},
    }
    finish = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
    payouts = {"umaren": [{"comb": [1, 2], "yen": 560}],
               "sanrenpuku": [{"comb": [1, 2, 3], "yen": 2990}]}
    corpus = [{"race_id": "t1", "report": report, "finish": finish, "payouts": payouts}]
    agg = run(corpus)
    # 既知ROI: umaren_hon 1点100円→560円=5.6 / trio_box4 4点400円→2990円=7.475
    if agg["umaren_hon"]["roi"] != 5.6:
        errs.append(f"umaren_hon roi {agg['umaren_hon']['roi']} ≠ 5.6")
    if agg["trio_box4"]["roi"] != 7.475:
        errs.append(f"trio_box4 roi {agg['trio_box4']['roi']} ≠ 7.475")
    if agg["trio_marks1"]["roi"] != 29.9:
        errs.append(f"trio_marks1 roi {agg['trio_marks1']['roi']} ≠ 29.9")
    # boxrev: center1×inside{2,3}=C(2,2)=1点 {1,2,3} → 2990円
    if agg["trio_boxrev"]["points_total"] != 1 or agg["trio_boxrev"]["roi"] != 29.9:
        errs.append(f"trio_boxrev 不一致: {agg['trio_boxrev']['points_total']}点 roi={agg['trio_boxrev']['roi']}")
    # allfit: 全パターン◎/○ は {1,2,3} → BOX 1点的中
    if agg["trio_allfit"]["points_total"] != 1 or not agg["trio_allfit"]["hit_races"]:
        errs.append(f"trio_allfit 不一致: {agg['trio_allfit']}")
    # boxrev p20 床: inside{2,3} は place 0.40/0.30 で残る＝床なしと同一の1点
    if agg["trio_boxrev_p20"]["points_total"] != 1 or agg["trio_boxrev_p20"]["roi"] != 29.9:
        errs.append(f"trio_boxrev_p20 不一致: {agg['trio_boxrev_p20']}")
    # 床が実際に間引くこと: floor=0.35 で inside 3(0.30) が落ち {1,2} の2頭→箱不成立
    if build_trio_boxrev(report, floor=0.35) != []:
        errs.append(f"boxrev floor 間引き不発: {build_trio_boxrev(report, floor=0.35)}")
    # wide p20 床: 同一パターン◎ 3頭のうち place 0.15 の1頭が床で消え、残る2頭の1ペアだけ
    rep_w = {"rank": [
        {"no": 1, "pattern_fit": {"α": "◎"}, "place_prob": 0.55},
        {"no": 2, "pattern_fit": {"α": "◎"}, "place_prob": 0.40},
        {"no": 4, "pattern_fit": {"α": "◎"}, "place_prob": 0.15},
    ], "pace": {"patterns": [{"id": "α"}]}}
    if build_wide_pairfit_p20(rep_w) != [(1, 2)]:
        errs.append(f"wide_pairfit_p20 不一致: {build_wide_pairfit_p20(rep_w)}")
    # 外れ側: 着順を入れ替え payoff 0
    finish2 = {1: 5, 2: 2, 3: 3, 4: 1, 5: 4}
    payouts2 = {"umaren": [{"comb": [2, 4], "yen": 1200}],
                "sanrenpuku": [{"comb": [2, 3, 4], "yen": 8000}]}
    agg2 = run([{"race_id": "t2", "report": report, "finish": finish2, "payouts": payouts2}],
               ["umaren_hon", "trio_marks1"])
    if agg2["umaren_hon"]["hit_races"] != 0 or agg2["umaren_hon"]["roi"] != 0.0:
        errs.append(f"外れ検定 umaren_hon: {agg2['umaren_hon']}")
    # 配当未収集レース: hit は数え ROI は除外
    agg3 = run([{"race_id": "t3", "report": report, "finish": finish, "payouts": None}], ["umaren_hon"])
    a3 = agg3["umaren_hon"]
    if a3["hit_races"] != 1 or a3["roi_races"] != 0 or a3["roi"] is not None:
        errs.append(f"配当未収集の扱い不一致: {a3}")
    # 同着（複数エントリ）: どれかに一致すれば的中・payoff はそのエントリ分
    payouts4 = {"umaren": [{"comb": [1, 2], "yen": 300}, {"comb": [1, 3], "yen": 400}]}
    agg4 = run([{"race_id": "t4", "report": report, "finish": finish, "payouts": payouts4}], ["umaren_hon"])
    if agg4["umaren_hon"]["payoff_yen"] != 300:
        errs.append(f"同着処理不一致: {agg4['umaren_hon']['payoff_yen']}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default=None, choices=list(STRATEGIES), help="1戦略＋明細表示")
    ap.add_argument("--since", default=None, help="YYYYMMDD 以降のレースのみ")
    ap.add_argument("--races", default=None, help="カンマ区切りの race_id 限定")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        errs = self_check()
        if errs:
            print("SELF-CHECK FAIL: " + "; ".join(errs), file=sys.stderr)
            sys.exit(1)
        print("self-check OK (既知ROI検算 / 外れ / 配当未収集 / 同着)")
        return

    corpus = load_corpus()
    if args.since:
        corpus = [c for c in corpus if c["race_id"][:8] >= args.since]
    if args.races:
        keep = set(args.races.split(","))
        corpus = [c for c in corpus if c["race_id"] in keep]
    strategies = [args.strategy] if args.strategy else None
    agg = run(corpus, strategies)
    if args.json:
        print(json.dumps(agg, ensure_ascii=False, indent=2))
    else:
        print(human(agg, detail_for=args.strategy))


if __name__ == "__main__":
    main()
