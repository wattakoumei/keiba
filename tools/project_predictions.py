#!/usr/bin/env python3
"""report.json → predictions.jsonl 投影器（依存ゼロ）。

report.json（構造化正本）から review-prediction 用の 2 レコードを抽出し
`data/predictions.jsonl` に追記する。手書きしない＝源は report.json 一本（drift 無し）。

  - pace レコード（1レース1行・record:"pace"）  ← pace.patterns[] ＋ meta
  - rank レコード（印持ち馬=mark!="—" のみ・1馬1行・record:"rank"） ← rank[]

使い方:
  python3 tools/project_predictions.py <race-id>            # append（既存があればエラー）
  python3 tools/project_predictions.py <race-id> --update   # 当日更新: note付きで履歴 append
  python3 tools/project_predictions.py <race-id> --dry-run  # 追記せず標準出力に表示
  python3 tools/project_predictions.py <race-id> --check    # 既存 jsonl と差分照合（追記しない）

終了コード: 0=成功 / 1=エラー。
"""
import sys, os, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRED = os.path.join(ROOT, "data", "predictions.jsonl")

# pace レコードに載せる pattern フィールド（順序＝可読性。tier→likelihood_tier に改名）
PATTERN_KEYS = ["id", "name", "trigger", "pace_level", "contesters", "leg_advantage",
                "formation_head", "formation_last_corner", "bias", "phase_flow", "prob"]


def build_pace(d):
    pats = []
    for p in d["pace"]["patterns"]:
        rec = {"id": p.get("id"), "name": p.get("name"),
               "likelihood_tier": p.get("tier")}
        for k in PATTERN_KEYS[2:]:
            if k in p:
                rec[k] = p[k]
        pats.append(rec)
    return {
        "record": "pace",
        "race_id": d["race_id"],
        "race_name": d.get("race_name"),
        "date": d.get("date"),
        "model_version": d.get("model_version"),
        "patterns": pats,
        "pace_factors": d["pace"].get("pace_factors", []),  # 展開トリガー早見（来そうな展開の判断材料）
        "falsification": d["pace"].get("counter_conditions", ""),
        "note": "",
    }


def build_ranks(d):
    out = []
    for r in d["rank"]:
        if r.get("mark") == "—":           # 印持ちのみ投影（従来挙動）
            continue
        out.append({
            "record": "rank",
            "race_id": d["race_id"],
            "date": d.get("date"),
            "model_version": d.get("model_version"),
            "horse_no": r.get("no"),
            "horse": r.get("horse"),
            "trainer": r.get("trainer"),
            "mark": r.get("mark"),
            "rank_order": r.get("rank_order"),
            "intent": r.get("intent", "→"),
            "pattern_fit": r.get("pattern_fit", {}),
            "pace_sensitivity": r.get("pace_sensitivity", ""),
            "pros": r.get("pros", []),
            "cons": r.get("cons", []),
        })
    return out


def load_report(race_id):
    path = os.path.join(ROOT, "data", "races", race_id, "report.json")
    if not os.path.exists(path):
        print(f"見つからない: {path}")
        return None
    return json.load(open(path, encoding="utf-8"))


def existing_for(race_id):
    if not os.path.exists(PRED):
        return []
    out = []
    for l in open(PRED, encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        if r.get("race_id") == race_id:
            out.append(r)
    return out


def emit(records):
    for r in records:
        print(json.dumps(r, ensure_ascii=False))


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    race_id = argv[0]
    flags = set(argv[1:])
    d = load_report(race_id)
    if d is None:
        return 1

    pace = build_pace(d)
    ranks = build_ranks(d)
    records = [pace] + ranks
    print(f"# {race_id}: pace 1 + rank {len(ranks)} = {len(records)} レコード", file=sys.stderr)

    if "--dry-run" in flags:
        emit(records)
        return 0

    if "--check" in flags:
        old = existing_for(race_id)
        old_pace = [r for r in old if r.get("record") == "pace"]
        old_rank = {r.get("horse_no"): r for r in old if r.get("record") == "rank"}
        print(f"既存: pace {len(old_pace)} / rank {len(old_rank)}", file=sys.stderr)
        if not old:
            print("（既存レコード無し＝新規。--check の比較対象なし）")
            return 0
        # rank の note 差分のみ要約（% スクラブ等の I2 改善を可視化）
        for nr in ranks:
            o = old_rank.get(nr["horse_no"])
            if not o:
                print(f"  + 新規 rank: {nr['horse_no']} {nr['horse']}")
                continue
            for fld in ("mark", "rank_order", "intent", "pattern_fit"):
                if o.get(fld) != nr.get(fld):
                    print(f"  ~ {nr['horse']} {fld}: {o.get(fld)!r} → {nr.get(fld)!r}")
            on = [c["note"] for c in o.get("cons", [])]
            nn = [c["note"] for c in nr.get("cons", [])]
            if on != nn:
                diff = [x for x in nn if x not in on]
                if diff:
                    print(f"  ~ {nr['horse']} cons 変更: {diff}")
        return 0

    # --- append モード ---
    existing = existing_for(race_id)
    if existing and "--update" not in flags:
        print(f"✗ {race_id} の既存レコードが {len(existing)} 件あります。"
              f"当日更新なら --update（note付きで履歴追記）、新規投入のみ既存無し時に許可。")
        return 1
    if "--update" in flags:
        for r in records:
            r["note"] = "当日更新"
    with open(PRED, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"✓ {PRED} に {len(records)} レコード追記"
          + ("（当日更新）" if "--update" in flags else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
