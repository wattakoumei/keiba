# 出力契約（report.json schema）

`/analyze-race` の最終出力は **構造化正本 `data/races/<race-id>/report.json`** の1ファイル。
人間向けの閲覧は **keiba-web（Astro）が report.json をレンダリングした web サイト**で行う（`report.md` は**廃止**＝手書きしない。過去レースの旧 report.md は残置）。

> **役割分担（I10）**: `report.json` が唯一の正本。web はその**ビュー**で正本を複製しない。
> `predictions.jsonl` は report.json からの**自動投影**（`tools/project_predictions.py`）＝review-prediction 用ログ。源は report.json 一本。
> 書込直後に **`python3 tools/validate_report.py <race-id>`**（スキーマ＋I2(%)＋**I1(市場・予想語)**＋I5＋全頭カバー）と **`python3 tools/validate_research_bundle.py <race-id>`**（observation↔artifact対応・馬番集合・I1市場語）を通す（Astro ビルド前提条件）。

> **不変則（中身の規律。形式が JSON になっても変わらない）**
> - **I2 散文%禁止＋率2カラム例外**: `report.json` の**文字列フィールドに `%`/`％` を一切書かない**（発揮能力・条件付き%・枠別複勝率%…散文%はすべて定性表現へ）。validator がエラー検出。
>   強弱は **印 ◎◯▲△×注 と `rank_order`（行順）**、確からしさは **可能性ティア `本線/対抗/伏線`** で表す。
>   **限定例外**＝`rank[].win_prob`/`place_prob`（**0..1 の数値F**・源は `tools/score_race.py` のみ）は web が `×100` して「単勝%」「複勝%」の2カラムに描画する。**並びは `rank_order` 順のまま・率は参考列**（率順に並べ替えない＝I8）。文字列には依然%を書かない＝率は数値Fのみ。
>   数値の `prob`（パターン内部確率）/`pace_level` は**ログ専用フィールド**＝**web は描画しない**（jsonl 投影と展開検証のために保持）。
> - **I1 市場ゼロ**: オッズ・人気・他人の予想・買い目・EV は持たない。馬券選択は人間。
> - **I3 表中心・最小分量**: §1 は1行。mermaid 等の図は持たない（段階フローは `phase_flow` の4文＝early/mid/late/result）。重複を出さない（結論の正本は `rank[]`）。
> - **I4 2成果物の独立**: `pace`（成果物1）と `rank`（成果物2）を別個に持ち、各々 `*_verification_contract` を備える。
> - **I5 複数パターン＋当日可変**: `pace.patterns[]` は必ず複数。
> - **I6 確定材料の先取り**: 枠順・乗替・回避が確定済みなら `pace.leg_table`/`patterns`/`rank` 本文に最初から織り込む（`day_board` に後付けしない）。
> - **I7 展開列＝箱組み**: `rank[].pattern_fit` と `pace.box_reverse` は同源（`per_horse_fit`）で矛盾させない。
> - **I11 散文の内部用語禁止**: report.json の**文字列フィールド**（phase_flow の early/mid/late/result、bias、pace_sensitivity、pros/cons の note、engine_check 等）に**エンジン内部の変数名を書かない**。読者は競馬ファンであり開発者ではない。以下の置換表に従う:
>   | 内部用語 | 散文での表現 |
>   |---------|-------------|
>   | `A_early` | 行き脚 |
>   | `A_cruise` | 追走力 |
>   | `A_finish` | 決め手 / 末脚 |
>   | `A_class` | 地力 |
>   | `phase_flow`（散文中での言及） | 段階フロー |
>   | `pace_level` | ペース水準 |
>   | `per_horse_fit` | パターン適合 |
>   JSON の**キー名**（`"phase_flow":`, `"pace_level":` 等の構造部分）はそのまま。禁止は値の散文のみ。

---

## report.json スキーマ

`§0〜§4` を構造化したもの。免責（§5）は静的テンプレ＝**data に持たない**（web 側に固定表示）。
具体例の参照点＝`data/races/20260617-kawasaki-11/report.json`（fixture）。

### meta（ヘッダ）

| キー | 型 | 意味 |
|------|----|------|
| `schema_version` | str | スキーマ版（現行 `"1.0"`）|
| `race_id` | str | `YYYYMMDD-開催-RR`（**RRは2桁0埋め**。突合キー）|
| `race_name` / `edition` / `race_no` / `grade` | str/str/int/str | レース名・回次・R番号・格 |
| `date` | str | `YYYY-MM-DD` |
| `course` | obj | `{track, surface, distance(int), direction}`（物理形状は `course-geometry.md` 由来）|
| `conditions` | str | 条件（例 `3歳牝馬定量55kg`）|
| `field_size` | int | 出走頭数（`rank[]` の件数と一致）|
| `model_version` | str | `"5.0"` |
| `used_observations` | str[] | 使用観点（例 `["A","B","C",...]`）|
| `header_notes` | str[] | モデル注記・観点欠落の代替構築・engine_check 有無・確定材料先取りの宣言 |
| `pivot` | str | **§1 当日の分岐点（1行）**。展開を分ける一点。 |

### §0 `day_board`（当日ボード・read-only）

> 分析時点で**本当に未知のものだけ**（I6）。web は**read-only チェックリスト**として表示（当日値は source に入れない＝絞り込みは web のチップで）。

| キー | 型 | 意味 |
|------|----|------|
| `reference_races` | obj[] | `{label, when, course, match(★), watch}` 当日バイアス採取用の参考R |
| `reference_note` | str | 参考R採取の優先順位メモ |
| `observation_blanks` | str | 当日記入の観察項目（ペース層／内外バイアス／決まり手／伸び位置）|
| `going` | obj[] | `{item, value(""), read}` 馬場状態・含水率・風（向き・強さ）等の当日確認項目と質の読み |
| `paddock_watch` | obj[] | `{mark, gate_no, horse, weight_note}` 注目馬のパドック観察枠 |
| `other_unknowns` | str[] | 折り合い・当日乗替/取消など未確定事項 |

### §2 `pace`（成果物1・展開予想）

| キー | 型 | 意味 |
|------|----|------|
| `verification_contract` | str | 検証契約（脚質有利不利・隊列・段階フローを固定しレース後に展開精度を独立採点）|
| `pace_factors` | obj[] | **展開トリガー早見（任意・推奨）**。来そうな展開を判断する材料を race-level で並べる。`{factor, reads, day_check}`。下記参照。web は §2 先頭に `<details open>` 表示・jsonl の pace レコードにも載る |
| `leg_table` | obj[] | **§2-1 脚質分類表**。`{gate, no, horse, jockey, trainer, leg_type, recent_pos, expected_pos}` 全馬（`trainer`＝調教師・核データ） |
| `patterns` | obj[] | **§2-2 展開パターン（複数）**。下記 pattern 構造。|
| `shape_note` | str | 展開の質メモ（**%・確率数値を書かない**＝定性。前崩れ系が前残りを上回る…等）|
| `formation_note` | str | 隊列（最有力パターンの序盤先頭→最終コーナー前方）|
| `bias_note` | str | 馬場バイアス（内外・枠の有利不利。当日 §0 で上書き前提）|
| `counter_conditions` | str | 反証条件（どの当日条件でどのパターンを本線へ付け替えるか）|
| `transmission` | str | **展開→着順の伝達**（最有力パターンで◎の着順がどう動くか。A/B/C仕分けの起点）|
| `box_reverse` | obj[] | **パターン別おすすめ馬（箱組み逆引き）**。`{pattern, tier, center[], inside[], spot[], drop[]}`（馬番配列）。源は `rank[].pattern_fit` と同一＝矛盾させない（I7）|

**pattern 構造**（`pace.patterns[]` の各要素）:

| キー | 型 | 意味 |
|------|----|------|
| `id` | str | パターンID（`α`/`β`/`γ`/`δ` 等）|
| `name` | str | パターン名 |
| `tier` | str | 可能性ティア `本線`/`対抗`/`伏線`（jsonl 投影時に `likelihood_tier`）|
| `prob` | num | 内部確率（**ログ専用・web 非描画**。0..1）|
| `trigger` | str | 発動トリガー |
| `pace_level` | num | ペース水準 0..1（ログ・展開検証用）|
| `contesters` | int[] | 先行争いの当事者（馬番）|
| `leg_advantage` | obj | `{逃げ,先行,差し,追込}` の有利不利スコア |
| `formation_head` / `formation_last_corner` | int[] | 序盤先頭・最終コーナー前方の隊列（馬番）|
| `bias` | str | そのパターンでのバイアス |
| `phase_flow` | obj | **段階フロー** `{early, mid, late, result}` の4文（図にしない＝I3）|
| `risers` / `sinkers` | int[] | 浮上馬・沈む馬（馬番）|

**pace_factors 構造**（`pace.pace_factors[]` の各要素・**展開トリガー早見**）= 「どの展開が来そうか」を人間が判断・当日に再ティアするための材料。pattern の `trigger`（個別スイッチ）に対し、これは race-level の**立っている材料**:

| キー | 型 | 意味 |
|------|----|------|
| `factor` | str | 材料名。**最低限カバー**: `先行勢の数と質`／`枠の効き`／`コース形状`／`例年傾向（過去開催）`／`当日で動く点`（レースに応じ騎手の出方・頭数等を足す）|
| `reads` | str | その材料の読み＝事実＋どのパターン（α/β…）へ振れるか。**% 禁止＝定性**（I2）。脚質別有利不利を手で固定せず「○○ならβ寄り」と条件で書く |
| `day_check` | str | 当日に確認して当落を判定する観測点（`§0 day_board` と連動。確定済みで動かない材料は `—`）|

- `例年傾向（過去開催）` の `reads` は **`tools/fetch_result.py history <過去開催id…>`** のペース署名（勝ち馬1角位置・上がり最速馬の着順・ρ）を素材に書く。**過去idは web 調査で特定**（同レースの過去開催の日付→12桁id化）。NAR(地方)は取得不確実＝web で補完。**結論(H/M/S)でなく定性傾向**を書く。
- `day_check` が埋まる材料は **§0 `day_board`** にも観察枠を用意して連動させる（当日採取→`counter_conditions` でティア付け替え）。

### §3 `rank`（成果物2・着順予想）＋ `rank_verification_contract`

`rank_verification_contract`(str): 検証契約（並び＋展開列・展開感度・好材料/懸念を固定。レース後に(a)順位相関(b)実現パターンと展開列/展開感度の的中を別個採点。**百分率は出さない**）。

`rank`(obj[]): **全馬を `rank_order` 昇順**で（下位・無印馬も省かない）。web の既定表示はこの印順、トグルで `leg_type` 脚質順（逃→先→差→追）。

| キー | 型 | 意味 |
|------|----|------|
| `no` / `gate` | int/str | 馬番・枠 |
| `horse` | str | 馬名 |
| `jockey` | str | 騎手 |
| `trainer` | str | **調教師（核データ）**。勝負気配(`intent`)の厩舎基準・将来の厩舎catalog結合キー。取得元＝JRA/競馬ラボはスクレイパ、NARは手動出走表 |
| `jockey_change` | str | 観点K乗替区分 `継続`/`強化`/`弱化`/`乗替`（テン乗り含む）|
| `intent` | str | **勝負気配度** `↑↑`/`↑`/`→`/`↓`（陣営がこの一戦に賭けているかの定性記号。**能力・印とは独立**＝強い馬の叩き台は `→`/`↓`・人気薄の一変狙いは `↑` も）。源＝**F追い切り差分＋K起用(`jockey_change`)＋H自信度**を束ねる（新規調査なし＝既証拠から導出）。**事前(F+K)で確定→当日Hで±1段更新可**。`%`・市場(人気/オッズ)は使わない。`↑↑`複数シグナル合致／`↑`前向き1〜2個／`→`平常(既定)／`↓`叩き台・使い込み・乗替弱化・手控え・弱気 |
| `mark` | str | 印 `◎◯▲△×注—`（強弱の主表現。`◯`=対抗の大円）|
| `rank_order` | int | 並び順位（1..N 連番）|
| `win_prob` | num | **単勝率（0..1）**。源＝`tools/score_race.py` の決定論出力。web が `×100` して「単勝%」列に描画。**並びは論理(`rank_order`)が主＝率順に並べ替えない**。較正先(市場)が無い内在%＝偽の精度（`header_notes` に明記）|
| `place_prob` | num | **複勝率（0..1・top3 Harville近似）**。源・描画・注意は `win_prob` と同じ。web は「複勝%」列に描画 |
| `leg_type` | str | 脚質（脚質順ソートの源）|
| `pattern_fit` | obj | **展開列の機械可読版** `{パターンID: "◎"\|"○"\|"△"}`。**圏内のみ記載・圏外は省略**。`◎`中心/`○`圏内/`△`一発（`○`=圏内の小円、`◎○△`のみ許可）|
| `pace_sensitivity` | str | **展開感度（1行）**: どの展開で浮上/沈むか・なぜ。`pattern_fit` が「どこで効くか」、これが「なぜそう読むか」の対 |
| `pros` / `cons` | obj[] | **好材料/懸念点** `{tag, note}`。各馬2〜4個。`note`＝事実＋なぜそう読んだか（**%禁止**）。`tag`＝観点 A指数/B近走/C血統/D適性/E展開/F調教/G馬体ローテ/H気配/K騎手/I リスク/L条件実績（複合は `A/B` 可）|

### §4

| キー | 型 | 意味 |
|------|----|------|
| `data_confidence` | str[] | 確信度が低かった観点・欠損・推定箇所・突合の根拠 |
| `reinforcement_requests` | str[] | ユーザー補強推奨（当日バイアス・確定馬体重・パドック等）|

---

## predictions.jsonl への投影（自動・`tools/project_predictions.py`）

report.json から **2種のレコードを抽出して append**する（手書きしない）。review-prediction はこの jsonl を従来どおり読む。

- **(1) pace レコード**（1レース1行・`record:"pace"`）: `pace.patterns[]` ＋ meta から組む。
  `{record:"pace", race_id, race_name, date, model_version, patterns:[{id, name, likelihood_tier(=tier), trigger, pace_level, contesters, leg_advantage, formation_head, formation_last_corner, bias, phase_flow, prob}], pace_factors, box_reverse(=pace.box_reverse・I7 箱組み逆引き＝box_sim の入力), falsification(=counter_conditions), note}`
- **(2) rank レコード**（**印持ち馬＝`mark!="—"` のみ**・1馬1行・`record:"rank"`）: `rank[]` から抽出。
  `{record:"rank", race_id, date, model_version, horse_no(=no), horse, trainer, mark, rank_order, intent, win_prob, place_prob, pattern_fit, pace_sensitivity, pros, cons}`（任意 `engine_check`）。`win_prob`/`place_prob` は review で着順精度の**補助採点**に使う（並びの主は論理）。

> `pace_level`/`leg_advantage`/`formation_*`/`prob` は**展開検証の正本として維持**（jsonl にも残す）。
> 当日更新時は report.json を更新→再投影。jsonl は**上書きせず** `note:"当日更新"` 付きで追記し履歴を残す。
> 後方互換: 旧 v1.x〜v4.0 の jsonl 行（`win_prob`/`phase_abilities`/`conditional[]` 等）はそのまま読める。新行はそれら%見出しを持たない。

## web レンダリング（keiba-web / Astro）の不変則

- report.json を `glob ../data/races/*/report.json` で読み、build 時に Zod（本スキーマと同型）で検証。
- **`prob`/`pace_level` は描画しない**（ログ専用）。ティア・印・行順・展開列・展開感度・好材料/懸念で伝える。
- **率2カラムは描画する**（I2 限定例外）: `rank[].win_prob`/`place_prob` を `×100`・小数1桁の「単勝%」「複勝%」列に。**並びは `rank_order` 順のまま**（率順に並べ替えない）。率は論理の並びに添える参考＝欠損馬は `—` 表示。
- v1 UX: 馬タップ→`pros/cons` 展開／パターン(α…)タップ→`pattern_fit` 連動ハイライト＋`phase_flow` 表示／印順⇄脚質順トグル／パターンチップ＋手動除外・注目トグル(localStorage)。
- ビューは正本を複製しない（I10）。`box_reverse` と `pattern_fit` は同源で矛盾させない（I7）。
