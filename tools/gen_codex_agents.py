#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_codex_agents.py — Codex用 観点エージェント定義(.codex/agents/*.toml)を正本(.claude/agents/obs-*.md)から生成。

なぜ:
  観点 subagent の指示は**エージェント中立の内容**（何をwebで調べ何を返すか）。Claude Code は markdown+frontmatter、
  Codex は toml で読む＝**形式だけ違う**。手で2つ維持すると必ずドリフトする（実際 v5.0 で乖離した）。
  正本を .claude/agents/obs-*.md に一本化し、Codex 版はここから**生成物**として吐く（編集するのは正本だけ）。

何を生成:
  .claude/agents/obs-<id>.md の frontmatter(name/description) + 本文 →
  .codex/agents/obs-<id>.toml（name / description / developer_instructions=本文）。
  末尾に「# GENERATED from .claude/agents/<file> — 手で編集しない」ヘッダを付す。

使い方:
  python3 tools/gen_codex_agents.py            # 生成（.codex/agents/*.toml を上書き）
  python3 tools/gen_codex_agents.py --check     # 生成物が最新かを検査（CI/コミット前ゲート・書き込まない）
  python3 tools/gen_codex_agents.py --self-check
終了コード: 0=OK / 1=差分あり(--check) or エラー。
"""
import sys, os, glob, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, ".claude", "agents")
OUT_DIR = os.path.join(ROOT, ".codex", "agents")


def parse_md(path):
    """obs-*.md → (name, description, body)。frontmatter は --- で挟まれた YAML 風。"""
    text = open(path, encoding="utf-8").read()
    if not text.startswith("---"):
        raise ValueError(f"{path}: frontmatter が無い")
    _, fm, body = text.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta.get("name", ""), meta.get("description", ""), body.strip()


def toml_literal(s):
    """TOML multiline literal string '''...''' 用。リテラルはエスケープ処理されないので
    markdown をそのまま入れられる。唯一の危険 ''' が本文にあれば安全な basic 文字列へ退避。"""
    if "'''" in s:
        esc = s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        return '"""\n' + esc + '\n"""'
    return "'''\n" + s + "\n'''"


def render_toml(name, desc, body, src_base):
    return (f"# GENERATED from .claude/agents/{src_base} — 手で編集しない\n"
            f"# 正本を直し `python3 tools/gen_codex_agents.py` で再生成すること。\n"
            f"name = {toml_literal(name)}\n"
            f"description = {toml_literal(desc)}\n"
            f"developer_instructions = {toml_literal(body)}\n")


def build_all():
    """{out_path: content} を返す（書き込みはしない）。"""
    out = {}
    for src in sorted(glob.glob(os.path.join(SRC_DIR, "obs-*.md"))):
        base = os.path.basename(src)
        name, desc, body = parse_md(src)
        out_path = os.path.join(OUT_DIR, base[:-3] + ".toml")
        out[out_path] = render_toml(name, desc, body, base)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="生成物が最新かを検査（書き込まない）")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        errs = []
        n, d, b = "obs-x", "説明", "本文\n複数行"
        t = render_toml(n, d, b, "obs-x.md")
        if "developer_instructions = '''" not in t or "本文\n複数行" not in t:
            errs.append("render_toml literal 不正")
        if "GENERATED" not in t:
            errs.append("生成ヘッダ欠落")
        tricky = toml_literal("これは ''' を含む")
        if not tricky.startswith('"""'):
            errs.append("''' 退避が効いていない")
        if errs:
            print("SELF-CHECK FAIL: " + "; ".join(errs), file=sys.stderr)
            return 1
        print("SELF-CHECK OK")
        return 0

    built = build_all()
    if not built:
        print("✗ 正本 .claude/agents/obs-*.md が無い", file=sys.stderr)
        return 1

    if args.check:
        stale = []
        for path, content in built.items():
            cur = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if cur != content:
                stale.append(os.path.relpath(path, ROOT))
        if stale:
            print("✗ Codex観点定義が古い（再生成が必要）:", file=sys.stderr)
            for s in stale:
                print("   " + s, file=sys.stderr)
            print("→ python3 tools/gen_codex_agents.py で再生成", file=sys.stderr)
            return 1
        print(f"✓ .codex/agents/*.toml は最新（{len(built)}件）")
        return 0

    for path, content in built.items():
        open(path, "w", encoding="utf-8").write(content)
    print(f"✓ {len(built)} 件の Codex 観点定義を生成（.codex/agents/*.toml）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
