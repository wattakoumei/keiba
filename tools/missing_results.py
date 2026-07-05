#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""missing_results.py — 改善ループのデータ欠落を一覧する決定論ゲート。

何をするか:
  data/races/*/ と data/results.jsonl を突合し、改善ループを回すのに足りないものを列挙する:
    1. result_missing   — 予測済み（report.json＋research有）なのに確定結果が未記録
    2. review_missing   — 結果はあるのに展開採点（pace_review）が無い
    3. missclass_missing— 結果はあるのに着順採点（miss_class）が無い
    4. pace_unlabeled   — 結果はあるのに実効ペース復元（label_reconstructed）が null
    5. payout_missing   — 結果はあるのに払戻（record:"payout"）が未記録（I1-R・箱ROI検証の素）

なぜコード化するか:
  結果記録の漏れは較正コーパスを痩せさせる（26件バックフィルの反省＝1ヶ月で25件溜め込んだ）。
  「何が欠けているか」を毎回目視で数えない。/backfill-results の STEP1。

使い方:
  python3 tools/missing_results.py           # 人間可読の欠落一覧
  python3 tools/missing_results.py --json    # 構造化（バックフィル spawn の入力）
  python3 tools/missing_results.py --self-check
"""
import sys, os, json, glob, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def scan(races_dir, results_path):
    have_result, have_review, have_missclass, unlabeled = set(), set(), set(), set()
    have_payout = set()
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                rid = d.get("race_id")
                if not rid:
                    continue
                if "finish" in d:
                    have_result.add(rid)
                    if not (d.get("pace_actual") or {}).get("label_reconstructed"):
                        unlabeled.add(rid)
                if d.get("record") == "pace_review":
                    have_review.add(rid)
                if "miss_class" in d:
                    have_missclass.add(rid)
                if d.get("record") == "payout":
                    have_payout.add(rid)

    predicted = set()
    for rd in sorted(glob.glob(os.path.join(races_dir, "*"))):
        rid = os.path.basename(rd)
        if (os.path.exists(os.path.join(rd, "report.json"))
                and glob.glob(os.path.join(rd, "research-*.json"))):
            predicted.add(rid)

    return {
        "result_missing": sorted(predicted - have_result),
        "review_missing": sorted(have_result - have_review),
        "missclass_missing": sorted(have_result - have_missclass),
        "pace_unlabeled": sorted(unlabeled),
        "payout_missing": sorted(have_result - have_payout),
        "counts": {"predicted": len(predicted), "with_result": len(have_result),
                   "with_review": len(have_review), "with_missclass": len(have_missclass),
                   "with_payout": len(have_payout)},
    }


LABELS = {
    "result_missing": "確定結果が未記録（→ /backfill-results で収集）",
    "review_missing": "展開採点 pace_review が無い（→ /review-prediction）",
    "missclass_missing": "着順採点 miss_class が無い（→ /review-prediction）",
    "pace_unlabeled": "実効ペース未復元 label_reconstructed=null（→ /review-prediction STEP1）",
    "payout_missing": "払戻が未記録（→ fetch_result.py payout / paste-payout。I1-R）",
}


def human(rep):
    c = rep["counts"]
    lines = [f"# データ欠落一覧（予測済み {c['predicted']} / 結果あり {c['with_result']} / "
             f"展開採点 {c['with_review']} / 着順採点 {c['with_missclass']}）", ""]
    for key, label in LABELS.items():
        ids = rep[key]
        lines.append(f"## {label}: {len(ids)}件")
        for rid in ids:
            lines.append(f"  {rid}")
        lines.append("")
    if not any(rep[k] for k in LABELS):
        lines.append("欠落なし＝改善ループのデータは全て揃っている")
    return "\n".join(lines)


def self_check():
    import tempfile
    errs = []
    with tempfile.TemporaryDirectory() as td:
        races = os.path.join(td, "races")
        # r1=予測済み+結果+採点済 / r2=予測済みのみ / r3=結果のみ(採点なし・ペース未復元)
        for rid in ("r1", "r2", "r3"):
            os.makedirs(os.path.join(races, rid))
        for rid in ("r1", "r2"):
            open(os.path.join(races, rid, "report.json"), "w").write("{}")
            open(os.path.join(races, rid, "research-a.json"), "w").write("{}")
        res = os.path.join(td, "results.jsonl")
        with open(res, "w") as f:
            f.write(json.dumps({"race_id": "r1", "finish": [],
                                "pace_actual": {"label_reconstructed": "M"}}) + "\n")
            f.write(json.dumps({"record": "pace_review", "race_id": "r1"}) + "\n")
            f.write(json.dumps({"race_id": "r1", "miss_class": []}) + "\n")
            f.write(json.dumps({"record": "payout", "race_id": "r1", "payouts": {}}) + "\n")
            f.write(json.dumps({"race_id": "r3", "finish": [],
                                "pace_actual": {"label_reconstructed": None}}) + "\n")
        rep = scan(races, res)
        if rep["payout_missing"] != ["r3"]:
            errs.append(f"payout_missing 不正: {rep['payout_missing']}")
        if rep["result_missing"] != ["r2"]:
            errs.append(f"result_missing 不正: {rep['result_missing']}")
        if rep["review_missing"] != ["r3"]:
            errs.append(f"review_missing 不正: {rep['review_missing']}")
        if rep["missclass_missing"] != ["r3"]:
            errs.append(f"missclass_missing 不正: {rep['missclass_missing']}")
        if rep["pace_unlabeled"] != ["r3"]:
            errs.append(f"pace_unlabeled 不正: {rep['pace_unlabeled']}")
    return errs


def main():
    ap = argparse.ArgumentParser()
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
    rep = scan(os.path.join(ROOT, "data", "races"), os.path.join(ROOT, "data", "results.jsonl"))
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else human(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
