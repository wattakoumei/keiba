#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""codex_fanout.py — Codex で観点別調査を並列 fan-out する driver（Claude Code の Workflow 相当）。

なぜ:
  Claude Code は analyze-race の STEP3 で 11 観点を Workflow/Task で並列 spawn する。Codex CLI には
  同等の subagent 並列プリミティブが無い＝この driver が「観点ごとに headless `codex exec` を並列起動し
  research-<X>.json を書かせる」ことで fan-out を忠実移植する。壁時計は逐次でなく最遅観点で決まる。

何をするか:
  各観点 X について prompt を組む: .codex/agents/obs-<id>.toml の developer_instructions
  ＋ 共通鉄則(research-protocol.md) ＋ spawn データ(seed.json・出走表.md・出力スキーマ) を連結し、
  `codex exec` に渡す。各 exec は data/races/<id>/research-<X>.json を書くよう指示される。
  すべての exec を ThreadPool で並列実行し、生成された research-*.json の有無で成否を集計する。

Codex CLI 依存の注意:
  実際の `codex exec` フラグは版で変わる。呼び出しは CMD_TEMPLATE（env CODEX_EXEC_TEMPLATE で上書き可）
  で組み立てる＝インストール版に合わせて1箇所だけ直せる。--dry-run で実行せずコマンドを確認できる。

使い方:
  python3 tools/codex_fanout.py <race-id> --dry-run          # 起動する並列コマンドを確認（codex 不要）
  python3 tools/codex_fanout.py <race-id>                     # 実行（要 codex・全観点）
  python3 tools/codex_fanout.py <race-id> --only E,D,B         # 一部観点だけ（速報/再実行）
  python3 tools/codex_fanout.py <race-id> --max-parallel 6     # 同時実行数
  python3 tools/codex_fanout.py --self-check                   # prompt 組み立ての健全性（codex 不要）
"""
import sys, os, glob, json, argparse, subprocess, shlex
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, ".codex", "agents")
PROTOCOL = os.path.join(ROOT, ".claude", "skills", "analyze-race", "references", "research-protocol.md")

# 観点ID → agent 定義 basename（SKILL.md の AGENT_OF と一致させる。正本はあちら）
# M=新馬モード専用・N=NARモード専用（既定 fan-out には入らない＝--only で明示指定）
AGENT_OF = {"A": "obs-a-index", "B": "obs-b-recent", "C": "obs-c-pedigree", "D": "obs-d-aptitude",
            "E": "obs-e-pace", "F": "obs-f-training", "G": "obs-g-rotation", "H": "obs-h-paddock",
            "I": "obs-i-risk", "K": "obs-k-jockey", "L": "obs-l-repeater",
            "M": "obs-m-debut", "N": "obs-n-class"}
DEFAULT_OBS = "ABCDEFGHIKL"   # 既定 fan-out（通常レース11観点）。新馬/NAR はモード側が --only で選ぶ

# codex 実行コマンドのテンプレート（env で上書き可）。{prompt_file} を読ませて非対話実行する想定。
# インストール版に合わせて調整する1箇所（既定は `codex exec` にプロンプトを渡す形）。
CMD_TEMPLATE = os.environ.get(
    "CODEX_EXEC_TEMPLATE",
    'codex exec --cd {root} --skip-git-repo-check "$(cat {prompt_file})"')
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")


def load_agent_instruction(obs_id):
    """.codex/agents/obs-*.toml の developer_instructions を取り出す（tomllib）。"""
    path = os.path.join(AGENTS_DIR, AGENT_OF[obs_id] + ".toml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"観点 {obs_id} の Codex 定義が無い: {path}（gen_codex_agents.py 未実行?）")
    try:
        import tomllib
        d = tomllib.load(open(path, "rb"))
        return d.get("developer_instructions", "")
    except ModuleNotFoundError:
        # tomllib(3.11+) が無い環境: developer_instructions の literal ブロックを素朴抽出
        text = open(path, encoding="utf-8").read()
        marker = "developer_instructions = "
        i = text.find(marker)
        body = text[i + len(marker):].lstrip()
        quote = body[:3]
        if quote in ("'''", '"""'):
            return body[3:body.index(quote, 3)].strip()
        return body


def build_prompt(race_id, obs_id, race_dir):
    """1観点ぶんの codex プロンプトを組む＝agent指示＋共通鉄則＋spawnデータ＋書き出し先。"""
    instr = load_agent_instruction(obs_id)
    protocol = open(PROTOCOL, encoding="utf-8").read() if os.path.exists(PROTOCOL) else ""
    seed_path = os.path.join(race_dir, "seed.json")
    card_path = os.path.join(race_dir, "出走表.md")
    seed = open(seed_path, encoding="utf-8").read() if os.path.exists(seed_path) else "(seed.json 無し)"
    card = open(card_path, encoding="utf-8").read() if os.path.exists(card_path) else "(出走表.md 無し)"
    out_rel = os.path.join("data", "races", race_id, f"research-{obs_id}.json")
    return (
        f"# 観点 {obs_id} 専属調査（race_id={race_id}）\n\n"
        f"あなたは競馬予想ハーネスの観点 {obs_id} 専属の収集員。以下の指示に厳密に従い、"
        f"web 調査の結果を **{out_rel} に JSON で書き出して終了**する（他のファイルは触らない）。\n\n"
        f"## 専属指示（この観点の役割・手順・スコア指針）\n{instr}\n\n"
        f"## 全観点共通の規律・推奨ソース・出力スキーマ\n{protocol}\n\n"
        f"## レースの核データ（出走表）\n```\n{card}\n```\n\n"
        f"## スクレイパ seed（脚質/テン速/近走/血統など。再調査せずここを起点に）\n```json\n{seed}\n```\n\n"
        f"## 厳守\n"
        f"- 市場（オッズ・人気・他人の予想）は証拠にもログにも使わない（I1）。\n"
        f"- 出力は {out_rel} の1ファイルのみ。スキーマは上記『出力スキーマ』に従う（E は PACE_EVIDENCE_SCHEMA）。\n"
    )


def cmd_for(prompt_file):
    return CMD_TEMPLATE.format(root=shlex.quote(ROOT), prompt_file=shlex.quote(prompt_file))


def run_one(race_id, obs_id, race_dir, scratch, dry_run):
    prompt = build_prompt(race_id, obs_id, race_dir)
    pf = os.path.join(scratch, f"prompt-{obs_id}.md")
    open(pf, "w", encoding="utf-8").write(prompt)
    cmd = cmd_for(pf)
    out_path = os.path.join(race_dir, f"research-{obs_id}.json")
    if dry_run:
        return {"obs": obs_id, "cmd": cmd, "prompt_chars": len(prompt), "status": "dry"}
    before = os.path.exists(out_path)
    try:
        r = subprocess.run(["/bin/sh", "-c", cmd], cwd=ROOT, capture_output=True,
                           text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return {"obs": obs_id, "status": "timeout"}
    wrote = os.path.exists(out_path) and (not before or os.path.getsize(out_path) > 0)
    valid = False
    if wrote:
        try:
            json.load(open(out_path, encoding="utf-8"))
            valid = True
        except Exception:
            valid = False
    return {"obs": obs_id, "status": "ok" if valid else "fail",
            "rc": r.returncode, "wrote": wrote, "valid_json": valid,
            "stderr_tail": (r.stderr or "")[-300:]}


def fanout(race_id, only, max_parallel, dry_run):
    race_dir = os.path.join(ROOT, "data", "races", race_id)
    if not os.path.isdir(race_dir):
        raise SystemExit(f"レースディレクトリが無い: {race_dir}")
    obs_ids = [x.strip().upper() for x in only.split(",")] if only else list(DEFAULT_OBS)
    for x in obs_ids:
        if x not in AGENT_OF:
            raise SystemExit(f"未知の観点: {x}（有効: {', '.join(AGENT_OF)}）")
    scratch = os.path.join(race_dir, ".codex_prompts")
    os.makedirs(scratch, exist_ok=True)

    results = []
    with ThreadPoolExecutor(max_workers=max_parallel) as ex:
        futs = {ex.submit(run_one, race_id, x, race_dir, scratch, dry_run): x for x in obs_ids}
        for f in as_completed(futs):
            results.append(f.result())
    return sorted(results, key=lambda r: r["obs"])


def self_check():
    errs = []
    if set(AGENT_OF) != set("ABCDEFGHIKLMN"):
        errs.append("AGENT_OF の観点集合が13観点(A-I,K,L,M,N)と不一致")
    if set(DEFAULT_OBS) != set("ABCDEFGHIKL"):
        errs.append("DEFAULT_OBS（既定 fan-out）が通常11観点(A-I,K,L)と不一致")
    # 生成済み toml があれば prompt 組み立てを1観点で試す
    sample = os.path.join(AGENTS_DIR, "obs-e-pace.toml")
    if os.path.exists(sample):
        instr = load_agent_instruction("E")
        if "展開証拠" not in instr and "E " not in instr:
            errs.append("load_agent_instruction が本文を取れていない")
        c = cmd_for("/tmp/p.md")
        if "{prompt_file}" in c or "{root}" in c:
            errs.append("CMD_TEMPLATE の置換が未解決")
    else:
        errs.append("obs-e-pace.toml が無い（先に gen_codex_agents.py）")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("race_id", nargs="?")
    ap.add_argument("--only", default=None, help="観点をカンマ区切りで限定（例 E,D,B）")
    ap.add_argument("--max-parallel", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="実行せず並列コマンドを表示")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        errs = self_check()
        if errs:
            print("SELF-CHECK FAIL: " + "; ".join(errs), file=sys.stderr)
            return 1
        print("SELF-CHECK OK")
        return 0

    if not args.race_id:
        ap.error("race_id が必要")
    results = fanout(args.race_id, args.only, args.max_parallel, args.dry_run)

    if args.dry_run:
        print(f"# fan-out 計画（{len(results)} 観点・同時 {args.max_parallel}・codex 未実行）")
        print(f"# CMD_TEMPLATE = {CMD_TEMPLATE}")
        for r in results:
            print(f"[{r['obs']}] prompt {r['prompt_chars']}字\n    {r['cmd']}")
        return 0

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"# fan-out 完了: {ok}/{len(results)} 観点で research-*.json 生成")
    for r in results:
        mark = "✓" if r["status"] == "ok" else "✗"
        print(f"  {mark} {r['obs']}: {r['status']}"
              + (f" (rc={r.get('rc')})" if r["status"] != "ok" else ""))
        if r["status"] != "ok" and r.get("stderr_tail"):
            print(f"      {r['stderr_tail'].strip()}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
