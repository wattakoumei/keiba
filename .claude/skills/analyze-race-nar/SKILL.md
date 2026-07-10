---
name: analyze-race-nar
description: 地方競馬（NAR）のレースを観点別の並列web調査で分析し、展開予想と着順予想を独立した2成果物として出力する。中央との違い＝場ごとのクラス階梯・転入/移籍馬を観点N「クラス格・転入換算」で共通ランクに正規化して地力比較の第一軸にする。市場（オッズ・人気）は一切使わず、馬券は人間判断。「大井11Rを分析して」「園田の◯◯を分析」「(地方の出走表貼り付け)を分析」で起動。中央（JRA）は /analyze-race。
---

# analyze-race-nar — 地方競馬（NAR）予想オーケストレータ

**手順の正本は `/analyze-race`**（`../analyze-race/SKILL.md`）。STEP1〜6・Workflow 骨子・CREED・完全性ゲート・
STEP5 の必須4コマンド・STEP6 当日可変は**そのまま実行**し、このファイルに書いた **NAR 差分だけを上書き適用**する（DRY＝手順を複製しない）。
不変則（市場ゼロ・%禁止・表中心・2成果物…）も同一（`.claude/rules/harness-invariants.md`）。

NAR 固有の references/（このスキル配下）:
- `nar-class-ladder.md` — **クラス階梯カタログ（観点Nの正本）**: 場ごとの階梯・共通ランクR・転入/移籍の換算原則（半静的・レビューで較正）
- `nar-course-geometry.md` — **NAR コース形状カタログ**（D/E/展開合成の正本。数値△は lazy 確定＝初回分析時に該当場だけ web 確認）

共用（`../analyze-race/references/` をそのまま使う）: `research-protocol.md`・`pace-synthesis.md`・`scoring-model.md`・
`output-template.md`・`pedigree-catalog.md`・`stable-intent-rubric.md`・`debut-catalog.md`（認定新馬時）。

## NAR 差分

### 差分1. STEP1 核データ収集（スクレイパ経路が無い）

- **`fetch_racecard.py` は JRA 専用＝使わない**。出走表は **keiba.go.jp 公式出馬表**（確実）→ nankankeiba.com（南関の馬柱）・楽天競馬 → ユーザー貼り付け、の順でフォールバック。**オッズ・人気は取得しない**。
- `出走表.md` に **所属列（大井/船橋/JRA/兵庫…）とクラス表記（レース条件の「C1二」等・混合なら全表記）を必ず立てる**＝観点Nの核データ（東京ダービーの `所属` 列形式を標準とする）。
- **最小 seed.json を手動整形して保存する**（`fetch_racecard race --json` と同形: `horses[]` に no/name/waku/性齢/斤量/騎手/trainer、分かる範囲で `style`/`ten_speed`/`recent[]`(date/venue/pos/field/first_corner)）。下流（assemble_report・inject_probs・risk_flags）がこれを読む。web で崩れず取れた範囲だけでよい＝欠損は中立フォールバックが効く。
- `risk_flags.py` は seed の `recent[]` が埋まった場合のみ実行（薄ければスキップ＝obs-i が web で代替）。`weight_adjust.py` は `出走表.md` から従来どおり実行（NAR はほぼ全て砂＝ダート扱い）。`fetch_oikiri.py`（競馬ブック）は NAR 非対応＝F を起動する場合も seed 無し `[]`。
- 締切確認・確定材料の先取り（I6）・当日参考Rの特定は正本どおり（当日カードは keiba.go.jp で特定）。
- `race-id` の場トークン（romaji・0埋め2桁は不変）: `monbetsu`(門別) `morioka`(盛岡) `mizusawa`(水沢) `urawa`(浦和) `funabashi`(船橋) `ooi`(大井) `kawasaki`(川崎) `kanazawa`(金沢) `kasamatsu`(笠松) `nagoya`(名古屋) `sonoda`(園田) `himeji`(姫路) `kochi`(高知) `saga`(佐賀)。この集合は `tools/inject_probs.py NAR_VENUES` とミラー＝増やす時は両方直す。

### 差分2. STEP2 観点セット（N を必ず入れる）

- **既定（深掘り）= 9観点 `A,B,C,D,E,G,I,K,N`**。**N（クラス格・転入換算）は NAR 必須**＝JRA で seed の `class_rank`/`class_move` が機械でやっていた仕事の代替であり、混合戦・転入馬の格を1軸に正規化する。
- **F（調教）・H（気配）・L（リピーター）は任意追加**: 南関・ダートグレードなど情報が厚いレースだけ足す（それ以外の場は web に調教/気配情報がほぼ無く空振りになる＝取れなければ確信度「低」で潰さない）。
- **速報モード = 6観点 `A,B,D,E,I,N`**（正本の5観点＋N。web 1バッチ厳守等の締切条項は正本どおり）。
- **認定新馬・フレッシュ（過去走ゼロ）= `C,E,F,I,K,M` ＋ N**（JRA 新馬モード準用。N は転入がないため出自地区の2歳戦水準の読みだけ＝軽い）。
- **K（騎手）は絞る場合も残すことを強く推奨**: 地方は騎手の寡占度が JRA より高く（リーディング上位と下位の差が大きい）、乗替の意味も重い。

### 差分3. STEP3 spawn 注入の差し替え（Workflow 骨子は正本を流用）

- `AGENT_OF` は正本の map に **`N:'obs-n-class'`** が定義済み＝NAR は points に N を入れるだけ。
- **N への注入**: `nar-class-ladder.md` の該当場の階梯行＋共通ランクR表＋換算原則（カタログ内は再調査しない・web は各馬の現級/転入元の確定だけ）。
- **D/E/展開合成への注入**: コース形状は `nar-course-geometry.md` の該当場行＋NAR共通の展開原則（JRA の course-geometry.md ではなく）。△暫定値の場を初めて分析する時は、D の web 調査で数値を確定しカタログに追記（lazy 確定）。
- **血統カタログ・厩舎 rubric は共用**（NAR 種牡馬がカタログ外なら従来どおり追記候補で報告）。
- **全観点への NAR 注記を CREED に1行追記**: `# NAR: 地方競馬＝webの情報量が中央より薄い。取れない項目は即「不明」+確信度「低」で確定し、seed・カタログ・核データで埋める（穴埋めの追加検索をしない）。所属・クラス表記を馬の同定に必ず使う（同名馬・移籍で取り違えない）。`

### 差分4. STEP4a/4b 合成の NAR 原則

- **展開合成**: `nar-course-geometry.md` の共通原則を骨格に＝小回り短直線は**前残り系を本線側に置くバイアスから出発**し、崩れる条件（先行過多・ハイ消耗・転入テン速馬の乱入）を明示的に探す。テンのダッシュ力（行き脚）の重みを中央より上げて読む。
- **着順合成**: **N の共通ランクRを地力比較の第一軸**にする（率でも `profile:"nar"` が base に N を組み込む＝scoring-model.md v4.7）。転入初戦の割引・2〜3戦目の巻き返しは N の pros/cons から展開列・懸念点へ転記。
- 2c〜2d の印規律・intent・展開列・パターン別おすすめ馬表は正本どおり。**＋NAR 印規律（2026-07-10 川崎レビュー由来・正本 2c2〜2c4 に追加適用）**:
  - **格の床**: N が格上位（共通ランクRがレース中心+1以上）とした馬を、減点系（下降基調・久々・転入初戦）だけを理由に**無印にしない**＝最低「注」で相手圏に残す（`nar-class-ladder.md` 換算原則7の印側。根拠: 水沢10R⑧無印→3着・川崎10R③無印→2着・川崎12R⑧注→3着の3レース再発）。
  - **◎のロバスト宣言禁止**: cons に発火型リスク（休み明け・初距離・大幅昇級・自建パターンの死角）を書いた馬に「全パターン◎」を与えない＝最低1パターンは△以下に落とし、2c3 の (a)ティア上げ or (b)印下げを必ず実行（根拠: 0617川崎11R⑩◎→9着・0709川崎10R⑥◎→11着・0709川崎7R⑥◎→6着＝cons発火3連発）。NAR平場（B/C級）は休み明け・状態変動の振れが中央より大きい前提で読む。
  - **前残り実現側の検算（監視中）**: 本線/対抗が前残り系のとき、内枠先行の△を一段上げる検算を必ず行い、◯を差し馬に置くなら 2c4 の「展開不問」根拠を明記（0616川崎②△→2着・0709川崎12R③△→2着＝2例。3例目で規律に昇格）。

### 差分5. STEP5 出力（nar フラグ）

- **report.json に `"nar": true` を必ず持たせる**＝`inject_probs.py` が NARプロファイル（`profile:"nar"`・base N/B/A/C）で率を注入する（race-id の場トークンでも自動判定されるが明示が確実）。
- 必須4コマンド（inject_probs → validate_report → validate_research_bundle → project_predictions）・keiba-web 閲覧は正本どおり（validator は観点ID非依存＝N でそのまま通る）。

## 注意

- 市場ゼロ・買い目なし・%禁止（率2カラム例外）は中央と完全に同一。EV/選別/配当の隔離レイヤー（I1-S/R/E）も同じ壁で使える（fetch_odds の JRA 経路が使えない場は `paste` 経路）。
- NAR コーパスの較正はゼロから＝率の参考精度は中央より更に低い旨が header_notes に自動付記される。レビュー（/review-prediction）は共通＝換算外れは `nar-class-ladder.md`、展開外れは `nar-course-geometry.md`／pace-synthesis が修正先。
