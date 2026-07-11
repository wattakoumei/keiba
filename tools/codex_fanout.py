#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""codex_fanout.py — Codex で観点別調査を並列 fan-out する driver（Claude Code の Workflow 相当）。

なぜ:
  Claude Code は analyze-race の STEP3 で観点を Workflow/Task で並列 spawn する。Codex CLI には
  同等の subagent 並列プリミティブが無い＝この driver が「観点ごとに headless `codex exec` を並列起動し
  research-<X>.json を書かせる」ことで fan-out を忠実移植する。壁時計は逐次でなく最遅観点で決まる。

何をするか:
  各観点 X について prompt を組む: .codex/agents/obs-<id>.toml の developer_instructions
  ＋ 共通鉄則(research-protocol.md) ＋ spawn データ を連結し、`codex exec` に渡す。
  spawn データは SKILL.md STEP3 の注入テーブルの**ミラー**（あちらを変えたらここも直す）:
    - 全観点: 出走表.md・seed.json・新馬フラグ(該当時)
    - C: pedigree-catalog.md 該当行（＋新馬時 debut-catalog.md）
    - D/E: course-geometry.md 該当場（NAR は nar-course-geometry.md 全文）
    - F/K: stable-intent-rubric.md／F: oikiri seed(ファイルがあれば)
    - D/I/G: weight_adjust.py 出力（weight.json 優先・無ければ実行）
    - I: risk_flags.py 出力（risk.json 優先・無ければ実行）
    - M: debut-catalog.md（新馬モード専用観点）
    - N: nar-class-ladder.md（NAR 専用観点）
  各 exec は data/races/<id>/research-<X>.json を書くよう指示される。
  すべての exec を ThreadPool で並列実行し、research-*.json が**この実行で新しく書かれたか**で成否を集計する
  （既存ファイルの残存を成功と誤認しない＝mtime 比較）。

モード自動判定（--only 未指定時の既定観点セット）:
  新馬 = 出走表.md に「新馬」「メイクデビュー」（--debut で強制）→ C,E,F,I,K,M
  NAR  = race-id の場トークンが inject_probs.NAR_VENUES（--nar で強制）→ A,B,C,D,E,G,I,K,N
  NAR×新馬 → C,E,F,I,K,M,N ／ 通常 JRA → 11観点 A-I,K,L
  速報モード等は --only で明示する（JRA 速報=A,B,D,E,I／NAR 速報=A,B,D,E,I,N）。

Codex CLI 依存の注意:
  実際の `codex exec` フラグは版で変わる。呼び出しは CMD_TEMPLATE（env CODEX_EXEC_TEMPLATE で上書き可）
  で組み立てる＝インストール版に合わせて1箇所だけ直せる。--dry-run で実行せずコマンドを確認できる。

使い方:
  python3 tools/codex_fanout.py <race-id> --dry-run          # 起動する並列コマンド＋注入量を確認（codex 不要）
  python3 tools/codex_fanout.py <race-id>                     # 実行（要 codex・モード自動判定）
  python3 tools/codex_fanout.py <race-id> --only E,D,B         # 一部観点だけ（速報/再実行）
  python3 tools/codex_fanout.py <race-id> --max-parallel 6     # 同時実行数
  python3 tools/codex_fanout.py --self-check                   # prompt/注入 組み立ての健全性（codex 不要）
"""
import sys, os, glob, json, argparse, subprocess, shlex
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, ".codex", "agents")
REF = os.path.join(ROOT, ".claude", "skills", "analyze-race", "references")
NAR_REF = os.path.join(ROOT, ".claude", "skills", "analyze-race-nar", "references")
PROTOCOL = os.path.join(REF, "research-protocol.md")
COURSE_MD = os.path.join(REF, "course-geometry.md")
PEDIGREE_MD = os.path.join(REF, "pedigree-catalog.md")
STABLE_MD = os.path.join(REF, "stable-intent-rubric.md")
DEBUT_MD = os.path.join(REF, "debut-catalog.md")
NAR_LADDER_MD = os.path.join(NAR_REF, "nar-class-ladder.md")
NAR_COURSE_MD = os.path.join(NAR_REF, "nar-course-geometry.md")

# 観点ID → agent 定義 basename（SKILL.md の AGENT_OF と一致させる。正本はあちら）
AGENT_OF = {"A": "obs-a-index", "B": "obs-b-recent", "C": "obs-c-pedigree", "D": "obs-d-aptitude",
            "E": "obs-e-pace", "F": "obs-f-training", "G": "obs-g-rotation", "H": "obs-h-paddock",
            "I": "obs-i-risk", "K": "obs-k-jockey", "L": "obs-l-repeater",
            "M": "obs-m-debut", "N": "obs-n-class"}

# 場トークン → 漢字（course-geometry の見出し照合用）。NAR の集合は inject_probs.NAR_VENUES が正本。
JRA_KANJI = {"sapporo": "札幌", "hakodate": "函館", "fukushima": "福島", "niigata": "新潟",
             "tokyo": "東京", "nakayama": "中山", "chukyo": "中京", "kyoto": "京都",
             "hanshin": "阪神", "kokura": "小倉"}
NAR_KANJI = {"monbetsu": "門別", "morioka": "盛岡", "mizusawa": "水沢", "urawa": "浦和",
             "funabashi": "船橋", "ooi": "大井", "kawasaki": "川崎", "kanazawa": "金沢",
             "kasamatsu": "笠松", "nagoya": "名古屋", "sonoda": "園田", "himeji": "姫路",
             "kochi": "高知", "saga": "佐賀"}
try:
    from inject_probs import NAR_VENUES  # ワンソース（tools/ から実行される前提）
except Exception:
    NAR_VENUES = set(NAR_KANJI)

# codex 実行コマンドのテンプレート（env で上書き可）。{prompt_file} を読ませて非対話実行する想定。
CMD_TEMPLATE = os.environ.get(
    "CODEX_EXEC_TEMPLATE",
    'codex exec --cd {root} --skip-git-repo-check "$(cat {prompt_file})"')
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")


def _read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def md_section(text, needle):
    """'## ' 見出しに needle を含むセクションを抜く（次の '## ' 手前まで・複数一致は連結）。"""
    out, active = [], False
    for ln in text.splitlines():
        if ln.startswith("## "):
            active = needle in ln
        if active:
            out.append(ln)
    return "\n".join(out).strip()


def _run_tool(argv, timeout=60):
    """tools/*.py を決定論 seed 用に実行（web には出ない）。失敗は空文字＝注入スキップ。"""
    try:
        r = subprocess.run([sys.executable] + argv, cwd=ROOT, capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def course_payload(nar, venue_kanji):
    """D/E へのコース物理形状（I10 ワンソース）。NAR は共通原則込みで全文（~4KB）。"""
    if nar:
        return _read(NAR_COURSE_MD)
    text = _read(COURSE_MD)
    if not text or not venue_kanji:
        return ""
    sec = md_section(text, venue_kanji)
    turf_start = md_section(text, "ダート芝スタート早見")
    return ((turf_start + "\n\n" + sec).strip()) if sec else ""


def pedigree_payload(seed):
    """C への血統カタログ該当行＝seed の父/母父に一致する行＋巻頭原則。カタログ外は明示して web 調査に回す。"""
    text = _read(PEDIGREE_MD)
    if not text:
        return ""
    names = set()
    for h in (seed or {}).get("horses", []):
        for k in ("sire", "damsire"):
            v = (h.get(k) or "").strip()
            if v:
                names.add(v)
    if not names:
        return ""
    hits, missed, seen = [], [], set()
    for n in sorted(names):
        rows = [ln for ln in text.splitlines() if ln.startswith("|") and n in ln]
        if rows:
            for r in rows:
                if r not in seen:
                    seen.add(r)
                    hits.append(r)
        else:
            missed.append(n)
    parts = [md_section(text, "巻頭原則"),
             "### 該当カタログ行（出走馬の父/母父に一致・列構成は原本の表どおり）\n" + "\n".join(hits)]
    if missed:
        parts.append("### カタログ外（web で調査し「追記候補」で報告）: " + "、".join(missed))
    return "\n\n".join(p for p in parts if p).strip()


def build_ctx(race_id, race_dir, force_debut=False, force_nar=False):
    """fan-out 1回ぶんの spawn 注入データを一度だけ組む（SKILL STEP3 のミラー）。"""
    parts = race_id.split("-")
    venue = parts[1].lower() if len(parts) >= 2 else ""
    nar = force_nar or venue in NAR_VENUES
    card = _read(os.path.join(race_dir, "出走表.md"))
    debut = force_debut or ("新馬" in card) or ("メイクデビュー" in card)
    seed_raw = _read(os.path.join(race_dir, "seed.json"))
    try:
        seed = json.loads(seed_raw) if seed_raw else {}
    except Exception:
        seed = {}
    venue_kanji = (NAR_KANJI if nar else JRA_KANJI).get(venue, "")

    weight = _read(os.path.join(race_dir, "weight.json")) or _run_tool(
        ["tools/weight_adjust.py", os.path.join(race_dir, "出走表.md"), "--json"])
    risk = ""
    if seed_raw:
        risk = _read(os.path.join(race_dir, "risk.json")) or _run_tool(
            ["tools/risk_flags.py", os.path.join(race_dir, "seed.json"), "--json",
             "--race-date", race_id[:8]])
    oikiri = ""
    for cand in sorted(glob.glob(os.path.join(race_dir, "oikiri*.json"))):
        oikiri = _read(cand)
        break

    return {"race_id": race_id, "venue": venue, "nar": nar, "debut": debut,
            "card": card, "seed_raw": seed_raw,
            "course": course_payload(nar, venue_kanji),
            "pedigree": pedigree_payload(seed),
            "stable": _read(STABLE_MD),
            "debut_catalog": _read(DEBUT_MD) if debut else "",
            "nar_ladder": _read(NAR_LADDER_MD) if nar else "",
            "weight": weight, "risk": risk, "oikiri": oikiri}


def default_obs(nar, debut):
    """--only 未指定時の観点セット（SKILL STEP2／NAR SKILL 差分2 とミラー）。"""
    if nar and debut:
        return list("CEFIKMN")
    if nar:
        return list("ABCDEGIKN")   # A,B,C,D,E,G,I,K,N（F/H/L は情報の厚いレースだけ --only で足す）
    if debut:
        return list("CEFIKM")
    return list("ABCDEFGHIKL")


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


def _injections(obs_id, ctx):
    """観点別の spawn 注入ブロック（SKILL STEP3 の注入テーブルのミラー＝あちらを変えたらここも直す）。"""
    blk = []
    if ctx["debut"]:
        blk.append("# 新馬戦（過去走なし）\nあなたの指示内の「新馬戦モード」節に従うこと。")
    if obs_id == "C" and ctx["pedigree"]:
        blk.append("# 血統カタログ該当行（pedigree-catalog.md・カタログ内は再調査しない）\n" + ctx["pedigree"])
    if ctx["debut"] and obs_id in ("M", "C") and ctx["debut_catalog"]:
        note = "①厩舎新馬型＋③セリ価格原則を使う" if obs_id == "M" else "②初戦適性（種牡馬）を使う"
        blk.append(f"# 新馬カタログ（debut-catalog.md・{note}・カタログ外は追記候補で報告）\n" + ctx["debut_catalog"])
    if obs_id in ("D", "E") and ctx["course"]:
        src = "nar-course-geometry.md" if ctx["nar"] else "course-geometry.md 該当場"
        blk.append(f"# コース物理形状（{src}・正本＝web で再調査しない）\n" + ctx["course"])
    if obs_id == "F" and ctx["oikiri"]:
        blk.append("# 追い切り好時計 seed（fetch_oikiri.py・好時計の上位抜粋＝全頭でない。不在馬はweb補完）\n" + ctx["oikiri"])
    if obs_id in ("F", "K") and ctx["stable"]:
        blk.append("# 厩舎の勝負気配傾向（stable-intent-rubric.md・型ラベル＝仕上げ型/追い切り常態/騎手起用。catalog外は暫定＋追記候補で報告）\n" + ctx["stable"])
    if obs_id in ("D", "I", "G") and ctx["weight"]:
        blk.append("# 重量重みづけ seed（weight_adjust.py・斤量/馬格×馬場の決定論タグ。自分のチャンネルを使う＝ D/G:馬格×馬場のパワー適性, I:斤量増の減点。pace タグは展開合成が使う＝ここでは無視可。斤量・馬格は再調査せずこの値を採用）\n" + ctx["weight"])
    if obs_id == "I" and ctx["risk"]:
        blk.append("# 決定論リスク seed（risk_flags.py・高齢/下降基調/大幅昇級/休み明け＝seedから確定。一次フラグとして採用し再調査しない。webは脚部不安/気性難/競走中止歴の実測だけに絞る。敗因が距離/展開で説明でき地力でないなら割引可）\n" + ctx["risk"])
    if obs_id == "N" and ctx["nar_ladder"]:
        blk.append("# クラス階梯カタログ（nar-class-ladder.md・階梯/共通ランクR/換算原則の正本＝再調査しない。web は各馬の現級・転入元の事実確定だけ）\n" + ctx["nar_ladder"])
    return blk


def build_prompt(race_id, obs_id, ctx):
    """1観点ぶんの codex プロンプト＝agent指示＋共通鉄則＋spawnデータ＋書き出し先。"""
    instr = load_agent_instruction(obs_id)
    protocol = _read(PROTOCOL)
    card = ctx["card"] or "(出走表.md 無し)"
    seed = ctx["seed_raw"] or "(seed.json 無し)"
    out_rel = os.path.join("data", "races", race_id, f"research-{obs_id}.json")
    inj = "\n\n".join(_injections(obs_id, ctx))
    return (
        f"# 観点 {obs_id} 専属調査（race_id={race_id}）\n\n"
        f"あなたは競馬予想ハーネスの観点 {obs_id} 専属の収集員。以下の指示に厳密に従い、"
        f"web 調査の結果を **{out_rel} に JSON で書き出して終了**する（他のファイルは触らない）。\n\n"
        f"## 専属指示（この観点の役割・手順・スコア指針）\n{instr}\n\n"
        f"## 全観点共通の規律・推奨ソース・出力スキーマ\n{protocol}\n\n"
        f"## レースの核データ（出走表）\n```\n{card}\n```\n\n"
        f"## スクレイパ seed（脚質/テン速/近走/血統など。再調査せずここを起点に）\n```json\n{seed}\n```\n\n"
        + (f"## spawn 注入データ（正本カタログ・決定論 seed＝再調査しない）\n{inj}\n\n" if inj else "")
        + f"## 厳守\n"
        f"- 市場（オッズ・人気・他人の予想）は証拠にもログにも使わない（I1）。\n"
        f"- 指示文中の WebSearch/WebFetch/Workflow/agentType は Claude Code の用語＝あなたの環境の「web検索」「ページ取得」に読み替える（調査の量・範囲の規律はそのまま守る）。\n"
        f"- 出力は {out_rel} の1ファイルのみ。スキーマは上記『出力スキーマ』に従う（E は PACE_EVIDENCE_SCHEMA）。\n"
    )


def cmd_for(prompt_file):
    return CMD_TEMPLATE.format(root=shlex.quote(ROOT), prompt_file=shlex.quote(prompt_file))


def run_one(race_id, obs_id, ctx, race_dir, scratch, dry_run):
    prompt = build_prompt(race_id, obs_id, ctx)
    pf = os.path.join(scratch, f"prompt-{obs_id}.md")
    open(pf, "w", encoding="utf-8").write(prompt)
    cmd = cmd_for(pf)
    out_path = os.path.join(race_dir, f"research-{obs_id}.json")
    if dry_run:
        return {"obs": obs_id, "cmd": cmd, "prompt_chars": len(prompt), "status": "dry"}
    before_mtime = os.path.getmtime(out_path) if os.path.exists(out_path) else None
    try:
        r = subprocess.run(["/bin/sh", "-c", cmd], cwd=ROOT, capture_output=True,
                           text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return {"obs": obs_id, "status": "timeout"}
    # 「この実行で新しく書かれたか」を mtime で判定＝前回の残存ファイルを成功と誤認しない
    wrote = os.path.exists(out_path) and (
        before_mtime is None or os.path.getmtime(out_path) > before_mtime)
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


def fanout(race_id, only, max_parallel, dry_run, force_debut=False, force_nar=False):
    race_dir = os.path.join(ROOT, "data", "races", race_id)
    if not os.path.isdir(race_dir):
        raise SystemExit(f"レースディレクトリが無い: {race_dir}")
    ctx = build_ctx(race_id, race_dir, force_debut, force_nar)
    obs_ids = ([x.strip().upper() for x in only.split(",")] if only
               else default_obs(ctx["nar"], ctx["debut"]))
    for x in obs_ids:
        if x not in AGENT_OF:
            raise SystemExit(f"未知の観点: {x}（有効: {', '.join(AGENT_OF)}）")
    scratch = os.path.join(race_dir, ".codex_prompts")
    os.makedirs(scratch, exist_ok=True)

    results = []
    with ThreadPoolExecutor(max_workers=max_parallel) as ex:
        futs = {ex.submit(run_one, race_id, x, ctx, race_dir, scratch, dry_run): x for x in obs_ids}
        for f in as_completed(futs):
            results.append(f.result())
    return ctx, sorted(results, key=lambda r: r["obs"])


def self_check():
    errs = []
    if set(AGENT_OF) != set("ABCDEFGHIKLMN"):
        errs.append("AGENT_OF の観点集合が13観点(A-I,K,L,M,N)と不一致")
    # モード別の既定観点セット（SKILL STEP2／NAR SKILL 差分2 のミラー）
    if default_obs(False, False) != list("ABCDEFGHIKL"):
        errs.append("JRA 通常セットが11観点と不一致")
    if default_obs(False, True) != list("CEFIKM"):
        errs.append("JRA 新馬セットが C,E,F,I,K,M と不一致")
    if default_obs(True, False) != list("ABCDEGIKN"):
        errs.append("NAR 通常セットが A,B,C,D,E,G,I,K,N と不一致")
    if default_obs(True, True) != list("CEFIKMN"):
        errs.append("NAR 新馬セットが C,E,F,I,K,M,N と不一致")
    # 場トークン: NAR_KANJI は inject_probs.NAR_VENUES と同一集合・JRA は10場
    if set(NAR_KANJI) != set(NAR_VENUES):
        errs.append("NAR_KANJI のキーが inject_probs.NAR_VENUES と不一致")
    if len(JRA_KANJI) != 10:
        errs.append("JRA_KANJI が10場でない")
    # 注入 payload の抽出健全性（正本ファイルがあれば）
    if os.path.exists(COURSE_MD):
        c = course_payload(False, "東京")
        if "直線" not in c or "東京" not in c:
            errs.append("course_payload が東京セクションを抜けていない")
    if os.path.exists(PEDIGREE_MD):
        p = pedigree_payload({"horses": [{"sire": "ドゥラメンテ", "damsire": "存在しない架空種牡馬X"}]})
        if "ドゥラメンテ" not in p or "巻頭原則" not in p:
            errs.append("pedigree_payload が該当行/巻頭原則を抜けていない")
        if "存在しない架空種牡馬X" not in p:
            errs.append("pedigree_payload がカタログ外を明示していない")
    # 生成済み toml があれば prompt 組み立てを1観点で試す
    sample = os.path.join(AGENTS_DIR, "obs-e-pace.toml")
    if os.path.exists(sample):
        instr = load_agent_instruction("E")
        if "展開証拠" not in instr and "E " not in instr:
            errs.append("load_agent_instruction が本文を取れていない")
        c = cmd_for("/tmp/p.md")
        if "{prompt_file}" in c or "{root}" in c:
            errs.append("CMD_TEMPLATE の置換が未解決")
        # 注入込みの build_prompt が観点別ブロックを持つか（ダミー ctx）
        ctx = {"race_id": "t", "venue": "tokyo", "nar": False, "debut": False,
               "card": "x", "seed_raw": "{}",
               "course": "コース行", "pedigree": "", "stable": "", "debut_catalog": "",
               "nar_ladder": "", "weight": "", "risk": "", "oikiri": ""}
        pr = build_prompt("t", "E", ctx)
        if "コース物理形状" not in pr:
            errs.append("build_prompt が E にコース注入をしていない")
        if "読み替える" not in pr:
            errs.append("build_prompt にツール名読み替えの1行が無い")
    else:
        errs.append("obs-e-pace.toml が無い（先に gen_codex_agents.py）")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("race_id", nargs="?")
    ap.add_argument("--only", default=None, help="観点をカンマ区切りで限定（例 E,D,B。未指定はモード自動判定の既定セット）")
    ap.add_argument("--max-parallel", type=int, default=8)
    ap.add_argument("--debut", action="store_true", help="新馬モードを強制（既定は出走表.md の「新馬/メイクデビュー」で自動判定）")
    ap.add_argument("--nar", action="store_true", help="NARモードを強制（既定は race-id の場トークンで自動判定）")
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
    ctx, results = fanout(args.race_id, args.only, args.max_parallel, args.dry_run,
                          force_debut=args.debut, force_nar=args.nar)
    mode = ("NAR×新馬" if ctx["nar"] and ctx["debut"] else
            "NAR" if ctx["nar"] else "新馬" if ctx["debut"] else "JRA通常")

    if args.dry_run:
        print(f"# fan-out 計画（{len(results)} 観点・同時 {args.max_parallel}・モード={mode}・codex 未実行）")
        print(f"# CMD_TEMPLATE = {CMD_TEMPLATE}")
        print(f"# 注入: course={len(ctx['course'])}字 pedigree={len(ctx['pedigree'])}字 "
              f"stable={len(ctx['stable'])}字 weight={len(ctx['weight'])}字 risk={len(ctx['risk'])}字 "
              f"oikiri={len(ctx['oikiri'])}字 debut_catalog={len(ctx['debut_catalog'])}字 "
              f"nar_ladder={len(ctx['nar_ladder'])}字")
        for r in results:
            print(f"[{r['obs']}] prompt {r['prompt_chars']}字\n    {r['cmd']}")
        return 0

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"# fan-out 完了（モード={mode}）: {ok}/{len(results)} 観点で research-*.json 生成")
    for r in results:
        mark = "✓" if r["status"] == "ok" else "✗"
        print(f"  {mark} {r['obs']}: {r['status']}"
              + (f" (rc={r.get('rc')})" if r["status"] != "ok" else ""))
        if r["status"] != "ok" and r.get("stderr_tail"):
            print(f"      {r['stderr_tail'].strip()}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
