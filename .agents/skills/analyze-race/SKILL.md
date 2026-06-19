---
name: analyze-race
description: 競馬レースを観点別の並列web調査で分析し、全証拠を突き合わせて複数の展開パターン（可能性ティア付き）を合成する。展開予想と着順予想を独立した2成果物として提示。市場（オッズ・人気）は一切使わず、馬券は人間判断。「◯◯レースを分析して」「<netkeiba URL>を分析」「(出走表貼り付け)を分析」で起動。
---

# analyze-race — 競馬予想オーケストレータ

観点ごとの web 調査 subagent を並列起動し、集まった証拠から **展開予想（成果物1）** と
**着順予想（成果物2）** を作る。モデル哲学とデータ配置は repo ルートの `AGENTS.md` が概観、
この skill は実行手順の入口。

## 最重要不変則

- **市場ゼロ**: オッズ・人気・他人の予想・専門紙の印・買い目・EV は証拠にもログにも入れない。
- **%禁止**: レポート文字列に `%`/`％` を出さない。強弱は印・行順・可能性ティア・展開列で示す。
- **2成果物を分離**: `pace` と `rank` を別々に作り、別々に検証できる形で保存する。
- **構造化正本**: 最終成果物は `data/races/<race-id>/report.json`。`report.md` は新規作成しない。
- **全馬カバー**: `rank[]`・`pace.leg_table[]`・使用観点の `research-*.json` は全頭を含む。
- **速度優先の純度維持**: seed/静的カタログで足りる情報は再検索しない。深掘りは勝敗・展開を動かす馬に集中する。

## 参照ファイル（必要になったものだけ読む）

- `references/output-template.md`: `report.json` スキーマ、I1/I2、jsonl 投影、web 描画契約。
- `references/research-protocol.md`: subagent 共通規律、速度・トークン予算、出力スキーマ。
- `references/observation-points.md`: 観点の意味、5/7/11 観点の選び方、相別能力への対応。
- `references/pace-synthesis.md`: STEP4a 展開合成、複数パターン、phase_flow、当日可変。
- `references/scraping.md`: `fetch_racecard.py` / `fetch_result.py` の使い方と場コード。
- `references/course-geometry.md`: コース物理形状。該当行だけ使い、web 再調査しない。
- `references/pedigree-catalog.md`: 血統カタログ。該当父・母父だけ使い、カタログ内は再検索しない。
- `references/stable-intent-rubric.md`: F/K 用の厩舎勝負気配ラベル。該当厩舎だけ使う。
- `references/scoring-model.md`: 相変位再帰の語彙。`score_race.py` は任意の並びサニティのみ。

## 実行手順

### STEP 1. レース特定と核データ

1. 入力（レース名 / URL / 貼り付け）から `race-id = YYYYMMDD-開催-RR` を決める。RR は2桁。
2. まず決定論ツールで核データを取る。
   - `python3 tools/fetch_racecard.py race <race_id> --json`
   - 今週開催で調教 seed が必要なら `python3 tools/fetch_oikiri.py week --json`
   - 当日参考Rが必要なら `python3 tools/fetch_racecard.py day <YYYYMMDD> <場2桁> --json`
3. `data/races/<race-id>/出走表.md` に、レース条件・全馬・騎手・調教師・枠馬番・前走・父母父などを保存する。オッズ列は持たない。
4. 取得が曖昧なら、推定で埋めずユーザーに URL または出走表貼り付けを求める。

確定済みの枠順・乗替・回避はここで本文材料へ織り込む。`day_board` には、分析時点で本当に未知の当日馬場・馬体重・パドック・参考R観察だけを残す。

### STEP 2. 観点モードを選ぶ

速度とトークンを節約するため、既定は頭数だけでなく「情報の厚さ」で絞る。

| モード | 使う目安 | 観点 |
|---|---|---|
| **5観点** | 〜10頭、地方、平場、web情報が薄い | AB / CD / E / FGHK / I |
| **7観点** | 10〜13頭、標準的な条件戦 | AB / C / D / E / FGK / H / I |
| **11観点** | 14頭以上、G1・重賞、情報が厚い、L/Kが鍵 | A B C D E F G H I K L |

例外:
- K が展開や勝負気配を動かすレースは単独で残す。
- L はリピーター色の濃いレースだけ残す。下級条件・若馬戦では原則省く。
- 展開合成（STEP4a）は、どのモードでも必須。

### STEP 3. 証拠ファンアウト

選んだ観点だけを専属 subagent（`.codex/agents/obs-*.toml`）で並列起動する（Codex の並列 subagent 機構を使う）。
subagent へ渡す payload は**短く**する。

必ず渡す:
- レース条件、全馬リスト、`field_size`
- `fetch_racecard.py` の seed（E/C/B/K で特に使用）
- 共通鉄則＋速度予算: `research-protocol.md` の「共通ルール」「速度・トークン予算」を**逐語注入**する（subagent は rules/protocol を自動ロードしない＝これが純粋性・全馬カバー・予算が届く唯一の経路）
- 出力先: `data/races/<race-id>/research-<観点ID>.json`

必要観点だけに渡す:
- C: `pedigree-catalog.md` の該当父・母父行だけ
- D/E: `course-geometry.md` の該当コース行だけ
- F: `fetch_oikiri.py` の該当馬 seed だけ
- F/K: `stable-intent-rubric.md` の該当厩舎行だけ

調査予算:
- seed と静的カタログで判断できる馬は web 再検索しない。
- 1観点あたり原則 **WebSearch 2バッチ以内 + WebFetch 1バッチ以内**。
- 深掘りは「上位候補」「展開トリガー」「seed矛盾」「強いリスク」に絞る。
- 取得できない情報は欠損として確信度を下げる。穴埋め目的の長時間検索はしない。

各 subagent は構造化 JSON のみを保存・返却する。Markdown の長文調査メモは作らない。

### STEP 4a. 展開合成（成果物1）

`pace-synthesis.md` に従い、観点Eだけでなく B/D/K/H/枠/コース形状を突き合わせて、
2〜4個の名前付き展開パターンを作る。

必須:
- `patterns[]`: `id`、`name`、`tier`、内部 `prob`、`pace_level`、`trigger`、`leg_advantage`、
  `formation_head`、`formation_last_corner`、`phase_flow`
- `phase_flow`: early/mid/late/result の4文。相変位再帰の因果語彙で書く。
- `pace_factors`: 先行勢、枠、コース形状、例年傾向、当日で動く点。
- `box_reverse`: `rank[].pattern_fit` と同源にする。

報告上は可能性ティアを使う。内部 `prob` は検証・ログ用で、web では描画しない。

### STEP 4b. 着順合成（成果物2）

最有力パターンの `phase_flow` に各馬を通し、A_early/A_cruise/A_finish/A_class の因果で
**印 ◎◯▲△×注— と `rank_order`** を決める。

必須:
- 全馬を `rank[]` に入れる。無印も省かない。
- `pattern_fit`: 各展開で圏内なら `◎/○/△` を付ける。圏外は省略。
- `pace_sensitivity`: どの展開で浮く/沈むかを1行で書く。
- `pros` / `cons`: 各馬2〜4個、観点タグ + 事実 + なぜそう読むか。
- `intent`: F/K/H 既存証拠から `↑↑/↑/→/↓` を決める。新規調査はしない。

整合ルール:
- `formation_head` / `formation_last_corner` / `falsification` に馬番で登場した馬は、印または注の候補として検討する。切るなら cons に理由を書く。
- A_finish 最上位級の馬は位置不利だけで全消しせず、届く展開を `△` 以上で検討する。
- `score_race.py` は任意。使う場合も並びサニティだけ確認し、% は転記しない。

### STEP 5. 保存と検証

1. `output-template.md` のスキーマで `data/races/<race-id>/report.json` を書く。
2. 必須ゲートを通す。
   - `python3 tools/validate_report.py <race-id>`
   - `python3 tools/validate_research_bundle.py <race-id>`
   - `python3 tools/project_predictions.py <race-id>`
3. エラーが出たら report/research を直して再実行する。

`validate_research_bundle.py` は軽量化で起きやすい観点欠落・全馬欠落・市場語混入を止めるため必須。

### STEP 6. 当日可変

当日情報を受けたら、基本は再調査しない。

- 馬場・参考R・乗替/取消で展開が動く: 既存パターンのティアを付け替え、最有力 `phase_flow` に沿って `rank` を再評価。
- パドック・馬体重など特定馬の状態が動く: その馬の H/G 読みと `intent` だけ更新。
- 更新後は `validate_report.py` → `validate_research_bundle.py` → `project_predictions.py <race-id> --update`。

## 速度改善の考え方

精度を落とさず速くする鍵は「検索を減らす」ことではなく、**検索する理由を限定する**こと。
seed、コースカタログ、血統カタログ、厩舎ラベルで説明できる部分は再取得せず、web は
「今日だけ変わる情報」「seedと矛盾する情報」「展開や印を動かす馬」に使う。
