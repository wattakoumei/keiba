#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_probs.py — score_race.py の決定論出力(win_prob/place_prob)を report.json の rank[] に注入する。

I8（v5.1）: 単勝率/複勝率は score_race.py が唯一の源＝毎回これを回して rank[].win_prob/place_prob に入れる。
率の入力(観点スコア・脚質・展開パターン)は既存の research-<観点>.json と report.json から機械的に組む
（エージェントの手組みゼロ＝再現可能・手計算の揺れを排除）。**並び(rank_order/mark)は論理が主＝率順に並べ替えない**。

組み立て:
  scores{no:{X:score}} / conf{no:{X:conf}} ← research-<X>.json（ファイル名の X を観点IDに採用＝中身スキーマの揺れに依存しない）
  style                                     ← report.json pace.leg_table[].leg_type（A_early の素。ten/agari/recent は省略=中立フォールバック）
  patterns[{id,prob,pace_level,contesters}] ← report.json pace.patterns[]
  horses(no,name)                           ← report.json rank[]
→ score_race.compute → win_prob/place_prob を no で対応づけ rank[] に round(4) で書き戻し、report.json を上書き保存。

使い方:
  python3 tools/inject_probs.py <race-id>          # 注入して report.json を更新
  python3 tools/inject_probs.py <race-id> --dry    # 書き戻さず率と食い違いをプレビュー
終了コード: 0=OK / 1=エラー（report/research 欠落・pace.patterns 無し）。
"""
import sys, os, json, glob, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_race

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_research_scores(race_dir):
    """research-<X>.json 群から scores{no:{X:score}} と conf{no:{X:conf}} を機械集約。
    観点ID X は**ファイル名**から採る（中身の point/observation_point の揺れに依存しない）。"""
    scores, conf = {}, {}
    for path in sorted(glob.glob(os.path.join(race_dir, "research-*.json"))):
        base = os.path.basename(path)
        X = base[len("research-"):-len(".json")].upper()  # research-A.json -> A
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for h in d.get("horses", []) or []:
            no = h.get("no")
            if not isinstance(no, int) or isinstance(no, bool):
                continue
            s = h.get("score")
            if isinstance(s, (int, float)) and not isinstance(s, bool):
                scores.setdefault(no, {})[X] = s
                c = h.get("confidence")
                if c:
                    conf.setdefault(no, {})[X] = c
    return scores, conf


def build_input(report, scores, conf):
    """report.json + 集約済み scores から score_race の入力 JSON を組む。"""
    pace = report.get("pace", {}) or {}
    style_of = {row.get("no"): row.get("leg_type")
                for row in (pace.get("leg_table") or []) if isinstance(row, dict)}
    horses = []
    for r in report.get("rank", []) or []:
        no = r.get("no")
        if not isinstance(no, int) or isinstance(no, bool):
            continue
        horses.append({
            "no": no,
            "name": r.get("horse", str(no)),
            "style": style_of.get(no),       # ten/agari/recent/draw_adj は省略=score_race が中立(0.5)で扱う
            "scores": scores.get(no, {}),
            "conf": conf.get(no, {}),
        })
    patterns = [{"id": p.get("id"), "prob": p.get("prob", 0.0),
                 "pace_level": p.get("pace_level", 0.5), "contesters": p.get("contesters", [])}
                for p in (pace.get("patterns") or [])]
    return {"race_id": report.get("race_id", ""), "horses": horses, "patterns": patterns}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("race_id")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    race_dir = os.path.join(ROOT, "data", "races", args.race_id)
    report_path = os.path.join(race_dir, "report.json")
    if not os.path.exists(report_path):
        print(f"✗ report.json が無い: {report_path}", file=sys.stderr)
        return 1
    report = json.load(open(report_path, encoding="utf-8"))

    scores, conf = load_research_scores(race_dir)
    if not scores:
        print(f"✗ research-*.json から観点スコアが1件も取れない（{race_dir}）", file=sys.stderr)
        return 1

    data = build_input(report, scores, conf)
    if not data["patterns"]:
        print("✗ pace.patterns が無い＝率を出せない", file=sys.stderr)
        return 1

    result = score_race.compute(data)
    errs = score_race.self_check(data, result)
    if errs:
        print("⚠ self-check: " + "; ".join(errs), file=sys.stderr)

    win = {h["no"]: h["win_prob"] for h in result["horses"]}
    place = {h["no"]: h["place_prob"] for h in result["horses"]}

    rank = report.get("rank", [])
    # 並びとエンジン複勝率順の食い違い（参考＝engine_check の素。論理が主なので並べ替えはしない）
    eng_order = sorted(win, key=lambda n: -place[n])
    logic_order = [r.get("no") for r in sorted(rank, key=lambda r: r.get("rank_order", 999))]
    disagree = sum(1 for i, no in enumerate(logic_order[:len(eng_order)]) if eng_order[i] != no)

    missing = []
    for r in rank:
        no = r.get("no")
        if no in win:
            r["win_prob"] = round(win[no], 4)
            r["place_prob"] = round(place[no], 4)
        else:
            missing.append(no)

    print(f"# {args.race_id}  率注入（源=score_race v{result['model_version']}・並びは論理が主）")
    for r in sorted(rank, key=lambda r: r.get("rank_order", 999)):
        no = r.get("no")
        w, pl = r.get("win_prob"), r.get("place_prob")
        if w is not None:
            print(f"  {r.get('mark',''):<2} {no:>2} {r.get('horse',''):<14} 単勝 {w*100:5.1f}%  複勝 {pl*100:5.1f}%")
        else:
            print(f"     {no:>2} {r.get('horse','')} ← 率なし")
    if missing:
        print(f"⚠ 率を入れられない馬(rankにいるがscore入力に無い): {missing}", file=sys.stderr)
    print(f"# 論理の並び vs エンジン複勝率順: 食い違い {disagree}頭"
          f"（並びは論理が主＝率順に並べ替えない。engine_check の素）")

    if args.dry:
        print("（--dry: 書き戻さない）")
        return 0
    json.dump(report, open(report_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✓ {os.path.relpath(report_path, ROOT)} に win_prob/place_prob を注入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
