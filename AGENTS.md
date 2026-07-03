# 競馬予想ハーネス (keiba) — Codex エントリ

> **このファイルは薄いポインタ。正本を複製しない（複製は必ずドリフトする）。**
> モデル哲学・不変則・観点・データ配置の**正本は Claude Code 版と共有**する。Codex で作業する前に次を読む:
> 1. **`CLAUDE.md`** — プロジェクト全体像・モデル哲学・用語・データ配置・改善ループ（正本）。
> 2. **`.claude/rules/harness-invariants.md`** — 強制ルールの正本（市場ゼロ・%禁止・表中心・2成果物の独立・複数パターン・確定材料先取り・率2カラム・エンジンサニティ）。**方針が食い違ったら invariants が勝つ。**
> 3. **`.claude/rules/editing-map.md`** — 「何を変えたい→どのファイル」のルーティングとドリフト防止手順。
>
> Codex は `.claude/rules/` を自動ロードしない＝**セッション開始時にこの3ファイルを明示的に読むこと**。

## Claude Code ↔ Codex の対応（オーケストレーションだけが差分）

決定論コア（`tools/*.py`＋`data/`）と手順・観点の**中身はエージェント非依存で共有**。違うのは「どう並列起動するか」だけ。

| 役割 | Claude Code | Codex | 実体 |
|---|---|---|---|
| エントリ／哲学 | `CLAUDE.md` | このファイル→ `CLAUDE.md` を読む | 正本は CLAUDE.md |
| 強制ルール | `.claude/rules/*.md`（自動ロード） | 手動で読む（上記) | 正本は `.claude/rules/` |
| 手順（analyze/review） | `.claude/skills/*/SKILL.md` | `.agents/skills/*/SKILL.md` | **symlink＝同一バイト** |
| リファレンス（scoring/pace 他） | `.claude/skills/analyze-race/references/` | `.agents/skills/analyze-race/references/` | **symlink＝同一バイト** |
| 観点 subagent（11体） | `.claude/agents/obs-*.md`（`agentType`で並列） | `.codex/agents/obs-*.toml` | **生成物**（`tools/gen_codex_agents.py`） |
| 観点の並列 fan-out | Workflow / Task ツール | `tools/codex_fanout.py`（並列 `codex exec`） | 観点ごと research-`<X>`.json |
| 決定論ツール | `tools/*.py` をシェル実行 | 同じ `tools/*.py` をシェル実行 | 完全共有（標準ライブラリのみ） |

## Codex での回し方（analyze-race）

1. 出走表/seed を用意（`tools/fetch_racecard.py` は Claude 版と共通）。`data/races/<race-id>/` に `出走表.md`・`seed.json`。
2. **観点調査を並列 fan-out**: `python3 tools/codex_fanout.py <race-id>`（`--only E,D,B` で限定・`--dry-run` で確認）。
   各観点は `.codex/agents/obs-*.toml` の指示＋共通鉄則＋seed を受け、`research-<X>.json` を書く。
3. 以降は Claude 版と同一手順（`.agents/skills/analyze-race/SKILL.md` の STEP4a 展開合成 → STEP4b 着順 → 率注入 `tools/inject_probs.py` → `tools/validate_report.py`）。SKILL 内の「Workflow で実行」は Claude 実装＝Codex では上記 fan-out に読み替える。

## ドリフト防止（重要）

- **`.codex/agents/*.toml` は生成物**＝手で編集しない。観点を直すなら正本 `.claude/agents/obs-*.md` を編集し `python3 tools/gen_codex_agents.py` で再生成。コミット前ゲート＝`python3 tools/gen_codex_agents.py --check`。
- **references / SKILL は symlink**＝Codex 側で編集すると正本を書き換える（それが正しい＝単一ソース）。別物にしない。
- 市場ゼロ（I1）はじめ不変則は Claude 版と同一に守る。選別レイヤー `/screen-card` の市場隔離（I1-S）も同じ。

## 免責

出力は予測であり的中を保証しない。馬券選択・実ベットは人間判断。市場は予想本体で一切参照しない。
