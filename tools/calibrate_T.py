#!/usr/bin/env python3
"""calibrate_T.py — softmax温度Tの較正スクリプト。

report.json（観点スコア＋展開パターン）と results.jsonl（実着順）を突合し、
Tを走査して Brier Score が最小になる値を探す。

使い方:
  python3 tools/calibrate_T.py                    # 全レース突合＋較正表
  python3 tools/calibrate_T.py --json             # 構造化出力
  python3 tools/calibrate_T.py --apply            # 最適Tを score_race.py に書き込み（要確認）
"""
import sys, os, json, glob, argparse, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import score_race
import inject_probs


def load_results():
    path = os.path.join(ROOT, "data", "results.jsonl")
    results = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "finish" not in r:
                continue
            rid = r["race_id"]
            results[rid] = {
                h["no"]: h["pos"]
                for h in r["finish"]
                if isinstance(h.get("pos"), int)
            }
    return results


def build_race_input(race_dir):
    rpt_path = os.path.join(race_dir, "report.json")
    if not os.path.exists(rpt_path):
        return None, None
    rpt = json.load(open(rpt_path, encoding="utf-8"))

    scores, conf = inject_probs.load_research_scores(race_dir)
    if not scores:
        return None, None

    seed_path = os.path.join(race_dir, "seed.json")
    seed = json.load(open(seed_path, encoding="utf-8")) if os.path.exists(seed_path) else None

    data = inject_probs.build_input(rpt, scores, conf, seed)
    if not data.get("patterns"):
        return None, None
    return data, rpt


def brier(predicted, actual_flag):
    return (predicted - actual_flag) ** 2


def run_calibration(t_values=None):
    if t_values is None:
        t_values = [round(0.25 + i * 0.05, 2) for i in range(26)]  # 0.25〜1.50

    results = load_results()
    races_dir = os.path.join(ROOT, "data", "races")

    matched = []
    for d in sorted(os.listdir(races_dir)):
        if d not in results:
            continue
        rd = os.path.join(races_dir, d)
        data, rpt = build_race_input(rd)
        if data is None:
            continue
        actual = results[d]
        valid_nos = [h["no"] for h in data["horses"] if h["no"] in actual]
        if not valid_nos:
            continue
        matched.append({"race_id": d, "data": data, "actual": actual, "valid_nos": valid_nos,
                         "n_runners": len(actual)})

    if not matched:
        return None

    current_T = score_race.PARAMS["T"]

    scan = []
    for T in t_values:
        brier_win_all = []
        brier_place_all = []
        baseline_all = []
        top_wins = 0
        top_places = 0
        total = 0

        for race in matched:
            data = dict(race["data"])
            data["params"] = {"T": T}
            result = score_race.compute(data)

            wp_map = {h["no"]: h["win_prob"] for h in result["horses"]}
            pp_map = {h["no"]: h["place_prob"] for h in result["horses"]}

            top_no = max(race["valid_nos"], key=lambda n: wp_map.get(n, 0))
            pos = race["actual"].get(top_no)
            if pos == 1:
                top_wins += 1
            if isinstance(pos, int) and pos <= 3:
                top_places += 1
            total += 1

            n = race["n_runners"]
            for no in race["valid_nos"]:
                wp = wp_map.get(no, 0)
                pp = pp_map.get(no, 0)
                pos = race["actual"][no]
                won = 1 if pos == 1 else 0
                placed = 1 if pos <= 3 else 0
                brier_win_all.append(brier(wp, won))
                brier_place_all.append(brier(pp, placed))
                baseline_all.append(brier(1.0 / n, won))

        bw = sum(brier_win_all) / len(brier_win_all)
        bp = sum(brier_place_all) / len(brier_place_all)
        bl = sum(baseline_all) / len(baseline_all)
        skill = 1 - bw / bl if bl > 0 else 0

        scan.append({
            "T": T, "brier_win": round(bw, 5), "brier_place": round(bp, 5),
            "baseline": round(bl, 5), "skill": round(skill, 4),
            "top_win_rate": round(top_wins / total, 3) if total else 0,
            "top_place_rate": round(top_places / total, 3) if total else 0,
        })

    best = min(scan, key=lambda s: s["brier_win"])

    return {
        "matched_races": len(matched),
        "horse_starts": sum(len(r["valid_nos"]) for r in matched),
        "race_ids": [r["race_id"] for r in matched],
        "current_T": current_T,
        "best_T": best["T"],
        "best_brier_win": best["brier_win"],
        "best_skill": best["skill"],
        "current_entry": next((s for s in scan if s["T"] == current_T), None),
        "best_entry": best,
        "scan": scan,
        "recommendation": recommend(current_T, best, len(matched)),
    }


def recommend(current_T, best, n_races):
    gap = abs(best["T"] - current_T)
    if n_races < 5:
        return {"action": "様子見", "reason": f"突合レース{n_races}件＝データ不足（5件以上で判定）"}
    if gap < 0.03:
        return {"action": "維持", "reason": f"現行T={current_T}と最適T={best['T']}の差が{gap:.2f}＝許容範囲"}
    if best["skill"] < 0:
        return {"action": "要検討", "reason": f"最適T={best['T']}でもskill={best['skill']:.3f}<0＝モデル自体の改善が先"}
    return {"action": "変更推奨", "reason": f"現行T={current_T}→{best['T']}でBrier skill {best['skill']:+.3f}",
            "new_T": best["T"]}


def apply_T(new_T):
    path = os.path.join(ROOT, "tools", "score_race.py")
    with open(path, encoding="utf-8") as f:
        code = f.read()
    code = re.sub(
        r'("T":\s*)[\d.]+',
        f'\\g<1>{new_T}',
        code, count=1,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    return path


def human_report(cal):
    lines = []
    lines.append(f"# T較正レポート（{cal['matched_races']}レース・{cal['horse_starts']}頭出走）")
    lines.append(f"突合レース: {', '.join(cal['race_ids'])}")
    lines.append("")
    lines.append(f"{'T':>5} {'Brier(win)':>11} {'Brier(plc)':>11} {'Skill':>8} {'◎単勝':>7} {'◎複勝':>7}")
    for s in cal["scan"]:
        marker = " ◀現行" if s["T"] == cal["current_T"] else (" ◀最適" if s["T"] == cal["best_T"] else "")
        lines.append(f"{s['T']:5.2f} {s['brier_win']:11.5f} {s['brier_place']:11.5f} "
                      f"{s['skill']:+7.3f} {s['top_win_rate']*100:6.0f}% {s['top_place_rate']*100:6.0f}%{marker}")
    lines.append("")
    rec = cal["recommendation"]
    lines.append(f"判定: {rec['action']}（{rec['reason']}）")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cal = run_calibration()
    if cal is None:
        print("突合できるレースが0件", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(cal, ensure_ascii=False, indent=2))
    else:
        print(human_report(cal))

    if args.apply:
        rec = cal["recommendation"]
        if "new_T" in rec:
            path = apply_T(rec["new_T"])
            print(f"\n✓ {path} の T を {cal['current_T']} → {rec['new_T']} に更新")
            print("※ scoring-model.md のミラー更新は手動で行ってください")
        else:
            print(f"\n変更不要: {rec['reason']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
