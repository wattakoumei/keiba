# keiba ハーネス編集マップ（どこを触ればいいか）

> 自動ロードされる（`.claude/rules/`）。「ハーネスを組みづらい」＝どのファイルを直せばいいか分からない、への処方。
> 不変則の正本は [harness-invariants.md](harness-invariants.md)。**矛盾時はそちらが勝つ**。

## ファイル責務マップ

| ファイル | 責務（ここを触るのはこういう時） |
|---|---|
| `CLAUDE.md` | プロジェクト全体像・モデル哲学・用語・データ配置・改善ループの**概観**。詳細仕様は各 reference に委譲。 |
| `.claude/rules/harness-invariants.md` | **不変則の正本**（市場ゼロ・%禁止・表中心・2成果物・展開列…）。 |
| `.claude/rules/editing-map.md` | この編集マップ。 |
| `.claude/skills/analyze-race/SKILL.md` | `/analyze-race` の**手順**（STEP1-6・Workflow 骨子＝観点 subagent の並列起動＋展開合成・観点モード決定・`AGENT_OF` マップ）。 |
| `.claude/agents/obs-*.md` | **観点ごとの専属 subagent（11個・A〜I,K,L）**：各観点の persona・調査手順・クエリ・推奨ソース・スコア指針。**観点を1つ調整するならここ**。Workflow から `agentType` で並列起動。 |
| `.claude/skills/analyze-race/references/observation-points.md` | **観点カタログの概念定義**（因子/相別マッピング 観点→A_early/cruise/finish/class・グルーピング 5/7/11）。手順は持たない（agent 側）。 |
| `.claude/skills/analyze-race/references/research-protocol.md` | **全観点共通**の規律・推奨ソース・**出力スキーマ**（RESULT_SCHEMA／E は PACE_EVIDENCE_SCHEMA）。観点固有の手順は持たない（agent 側）。 |
| `.claude/skills/analyze-race/references/pace-synthesis.md` | **展開合成 STEP4a**：複数パターン・phase_flow・`per_horse_fit`・当日可変・PACE_MODEL_SCHEMA。 |
| `.claude/skills/analyze-race/references/scoring-model.md` | 相変位再帰の**語彙と因果骨格**（相別能力→3相再帰）。6ノブ/PARAMS は任意エンジン用。 |
| `.claude/skills/analyze-race/references/output-template.md` | **レポート体裁の正本**（§0-§5・展開列/展開感度/好材料/懸念点の書式・mermaid無し）＋ `predictions.jsonl` の pace/rank 2レコード形式。 |
| `.claude/skills/analyze-race/references/course-geometry.md` | **コース物理形状の静的カタログ**（直線長・坂・初角特記。D/E/展開合成の正本）。コース改修・数値訂正はここだけ直す。 |
| `.claude/skills/analyze-race/references/pedigree-catalog.md` | **血統カタログ**（種牡馬の父/母父傾向・決め手の質・巻頭原則。観点Cの正本）。半静的＝年1回＋新種牡馬デビュー時に追記、`as-of` 更新。 |
| `.claude/skills/analyze-race/references/stable-intent-rubric.md` | **厩舎の勝負気配傾向**（3次元の型ラベル＝仕上げ型/追い切り常態/騎手起用）の定義＋lazy catalog。F/K に spawn 注入し `intent` の"普段の基準"に使う。半静的・有料DB不要・総合力とは独立。出会った厩舎を追記候補→human承認で追記。 |
| `.claude/skills/analyze-race/references/scraping.md` | `tools/fetch_racecard.py`（出走表/当日カード）・`tools/fetch_oikiri.py`（追い切り好時計seed=観点F）の使い方・場コード・JRA/競馬ラボ/競馬ブック経路。 |
| `.claude/skills/review-prediction/SKILL.md` | `/review-prediction`：**2スコアカード採点**・A/B/C 仕分け・修正先ルーティング・results.jsonl 形式。 |
| `tools/score_race.py` | 任意サニティチェックの決定論実装（並びの整合のみ。%の正本ではない）。 |
| `tools/validate_report.py` | report.json の**スキーマ＋I2(%禁止)＋I5(複数パターン必須)＋全頭カバー(rank=field_size)**ゲート（STEP5必須・依存ゼロ）。 |
| `tools/validate_research_bundle.py` | **`used_observations`↔実 `research-<観点>.json` の対応ゲート**（観点欠落の無検知を塞ぐ＝P6対策・STEP5必須）。schema検証とは別tool＝過去レースの `--all` schema検証を壊さない。 |

## 「〜を変えたい」→ どこを直す

| やりたいこと | 主に直すファイル |
|---|---|
| レポートの**列・見た目・分量**（行を増減、列追加、書式） | `output-template.md`（必要なら CLAUDE.md データ配置の1行も） |
| **不変則**（% / 市場 / mermaid / サマリ等の方針） | `harness-invariants.md` → 各文書のエコーを追従（下記手順） |
| **観点の調査手順・クエリ・ソース・スコア指針**を1つ調整 | `.claude/agents/obs-<id>.md`（その観点の subagent だけ） |
| **観点の追加/削除・相別マッピング・グルーピング**（着順の読み筋＝レビューA系の修正先） | `observation-points.md`（追加時は新 `.claude/agents/obs-*.md` ＋ SKILL の `AGENT_OF` も） |
| **展開パターンの作り方**・phase_flow・展開列の源（展開の読み筋＝レビューB系の修正先） | `pace-synthesis.md` |
| 各観点の**調査手順・ソース** | `research-protocol.md` |
| スコアリングの**語彙・エンジン（6ノブ）** | `scoring-model.md` |
| **採点基準・A/B/C 仕分け・修正ルーティング** | `review-prediction/SKILL.md` |
| **スクレイピング**（取得元・コード） | `scraping.md` |
| 予測ログの**フィールド**（pace/rank レコード） | `output-template.md` 末尾（＋読む側の review-prediction/SKILL.md） |

## 不変則を変えるときの手順（ドリフト防止）

1. **`harness-invariants.md` を直す**（正本）。
2. **各文書のエコーを grep して追従**させる。例:
   - `grep -rn "mermaid" .claude` ／ `grep -rn "サマリ\|観点別ハイライト" .claude`
   - `grep -rn "§2\|§3" .claude`（番号を変える場合は参照を全部直す。原則 §2/§3 は変えない＝[harness-invariants](harness-invariants.md) I9）
3. レポート体裁が絡むなら **`output-template.md` を最後に確認**（体裁の正本）。
4. モデル（相別能力・3相再帰）を触った場合のみ `scoring-model.md` のバージョンを上げる。

## 成果物と検証の対応（改善ループ）

- **成果物1 展開予想（§2）** ↔ 展開精度スコアカード（B系）→ 修正先は `pace-synthesis.md`・観点E・pace_level/phase_flow。
- **成果物2 着順予想（§3）** ↔ 着順精度スコアカード（A系）→ 修正先は `observation-points.md` の相別マッピング・好材料/懸念の読み筋・**展開列(pattern_fit)**。
- 採点と一次仕分け（A/B/C）の手順は `review-prediction/SKILL.md`。
