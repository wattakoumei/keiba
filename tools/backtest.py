#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest.py — エンジン経路の一括再採点（バックテスト）。

何をするか:
  data/races/*/（research-*.json＋report.json＋seed.json）と data/results.jsonl を突合できた全レースを、
  現行 PARAMS（または --set 上書き）で score_race に再生させ、率の精度指標を一括集計する。
  併せて report.json に記録済みの論理の並び（rank_order・◎）を「記録時の参照値」として同じ指標で並記する
  （論理側はパラメータ非依存＝再生できないので、あくまで当時ログの採点）。

なぜコード化するか:
  ノブ・エンジンを変えたとき「次のレースから前向きに試す」しか検証手段が無いと、改善と改悪を区別できない。
  過去コーパスに対する A/B（現行 vs 上書き）を決定論で回し、採用判断の材料にする。

検証できる範囲（重要）:
  再生できるのはエンジン経路（観点スコア→score_race→win_prob/place_prob）のみ。
  読み筋（散文・印・rank_order＝人間の論理）は再生不能＝前向き比較（/review-prediction の蓄積）でしか測れない。

使い方:
  python3 tools/backtest.py                          # 現行PARAMSで全コーパス採点
  python3 tools/backtest.py --set T=0.7              # A/B: 現行 vs T上書き（--set は複数可）
  python3 tools/backtest.py --races <id>,<id>        # レース絞り込み
  python3 tools/backtest.py --since 20260620         # 日付下限（race_id 先頭8桁）
  python3 tools/backtest.py --json                   # 構造化出力（効果測定の下流用）
  python3 tools/backtest.py --self-check             # 指標関数の健全性検査（データ不要）

規律:
  読み取り専用＝report.json/results.jsonl を一切書き換えない。市場データ不使用（I1）。
  複勝は top3 事象で固定（engine の place_prob=Harville top3 と定義を揃える。
  5〜7頭立てのJRA複勝ルール=top2 とは別物なので少頭数レースは表中で n を確認すること）。
"""
import sys, os, json, argparse, math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import score_race
import calibrate_T  # load_results / build_race_input を再利用（コーパス突合のワンソース）

EPS = 1e-9


# === 指標プリミティブ ===

def avg_ranks(vals, desc=False):
    """値リスト→1始まり順位（同値は平均順位）。desc=True で大きいほど上位。"""
    order = sorted(range(len(vals)), key=lambda i: (-vals[i] if desc else vals[i]))
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Spearman ρ（同値は平均順位）。要素2未満・分散0は None。"""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx, ry = avg_ranks(xs), avg_ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx < EPS or vy < EPS:
        return None
    return cov / math.sqrt(vx * vy)


def order_metrics(pred_rank_of, actual_pos_of, nos):
    """予測順位マップ vs 実着順マップから ρ・top3重なりを出す（エンジン/論理で共用）。"""
    xs = [pred_rank_of[n] for n in nos]
    ys = [actual_pos_of[n] for n in nos]
    rho = spearman(xs, ys)
    top3_pred = set(sorted(nos, key=lambda n: pred_rank_of[n])[:3])
    top3_act = set(sorted(nos, key=lambda n: actual_pos_of[n])[:3])
    k = min(3, len(nos))
    overlap = len(top3_pred & top3_act) / k if k else None
    return rho, overlap


# === コーパス ===

def load_corpus(race_filter=None, since=None):
    """results.jsonl と突合できたレースの (race_id, engine入力, report, actual{no:pos}) を返す。"""
    results = calibrate_T.load_results()
    races_dir = os.path.join(ROOT, "data", "races")
    corpus, skipped = [], []
    for rid in sorted(os.listdir(races_dir)):
        if race_filter and rid not in race_filter:
            continue
        if since and rid[:8] < since:
            continue
        if rid not in results:
            continue
        data, rpt = calibrate_T.build_race_input(os.path.join(races_dir, rid))
        if data is None:
            skipped.append(rid)
            continue
        actual = results[rid]
        valid = [h["no"] for h in data["horses"] if h["no"] in actual]
        if len(valid) < 2:
            skipped.append(rid)
            continue
        corpus.append({"race_id": rid, "data": data, "report": rpt,
                       "actual": actual, "valid_nos": valid})
    return corpus, skipped


# === 採点 ===

def score_engine(corpus, params_override=None):
    """コーパス全体をエンジン再生し、レース別＋集計の指標を返す。"""
    per_race = []
    briers_w, briers_p, briers_base = [], [], []
    loglosses = []
    top1_win = top1_place = 0
    rhos, overlaps = [], []
    for race in corpus:
        data = dict(race["data"])
        if params_override:
            data["params"] = dict(params_override)
        result = score_race.compute(data)
        wp = {h["no"]: h["win_prob"] for h in result["horses"]}
        pp = {h["no"]: h["place_prob"] for h in result["horses"]}
        actual = race["actual"]
        nos = [n for n in race["valid_nos"] if n in wp]
        n_run = len(actual)

        for no in nos:
            won = 1 if actual[no] == 1 else 0
            placed = 1 if actual[no] <= 3 else 0
            briers_w.append((wp[no] - won) ** 2)
            briers_p.append((pp[no] - placed) ** 2)
            briers_base.append((1.0 / n_run - won) ** 2)

        winner = next((n for n in nos if actual[n] == 1), None)
        ll = -math.log(max(wp[winner], EPS)) if winner is not None else None
        if ll is not None:
            loglosses.append(ll)

        top1 = max(nos, key=lambda n: wp[n])
        if actual[top1] == 1:
            top1_win += 1
        if actual[top1] <= 3:
            top1_place += 1

        pred_rank = {n: -wp[n] for n in nos}  # win_prob 降順=順位昇順
        rho, ov = order_metrics(pred_rank, actual, nos)
        if rho is not None:
            rhos.append(rho)
        if ov is not None:
            overlaps.append(ov)

        per_race.append({"race_id": race["race_id"], "n": n_run,
                         "rho": None if rho is None else round(rho, 3),
                         "top1_no": top1, "top1_pos": actual[top1],
                         "logloss": None if ll is None else round(ll, 3),
                         "winner_prob": None if winner is None else round(wp[winner], 4)})

    n = len(corpus)
    bw = sum(briers_w) / len(briers_w) if briers_w else None
    bb = sum(briers_base) / len(briers_base) if briers_base else None
    agg = {
        "races": n, "starts": len(briers_w),
        "brier_win": round(bw, 5) if bw is not None else None,
        "brier_place": round(sum(briers_p) / len(briers_p), 5) if briers_p else None,
        "brier_baseline": round(bb, 5) if bb is not None else None,
        "skill_win": round(1 - bw / bb, 4) if bw is not None and bb else None,
        "logloss_win": round(sum(loglosses) / len(loglosses), 4) if loglosses else None,
        "spearman_mean": round(sum(rhos) / len(rhos), 4) if rhos else None,
        "top1_win_rate": round(top1_win / n, 3) if n else None,
        "top1_place_rate": round(top1_place / n, 3) if n else None,
        "top3_overlap_mean": round(sum(overlaps) / len(overlaps), 4) if overlaps else None,
    }
    return {"aggregate": agg, "per_race": per_race}


def score_logic(corpus):
    """記録済みの論理並び(rank_order・◎)を同じ指標で採点（パラメータ非依存の参照値）。"""
    per_race = []
    rhos, overlaps = [], []
    hon_win = hon_place = hon_total = 0
    for race in corpus:
        rank = race["report"].get("rank", []) or []
        actual = race["actual"]
        order_of = {r.get("no"): r.get("rank_order") for r in rank
                    if isinstance(r.get("no"), int) and isinstance(r.get("rank_order"), int)}
        nos = [n for n in race["valid_nos"] if n in order_of]
        rho = ov = None
        if len(nos) >= 2:
            rho, ov = order_metrics(order_of, actual, nos)
            if rho is not None:
                rhos.append(rho)
            if ov is not None:
                overlaps.append(ov)
        hon = next((r.get("no") for r in rank if r.get("mark") == "◎"), None)
        hon_pos = actual.get(hon)
        if isinstance(hon_pos, int):
            hon_total += 1
            if hon_pos == 1:
                hon_win += 1
            if hon_pos <= 3:
                hon_place += 1
        per_race.append({"race_id": race["race_id"],
                         "rho": None if rho is None else round(rho, 3),
                         "hon_no": hon, "hon_pos": hon_pos})
    agg = {
        "spearman_mean": round(sum(rhos) / len(rhos), 4) if rhos else None,
        "hon_races": hon_total,
        "hon_win_rate": round(hon_win / hon_total, 3) if hon_total else None,
        "hon_place_rate": round(hon_place / hon_total, 3) if hon_total else None,
        "top3_overlap_mean": round(sum(overlaps) / len(overlaps), 4) if overlaps else None,
    }
    return {"aggregate": agg, "per_race": per_race}


# === 出力 ===

def human_report(out):
    lines = []
    eng = out["engine_baseline"]["aggregate"]
    var = out.get("engine_variant")
    logic = out["logic"]["aggregate"]
    lines.append(f"# バックテスト（{eng['races']}レース・{eng['starts']}頭出走・複勝=top3事象固定）")
    if out["skipped"]:
        lines.append(f"⚠ 突合不能で除外: {', '.join(out['skipped'])}")
    lines.append("")

    logic_pr = {r["race_id"]: r for r in out["logic"]["per_race"]}
    lines.append(f"{'race_id':<24} {'n':>3} {'eng_ρ':>6} {'logic_ρ':>7} {'top1着':>6} {'◎着':>4} {'logloss':>8}")
    for r in out["engine_baseline"]["per_race"]:
        lg = logic_pr.get(r["race_id"], {})
        f = lambda v, w: f"{v:>{w}}" if v is not None else " " * (w - 1) + "-"
        lines.append(f"{r['race_id']:<24} {r['n']:>3} {f(r['rho'],6)} {f(lg.get('rho'),7)} "
                     f"{f(r['top1_pos'],6)} {f(lg.get('hon_pos'),4)} {f(r['logloss'],8)}")
    lines.append("")

    def agg_rows(a):
        return [("Brier(win)", a["brier_win"]), ("Brier(place)", a["brier_place"]),
                ("Brier基準(1/n)", a["brier_baseline"]), ("Skill(win)", a["skill_win"]),
                ("logloss(win)", a["logloss_win"]), ("Spearman平均", a["spearman_mean"]),
                ("top1単勝率", a["top1_win_rate"]), ("top1複勝率", a["top1_place_rate"]),
                ("top3重なり", a["top3_overlap_mean"])]

    if var:
        lines.append(f"## A/B（現行 vs 上書き {out['params_override']}）")
        lines.append(f"{'指標':<16} {'現行':>10} {'上書き':>10} {'Δ':>9}")
        for (k, b), (_, v) in zip(agg_rows(eng), agg_rows(var["aggregate"])):
            if b is None or v is None:
                continue
            lines.append(f"{k:<16} {b:>10.4f} {v:>10.4f} {v - b:>+9.4f}")
        lines.append("（Brier/logloss は小さいほど良い・Skill/ρ/的中率は大きいほど良い）")
    else:
        lines.append("## 集計（エンジン・現行PARAMS）")
        for k, v in agg_rows(eng):
            if v is not None:
                lines.append(f"  {k:<16} {v:.4f}")

    lines.append("")
    lines.append("## 参考: 論理の並び（記録時ログ・パラメータ非依存＝再生不能）")
    lines.append(f"  Spearman平均     {logic['spearman_mean']}")
    lines.append(f"  ◎単勝率          {logic['hon_win_rate']}（{logic['hon_races']}レース）")
    lines.append(f"  ◎複勝率          {logic['hon_place_rate']}")
    lines.append(f"  top3重なり       {logic['top3_overlap_mean']}")
    return "\n".join(lines)


# === self-check（データ不要・指標関数の健全性） ===

def self_check():
    errs = []
    if spearman([1, 2, 3], [1, 2, 3]) != 1.0:
        errs.append("spearman 完全一致≠1")
    if spearman([1, 2, 3], [3, 2, 1]) != -1.0:
        errs.append("spearman 完全逆転≠-1")
    if spearman([1, 1, 1], [1, 2, 3]) is not None:
        errs.append("spearman 分散0がNoneでない")
    if avg_ranks([10, 20, 20, 30]) != [1.0, 2.5, 2.5, 4.0]:
        errs.append("avg_ranks 同値平均が不正")
    # 合成レースを end-to-end（compute→採点）で通す
    data = {"race_id": "selfcheck",
            "horses": [
                {"no": 1, "name": "A", "style": "逃", "ten_speed": "速",
                 "scores": {"A": 2, "B": 2}, "conf": {}},
                {"no": 2, "name": "B", "style": "差", "ten_speed": "中",
                 "scores": {"A": 0, "B": 0}, "conf": {}},
                {"no": 3, "name": "C", "style": "追", "ten_speed": "遅",
                 "scores": {"A": -2, "B": -2}, "conf": {}}],
            "patterns": [{"id": "P1", "prob": 1.0, "pace_level": 0.2}]}
    corpus = [{"race_id": "selfcheck", "data": data,
               "report": {"rank": [{"no": 1, "rank_order": 1, "mark": "◎"},
                                    {"no": 2, "rank_order": 2, "mark": "◯"},
                                    {"no": 3, "rank_order": 3, "mark": "▲"}]},
               "actual": {1: 1, 2: 2, 3: 3}, "valid_nos": [1, 2, 3]}]
    eng = score_engine(corpus)
    a = eng["aggregate"]
    if a["races"] != 1 or a["starts"] != 3:
        errs.append("score_engine 件数不正")
    if not (0 <= a["brier_win"] <= 1):
        errs.append("brier_win 範囲外")
    if a["logloss_win"] is None or a["logloss_win"] < 0:
        errs.append("logloss 不正")
    # スロー(L=0.2)で高スコア逃げ馬が1着の合成例＝ρは正のはず
    if a["spearman_mean"] is None or a["spearman_mean"] <= 0:
        errs.append(f"合成レースのρが非正: {a['spearman_mean']}")
    lg = score_logic(corpus)["aggregate"]
    if lg["spearman_mean"] != 1.0 or lg["hon_win_rate"] != 1.0:
        errs.append("score_logic 完全的中例の採点不正")
    # A/B: T を大きくすると確率が平坦化＝的中1着馬の logloss は増えるはず
    eng_hiT = score_engine(corpus, {"T": 5.0})
    if eng_hiT["aggregate"]["logloss_win"] <= a["logloss_win"]:
        errs.append("T上書きが効いていない")
    return errs


def parse_set(pairs):
    override = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--set は KEY=VALUE 形式: {p}")
        k, v = p.split("=", 1)
        if k not in score_race.PARAMS:
            raise SystemExit(f"未知のパラメータ: {k}（有効: {', '.join(score_race.PARAMS)}）")
        override[k] = float(v)
    return override


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", default=[],
                    help="PARAMS 上書き KEY=VALUE（複数可）→ 現行とのA/B比較")
    ap.add_argument("--races", default=None, help="カンマ区切りの race_id で絞り込み")
    ap.add_argument("--since", default=None, help="YYYYMMDD 以降のレースのみ")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        errs = self_check()
        if errs:
            print("SELF-CHECK FAIL: " + "; ".join(errs), file=sys.stderr)
            return 1
        print("SELF-CHECK OK")
        return 0

    override = parse_set(args.set)
    race_filter = set(args.races.split(",")) if args.races else None
    corpus, skipped = load_corpus(race_filter, args.since)
    if not corpus:
        print("突合できるレースが0件", file=sys.stderr)
        return 1

    out = {"params_override": override or None,
           "skipped": skipped,
           "engine_baseline": score_engine(corpus),
           "engine_variant": score_engine(corpus, override) if override else None,
           "logic": score_logic(corpus)}

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(human_report(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
