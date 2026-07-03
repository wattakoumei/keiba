#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""record_change.py — ハーネス変更台帳（改善と改悪を区別するための効果測定の入口）。

何をするか:
  ノブ・読み筋・ツールの変更を data/changes.jsonl に1行1件で記録し、採用時点のバックテスト
  集計（スナップショット）を一緒に保存する。後日 `compare` で導入後レースに対する効果を測る。

なぜコード化するか:
  変更の導入日と採用時性能が残っていないと、前向き検証（レビュー蓄積）で改善/改悪を判定できない。
  「もっともらしい修正」を無検証で積む＝小標本への過学習を防ぐ台帳。

効果測定の設計（重要）:
  - kind=knob（score_race.PARAMS の数値変更）: 導入後レースだけを使い、現行コード(=新値) vs
    旧値上書きの**反実仮想A/B**を同一レース集合で回す＝コーパス難易度差が混ざらない最も公平な比較。
  - kind=rule/tool/data（再生不能な変更）: 導入後コーパスの集計 vs 採用時スナップショットの粗い比較
    のみ（別コーパス比較＝難易度差が混ざる旨を必ず注記）。
  - どちらも導入後レースが10件未満なら「様子見」を明示（最低Nゲート）。

使い方:
  python3 tools/record_change.py add --kind knob --target T --before 0.55 --after 0.75 \
      --desc "26件バックテストとcalibrate_Tの一致でTを緩和"
  python3 tools/record_change.py list
  python3 tools/record_change.py compare chg-0001
  python3 tools/record_change.py --self-check

規律: 台帳は追記のみ（既存行を書き換えない）。市場データ不使用（I1）。
"""
import sys, os, json, argparse, subprocess, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import score_race
import backtest

REGISTRY = os.path.join(ROOT, "data", "changes.jsonl")
MIN_N = 10  # 効果判定の最低レース数


def load_registry(path=REGISTRY):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def next_id(entries):
    mx = 0
    for e in entries:
        try:
            mx = max(mx, int(e["id"].split("-")[1]))
        except (KeyError, IndexError, ValueError):
            pass
    return f"chg-{mx + 1:04d}"


def git_head():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def knob_key(target):
    """target 'T' / 'score_race.PARAMS.T' → PARAMS キー（無効なら None）。"""
    k = target.split(".")[-1]
    return k if k in score_race.PARAMS else None


def cmd_add(args):
    entries = load_registry()
    if args.kind == "knob":
        k = knob_key(args.target)
        if k is None:
            raise SystemExit(f"kind=knob だが target が PARAMS に無い: {args.target}"
                             f"（有効: {', '.join(score_race.PARAMS)}）")
        if args.before is None or args.after is None:
            raise SystemExit("kind=knob は --before/--after 必須（反実仮想A/Bに使う）")
        cur = score_race.PARAMS[k]
        if abs(cur - float(args.after)) > 1e-9:
            print(f"⚠ 現行 PARAMS.{k}={cur} が --after={args.after} と不一致"
                  f"（変更を適用してから add する運用が正）", file=sys.stderr)
    corpus, _ = backtest.load_corpus()
    snap = backtest.score_engine(corpus)["aggregate"] if corpus else None
    entry = {
        "id": next_id(entries),
        "date": datetime.date.today().isoformat(),
        "kind": args.kind,
        "target": args.target,
        "before": args.before,
        "after": args.after,
        "desc": args.desc,
        "commit": git_head(),
        "snapshot": snap,
        "corpus_ids": [r["race_id"] for r in corpus],
    }
    with open(REGISTRY, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"✓ {entry['id']} を記録（{args.kind}: {args.target}・採用時コーパス{len(corpus)}件）")
    if snap:
        print(f"  採用時: Brier(win)={snap['brier_win']} logloss={snap['logloss_win']} "
              f"ρ={snap['spearman_mean']} top1単勝={snap['top1_win_rate']}")
    return 0


def cmd_list(_args):
    entries = load_registry()
    if not entries:
        print("台帳は空")
        return 0
    print(f"{'id':<9} {'date':<11} {'kind':<5} {'target':<24} 変更")
    for e in entries:
        chg = f"{e.get('before')}→{e.get('after')}" if e.get("before") is not None else "-"
        print(f"{e['id']:<9} {e['date']:<11} {e['kind']:<5} {e['target']:<24} {chg}  {e['desc'][:40]}")
    return 0


def _delta_table(base_agg, var_agg, label_a, label_b):
    rows = [("Brier(win)", "brier_win"), ("Brier(place)", "brier_place"),
            ("Skill(win)", "skill_win"), ("logloss(win)", "logloss_win"),
            ("Spearman平均", "spearman_mean"), ("top1単勝率", "top1_win_rate"),
            ("top1複勝率", "top1_place_rate")]
    lines = [f"{'指標':<14} {label_a:>10} {label_b:>10} {'Δ':>9}"]
    for name, key in rows:
        a, b = base_agg.get(key), var_agg.get(key)
        if a is None or b is None:
            continue
        lines.append(f"{name:<14} {a:>10.4f} {b:>10.4f} {b - a:>+9.4f}")
    return "\n".join(lines)


def cmd_compare(args):
    entries = load_registry()
    e = next((x for x in entries if x["id"] == args.id), None)
    if e is None:
        raise SystemExit(f"台帳に無い: {args.id}")
    since = (datetime.date.fromisoformat(e["date"]) + datetime.timedelta(days=1)).strftime("%Y%m%d")
    corpus, _ = backtest.load_corpus(since=since)
    n = len(corpus)
    print(f"# {e['id']} 効果測定（{e['kind']}: {e['target']} {e.get('before')}→{e.get('after')}・導入日 {e['date']}）")
    print(f"導入後コーパス: {n}件（{since} 以降）")
    if n == 0:
        print("→ 導入後レースが0件＝まだ測れない")
        return 0
    gate = f"⚠ {n}件 < 最低N={MIN_N}＝様子見（判定はまだ確定させない）" if n < MIN_N else f"最低N={MIN_N} 充足"

    k = knob_key(e["target"]) if e["kind"] == "knob" else None
    if k and e.get("before") is not None:
        # 反実仮想A/B: 同一の導入後レースで 旧値 vs 現行コード(新値)
        counter = backtest.score_engine(corpus, {k: float(e["before"])})["aggregate"]
        adopted = backtest.score_engine(corpus)["aggregate"]
        print("方式: 反実仮想A/B（同一レース集合・旧値上書き vs 現行）")
        print(_delta_table(counter, adopted, "旧値", "現行"))
        print("（Brier/logloss は小さいほど良い・Skill/ρ/的中率は大きいほど良い）")
    else:
        adopted = backtest.score_engine(corpus)["aggregate"]
        snap = e.get("snapshot") or {}
        print("方式: 粗比較（採用時スナップショット vs 導入後コーパス＝**難易度差が混ざる**参考値）")
        print(_delta_table(snap, adopted, "採用時", "導入後"))
    print(gate)
    return 0


def self_check():
    errs = []
    import tempfile
    with tempfile.NamedTemporaryFile("w+", suffix=".jsonl", delete=False) as tf:
        tmp = tf.name
    try:
        if load_registry(tmp) != []:
            errs.append("空台帳が[]でない")
        e1 = {"id": "chg-0001", "date": "2026-07-01", "kind": "knob", "target": "T",
              "before": "0.55", "after": "0.75", "desc": "test", "snapshot": {"brier_win": 0.1}}
        with open(tmp, "a", encoding="utf-8") as f:
            f.write(json.dumps(e1) + "\n")
        back = load_registry(tmp)
        if len(back) != 1 or back[0]["id"] != "chg-0001":
            errs.append("追記/再読込が不一致")
        if next_id(back) != "chg-0002":
            errs.append(f"next_id 不正: {next_id(back)}")
        if knob_key("score_race.PARAMS.T") != "T" or knob_key("存在しない") is not None:
            errs.append("knob_key 不正")
        t = _delta_table({"brier_win": 0.10, "logloss_win": 2.0},
                         {"brier_win": 0.08, "logloss_win": 1.9}, "a", "b")
        if "-0.0200" not in t:
            errs.append("delta_table のΔ計算不正")
    finally:
        os.unlink(tmp)
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    ap_add = sub.add_parser("add")
    ap_add.add_argument("--kind", required=True, choices=["knob", "rule", "tool", "data"])
    ap_add.add_argument("--target", required=True, help="変更対象（knob は PARAMS キー名）")
    ap_add.add_argument("--before", default=None)
    ap_add.add_argument("--after", default=None)
    ap_add.add_argument("--desc", required=True, help="何を・なぜ変えたか")
    ap_list = sub.add_parser("list")
    ap_cmp = sub.add_parser("compare")
    ap_cmp.add_argument("id")
    args = ap.parse_args()

    if args.self_check:
        errs = self_check()
        if errs:
            print("SELF-CHECK FAIL: " + "; ".join(errs), file=sys.stderr)
            return 1
        print("SELF-CHECK OK")
        return 0
    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "compare":
        return cmd_compare(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
