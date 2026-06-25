---
name: analyze-race
description: 競馬レースを観点別の並列web調査で分析し、全証拠を突き合わせて複数の展開パターン（確率付き）を合成、各パターンで条件づけた着順分布を出力する。展開予想と着順予想を独立した2成果物として提示。市場（オッズ・人気）は一切使わず、馬券は人間判断。「◯◯レースを分析して」「<netkeiba URL>を分析」「(出走表貼り付け)を分析」で起動。
---

# analyze-race — 競馬予想オーケストレータ（展開予想＋着順予想エンジン）

観点ごとに web 調査サブエージェントを**並列起動**して証拠を集め、それを束ねて**展開パターンを合成**し、
**展開予想（成果物1）と着順予想（成果物2）**を出力する。モデル哲学とデータ配置は repo ルートの `CLAUDE.md` 参照。

> **市場ゼロの原則**: オッズ・人気・他人の予想（専門紙の印・予想展開記事）は**証拠にもログにも一切使わない**。
> 予測は馬の内在情報のみで完結する。
>
> **論理ファーストの原則（v5.0）**: ユーザーは**表しか見ない**。レポートに **% は出さない**（発揮能力・1着率・条件付き%等は撤廃）。
> 着順の並びは**論理**（相変位再帰の因果＝序盤A_early→中盤A_cruise→終盤A_finish）で決め、**印 ◎◯▲△× と行順**で強弱を伝える。
> 数字の代わりに **展開感度・好材料・懸念点（観点タグ＋なぜそう読んだか）** を厚く書く。`tools/score_race.py` は**任意のサニティチェック**（並びの整合確認）に降格。

参照ファイル（このSkillの references/）:
- `observation-points.md` — 観点カタログ（10/7/5観点）と因子マッピング、純粋情報の原則
- `research-protocol.md` — 各観点の調査手順・推奨ソース・出力スキーマ（E は PACE_EVIDENCE_SCHEMA）
- `pace-synthesis.md` — **STEP4a 展開合成**の手順・矛盾解決・複数パターン構築・段階フロー（phase_flow）・当日可変
- `scoring-model.md` — **相変位再帰の因果骨格**（相別能力 A_early/cruise/finish/class → 3相再帰）の定義。v5.0 で**並びのサニティチェック**に降格（%の正本ではない）
- `output-template.md` — **出力契約（report.json スキーマ）の正本**（§0-§4 の構造化・I2 %禁止）＋ jsonl 投影と web レンダリングの不変則
- `course-geometry.md` — **コース物理形状の静的カタログ**（直線長・坂・初角特記。D/E/展開合成の正本＝web再調査しない）
- `pedigree-catalog.md` — **血統カタログ**（種牡馬の父/母父傾向・決め手の質・巻頭原則。C の正本＝半静的・年1更新）
- `stable-intent-rubric.md` — **厩舎の勝負気配傾向**（3次元の型ラベル＝仕上げ型/追い切り常態/騎手起用）の定義＋lazy catalog。F/K が `intent` の"普段の基準"に使う（半静的・有料DB不要・総合力とは独立）

## 手順

### STEP 1. レース特定 & 核データ収集

> **締切確認（最初に必ず／馬券は発走で締め切る）**: レースを特定したら**発走時刻と現在時刻を確認**し、残り時間をユーザーに告げて**深掘り(11/7観点・約20〜25分)か速報(5観点・約5〜8分)かを提案する**（モードは毎回その場で選ぶ＝自動切替しない）。`fetch_racecard.py day` 出力に `post_time` がある。間に合わない深掘りを黙って走らせない＝**速度は精度の前提**。選んだモードを STEP2 に渡す。

入力（レース名 / URL / 貼り付け出走表）からレースを特定し、以下を集める：
- レース名・日付・競馬場・距離・コース（芝/ダ・回り）・馬場状態・頭数
- **出走表**（馬番・馬名・性齢・斤量・騎手・**調教師**・脚質・前走）＝調教師は核データ（勝負気配の厩舎基準・将来の厩舎catalog結合キー。NARは手動出走表に列を立てる＝関東オークスの `所属(厩舎)` 形式を標準化）

**まず `python3 tools/fetch_racecard.py race <race_id> --class=<クラス> --json` で核を取得**。取得は **JRA優先→競馬ラボ自動フォールバック**
（`source` フィールドで判別。仕様は `references/scraping.md`）。WebFetch が WAF/JS で弾かれ小型モデルが捏造する箇所を決定論的に置換。
- **`--class=<クラス>`**（例 `--class=3歳上1勝クラス`）でレースのクラスを渡すと、seed に `race_class_rank` と各馬の **昇降級デルタ `class_move{last,top,vs_current}`**（過去走 `recent[].class_rank` 由来）が機械的に付く＝観点Bが昇降級を読み直さず内容に集中できる。JRA経路は title 無しなので**渡し必須**（競馬ラボ経路は title から自動）。クラスが不明なら省略可（rank=null・obs-b が web 確定）。
- **JRA経路**（今週開催）: 馬名・性齢・斤量・騎手・血統(父母父)・枠/馬番・**前走通過順由来の精密脚質**まで1ページで揃う＝web調査の負担が大きく減る。
- **競馬ラボ経路**（過去/未来週・JRA障害時）: 馬名・脚質傾向(粗)・血統・枠/馬番。性齢・斤量・騎手・前走は web 調査で補う。
**両ソースとも非ゼロ終了したら** WebFetch → ユーザー貼り付けにフォールバック。
**オッズ・人気は取得しない**（市場は使わない）。
**取得が不確実 or 曖昧なら、ここでユーザーに URL 指定か貼り付けでの補強を依頼する**
（出走表は崩れやすい核データなので無理に推定しない）。

`race-id` を `YYYYMMDD-開催-レース番号` で決め、
`data/races/<race-id>/出走表.md` に整形保存する（全馬リスト＋レース条件。オッズ列は持たない）。

**追い切り好時計 seed の取得（観点F用・今週開催のみ）**: ここで **`python3 tools/fetch_oikiri.py week --json` も実行**し、出力を STEP3 で F に `oikiri` として渡す（配線は下記 Workflow 骨子）。
**全頭でない好時計の上位抜粋**＝対象馬が載れば一次事実、不在馬は F が web 補完（不在≠調教不良）。**非ゼロ終了（今週外・ページ変化）なら空 `[]` で渡し、F は全頭 web 調査**にフォールバック（スクレイパは fast-path であって必須依存ではない）。`--date <M/D>` で出走日に絞れるが、リストは小さいので既定は週全部でよい（F が馬名で突合）。

**確定材料の先取り（点②／§0 後付けにしない）**: ここで **枠順・乗替・回避（出走取消）が確定済みか**を判定する。
- **確定済みなら核データとして取り込み**、research エージェントと STEP4a/4b・§2-1/§2-2/§3 本文に**最初から織り込む**（脚質分類への内/外割当て・枠トリップ補正・先行争いの再評価をこの時点で実施）。
  `fetch_racecard.py` 出力で枠/馬番が出ていれば枠は確定とみなす。**完成レポートに後付けして再実行する無駄を避ける**。
- **未確定（数日前の分析で枠未発表 等）なら**、その項目だけ §0 ボードに「当日記入」で残す。
- 当日の馬場・クッション値・含水率・パドック・馬体重・前半参考Rの観察値は**常に当日記入**（分析時点では本質的に未知）。

**当日の参考レース特定（§0-1 用）**: 本命は後半R（11R 等）が多く、前半Rは当日バイアスの採取に使える。
**`python3 tools/fetch_racecard.py day <YYYYMMDD> <場2桁> --json` で当日カードを取得**（WebFetch より確実。場コードは `references/scraping.md`）し、
対象レースと**条件が一致する前半Rを名指しで拾う**。
一致の優先順位は **芝/ダート（必須）＞ 同日・時間帯（必須・直前ほど重い）＞ 回り内外・右左 ＞ 距離帯**
（芝/ダは絶対に混ぜない。回り・距離は近いもので代用し割引）。
R番号・発走時刻・コースを §0-1 の表に埋める。カードが取れなければ一致基準だけ記し「当日特定」と注記。

### STEP 2. 観点モードの決定

`observation-points.md` に従い、**STEP1 で選んだ深掘り/速報**と頭数・情報量で観点数を決める（既定 11 観点 A〜I, K, L。市場Jは無い）。**速度・トークン優先＝web情報が薄い/少頭数のレースは迷ったら絞る側に倒す**：

**速報モード（締切が迫る・ユーザーが速報を選択）＝最優先で壁時計を切り詰める**：
- **観点は 5 個固定 `A,B,D,E,I`**（時計・近走・適性・展開証拠・リスク＝**並びを作る核だけ**。F調教/H気配は無料web範囲で実測が取れず低寄与、G/K/L は当日補強に回す）。
- **web は1観点あたり 1 バッチ厳守**（CREED の deadline 条項。超過は打切る）。研究 subagent は**軽量モデル**で起動（`opts.model:'sonnet'`＝収集は機械作業。合成は据え置き）。
- 落とした F/G/H/K/L は §4 と当日ボードで「補強で取得」と明示。STEP4a 展開合成は**省かない**（速報でも2成果物の独立は維持）。
- 主要ボトルネックは **web 往復回数と観点数**（モデルは副次）。まず観点を5に・バッチを1に絞ることで壁時計が効く。

**深掘りモード（時間に余裕・既定）**：
- 多頭数(14〜18) / GⅠ等の情報が厚いレース → **11 観点**（A〜I, K, L 全部）
- 標準(10〜13頭) → **7 観点**
- 少頭数(〜10) / 情報が薄い → **5 観点**

騎手の乗り替わりが鍵になるレース（主戦離脱・強化乗り替わり・テン乗り多数）では、
観点数を絞る場合でも **K を単独観点として残す**ことを推奨（速報でも K を足し 6 観点にしてよい）。
リピーター色の濃いレース（ハンデ重賞・季節レース・同舞台の重賞・高齢馬多数）では同様に **L を残す**ことを推奨（下級条件・若馬戦では L は省いてよい）。
**いずれのモードでも STEP4a 展開合成は必ず実施する。**

### STEP 3. 証拠ファンアウト（Workflow）→ 展開合成

観点ごとに調査サブエージェントを**並列起動して証拠を集め**（Research フェーズ）、
全証拠が出揃ってから**展開合成を1回だけ走らせる**（PaceSynthesis フェーズ）。
多数のエージェントを使う重い処理なので **Workflow ツールで実行**する。**各観点は専属 subagent**（`.claude/agents/obs-<id>.md`、agentType＝`obs-a-index`…`obs-k-jockey`）＝**ペルソナ・調査手順・推奨ソース・スコア指針はその agent 定義に内蔵**。Workflow が各 subagent に渡すのは**データと共通鉄則だけ**：
- `出走表.md` の全馬リスト＋レース条件（**オッズは渡さない**）
- **スクレイパ seed**（STEP1 の `fetch_racecard.py` 出力）。JRA経路なら 脚質(通過順由来の精密)・テン速・血統(父母父)・枠/馬番・性齢・斤量・騎手・**h2h直接対戦**・**クラス序列タグ（`recent[].class_rank`／各馬 `class_move`／`race_class_rank`＝昇降級が機械判定済み・観点B用）**、競馬ラボ経路なら脚質傾向(粗)・血統・枠。観点E/C/B はこれを **検証・補強**し、ゼロから取り直さない（`references/scraping.md`）
- **コース物理形状**（`references/course-geometry.md` の該当コース行＝直線長・坂・初角特記）。D/E/展開合成はこれを正本とし **web で再調査しない**
- **血統カタログ**（`references/pedigree-catalog.md` の出走馬の父・母父に該当する行＋巻頭原則）。C はこれを正本とし**カタログにある血は web 再調査しない**（外の血だけ調査・追記候補で報告）
- **追い切り好時計 seed**（`python3 tools/fetch_oikiri.py week --json`＝競馬ブック好時計ランキング）。F に渡す。**全頭ではない上位抜粋**＝対象馬が載れば一次事実、不在馬は F が web 補完（不在≠調教不良）
- 出力スキーマ（`research-protocol.md` 末尾。**観点E は PACE_EVIDENCE_SCHEMA**で生証拠のみ）＋共通鉄則（全馬漏れなく／出典必須／捏造しない／純粋情報のみ）

> **DRY と純粋性の正本**: subagent は `.claude/rules` を自動ロードしない別コンテキスト。よって**純粋性・スキーマ・全馬規律はこの spawn 時注入が正本**（各 agent 定義は再掲せず1行リマインダのみ持つ）。観点を**1つ調整したい**ときは触るのは `.claude/agents/obs-<id>.md` だけ（[editing-map](../../rules/editing-map.md)）。

各 subagent は web 調査の上、**全文prose は生成せず**（未読のため廃止）、スキーマの構造化要約を `data/races/<race-id>/research-<観点ID>.json` に保存し、同じ要約を返す。
その後、**PaceSynthesis エージェント**が全証拠（E の脚質・先行争い、B の近走脚質、D のバイアス、K の騎手の出方、
関係者コメント、出走表の枠）を突き合わせ、`pace-synthesis.md` に従って **複数の名前付き展開パターン**（PACE_MODEL）を作る。

Workflow スクリプトの骨子（Research 並列 → バリア → PaceSynthesis）：

```js
export const meta = {
  name: 'race-fanout-and-pace',
  description: '観点ごとに専属 subagent を並列起動して証拠をweb調査し、全証拠を突き合わせて展開パターンを合成する',
  phases: [{ title: 'Research' }, { title: 'PaceSynthesis' }],
}
// args = { raceId, condition, horses, field_size, expected_nos, seed, pedigree, course, oikiri, stable, points:[{id}], mode }  ※ odds は渡さない
//   mode = '速報' | '深掘り'（STEP1 の締切確認で選択）。速報は points=[A,B,D,E,I]・web1バッチ厳守・研究agentを軽量モデルで起動（合成は据え置き）
//   expected_nos = 全出走馬の馬番配列（fetch_racecard seed 由来）。合成前ゲートの exact set 一致用（別馬混入も止める）
//   stable=厩舎の勝負気配傾向 rubric＋該当厩舎の型ラベル行(stable-intent-rubric.md・F/K用)。無ければ暫定ラベルを当て追記候補で報告
//   pedigree=血統カタログ該当行(C用) / course=コース形状該当行(D,E用) / oikiri=追い切り好時計seed(F用)。カタログ内は再調査しない
//   観点の手順/ソース/スコア指針は .claude/agents/obs-<id>.md（subagent）に内蔵。ここで渡すのはデータ＋共通鉄則のみ
//   seed = fetch_racecard.py の race 出力（脚質傾向・血統・枠/馬番）。E/C/B は seed を検証・補強する

// 観点ID → 専属 subagent（.claude/agents/）。STEP2 で選んだ観点だけ points に入れる
const AGENT_OF = { A:'obs-a-index', B:'obs-b-recent', C:'obs-c-pedigree', D:'obs-d-aptitude', E:'obs-e-pace',
                   F:'obs-f-training', G:'obs-g-rotation', H:'obs-h-paddock', I:'obs-i-risk', K:'obs-k-jockey',
                   L:'obs-l-repeater' }

const RESULT_SCHEMA = { /* point, overall_confidence, field_note, horses:[{no,name,pros,cons,score(-2..+2 / Iは0..-2),confidence,sources}], note */ }
const PACE_EVIDENCE_SCHEMA = { /* legs:[{no,name,style,ten_speed,expected_pos}], lead_contenders:[{no,stance}], draw:[{no,note}] */ }  // 馬場バイアスは D が返す（E から一本化）
const PACE_MODEL_SCHEMA = { /* patterns:[{id,name,prob,likelihood_tier(本線/対抗/伏線),trigger,first_600m,pace_level,leg_advantage,formation_head,formation_last_corner,bias,phase_flow:{early,mid,late,result},per_horse_fit}], falsification, field_note */ }

// 全 subagent 共通の鉄則（純粋性・規律）。観点固有のペルソナ/手順は agent 定義側にあるのでここでは渡さない
const CREED =
  `# 鉄則（全観点共通）\n` +
  `- 対象は全出走馬、漏れなく（＝完全性。「1頭ずつ」は漏らさず全頭の意味であって、直列に1頭ずつ調べる意味ではない）。馬番・馬名を必ず明記。\n` +
  `- 出典URL必須。推定は「推定」と明記し確信度を下げる。捏造しない＝取得できない項目は欠損として確信度「低」。\n` +
  `- 純粋情報のみ: オッズ・人気・オッズ変動・他人の予想/印/予想展開記事は使わない。関係者コメント・媒体の主観評価(調教/パドック点)は採用可。\n` +
  `- 市場語（人気・オッズ・配当・払戻）は research JSON に1文字も書かない＝事実の引用でも『N番人気で差し切り』のように書かない（『後方から差し切り』等に言い換える）。『市場を除外した』旨の宣言文も書かない（STEP5 で機械スキャンする＝I1）。\n` +
  `# 調査の進め方（並列・直列禁止＝壁時計短縮）\n` +
  `- 全頭を1頭ずつ直列に検索しない。同種クエリは1ターンにまとめて並列発行（1メッセージ内に複数の WebSearch/WebFetch を同時に出す）。各クエリ・各抽出値に馬番＋馬名を必ず紐付け取り違えない。\n` +
  `# 速度・トークン予算（カバーは必須・深さは可変）\n` +
  `- 全頭が出力に載ること（カバー）は必須。だが全馬を同じ深さで web 検索しない＝seed・静的カタログ・核データで判断できる馬は再検索せず seed 値のまま評価する。\n` +
  `- web は原則 WebSearch 2バッチ＋WebFetch 1バッチ以内（1バッチ=最大6頭並列）。重賞など情報が厚い時だけ +1バッチ。穴埋め目的の追加検索を続けない。\n` +
  `- 追加 web で深掘りするのは次の馬だけ: ①seed と矛盾 ②展開トリガー(逃げ/ハナ主張/控え) ③上位印 or pattern_fit ◎○△ 候補 ④強い加点/減点(休み明け・乗替・故障明け・初条件) ⑤静的カタログ外で判断に必要。\n` +
  `- 1頭あたり出典URLは原則2件(重要馬3件)。pros/cons は各馬1〜3件・下流で使う事実だけ。取得不能は「不明」+確信度「低」で止める。`

// 速報モードの追加鉄則（締切優先＝壁時計を最短化）。深掘りでは空文字＝従来どおり。
const DEADLINE_CAP = (args.mode==='速報')
  ? `\n# 速報モード（締切優先・最優先で守る）\n` +
    `- web は WebSearch 1バッチのみ（最大6頭並列×1回）。WebFetch は本当に要る重要馬のみ最小限。穴埋めの追加検索は一切しない＝seed/核データ/静的カタログで埋める。\n` +
    `- 取れない項目は即「不明」+確信度「低」で確定し次へ。完璧さより締切。カバー(全頭出力)だけは死守。`
  : ``

// 合成入力用の TOON エンコーダ（決定論・出力側＝一方向で壊れない／schema検証は agent 側で完了済）。
// uniform な per-horse 配列をヘッダ1回＋"|"区切り行で表現＝JSON のキー反復を畳み、合成入力のトークンを削減。
function toToon(results){
  return results.map(r=>{
    if(!r) return ''
    if(Array.isArray(r.legs)) return `## E pace-evidence\n`+JSON.stringify(r)  // E は小さいのでそのまま
    const head = `## ${r.point||'?'} (conf:${r.overall_confidence||''})${r.field_note?(' note:'+r.field_note):''}\n`
    const rows = (r.horses||[]).map(h=>[h.no,h.name,h.score,h.confidence,
        (h.pros||[]).join(';'),(h.cons||[]).join(';'),(h.sources||[]).join(',')].join('|')).join('\n')
    return head+`no|name|score|conf|pros|cons|sources\n`+rows
  }).filter(Boolean).join('\n\n')
}

// --- Phase 1: 全観点を専属 subagent で並列収集（E だけ証拠スキーマ）---
// dispatch は重い順（per-horse fetch が多い順）に並べる＝cap=8 の wave1 に重い観点、軽い K/G/I を後方へ。
const HEAVY_ORDER = ['A','B','D','L','H','F','C','E','K','G','I']
const ordered = [...args.points].sort((a,b)=> HEAVY_ORDER.indexOf(a.id) - HEAVY_ORDER.indexOf(b.id))
const runOne = (p) => agent(
    `# レース条件\n${args.condition}\n\n# 出走馬（全頭）\n${args.horses}\n` +
    // E(脚質)・C(血統)・B(近走脚質) は seed を起点に検証・補強する
    (['E','C','B'].includes(p.id) ? `\n# スクレイパ seed（検証・補強の起点／ゼロから取り直さない）\n${JSON.stringify(args.seed)}\n` : ``) +
    // C は血統カタログ該当行、D/E はコースカタログ該当行、F は追い切り好時計 seed を渡す（カタログにある分は再調査しない）
    (p.id==='C' ? `\n# 血統カタログ該当行（pedigree-catalog.md・カタログ内は再調査しない）\n${args.pedigree||''}` : ``) +
    (['D','E'].includes(p.id) ? `\n# コース物理形状（course-geometry.md 該当行）\n${args.course||''}` : ``) +
    (p.id==='F' ? `\n# 追い切り好時計 seed（fetch_oikiri.py・好時計の上位抜粋＝全頭でない。不在馬はweb補完）\n${JSON.stringify(args.oikiri||[])}` : ``) +
    // F/K は厩舎の勝負気配傾向 rubric＋該当厩舎の型ラベルを受け取り、intent の"普段の基準"に使う（無ければ暫定ラベルを追記候補で報告）
    (['F','K'].includes(p.id) ? `\n# 厩舎の勝負気配傾向（stable-intent-rubric.md・型ラベル＝仕上げ型/追い切り常態/騎手起用。catalog外は暫定＋追記候補で報告）\n${args.stable||''}` : ``) +
    `\n${CREED}${DEADLINE_CAP}\n- **全文prose は生成・保存しない**（未読のため廃止）。スキーマの構造化要約を data/races/${args.raceId}/research-${p.id}.json に保存し、同じ要約を返す。`,
    // 速報は研究agentを軽量モデルで起動（収集は機械作業＝壁時計優先）。合成(PaceSynthesis)は据え置き＝推論の核。
    { label:`research:${p.id}`, phase:'Research', schema: p.id==='E'?PACE_EVIDENCE_SCHEMA:RESULT_SCHEMA, agentType: AGENT_OF[p.id],
      ...(args.mode==='速報' ? { model:'sonnet' } : {}) }
  )
let research = (await parallel(ordered.map(p => () => runOne(p).then(r=>({p,r})).catch(()=>({p,r:null})))))
                 .filter(x => x.r)   // ← await 完了が暗黙バリア

// --- 完全性アサーション（恒久ガード＝取りこぼし検出）。非E=horses, E=legs が「配列・行数=field_size・各行の no が int・重複なし」を満たすか。
// 旧実装は length だけ見ていたが、馬番重複・別馬混入・no欠損だと壊れた TOON が合成に渡る（行数N でも distinct な馬番が足りない）。
// distinct な int no 数 と 行数 の両方を見る。workflow は fs 不可なので「返却データの全頭カバー」までを合成前に見る（ファイル保存自体は STEP5 の validate_research_bundle が担保）。
const EXP = new Set(args.expected_nos || [])   // 全出走馬の馬番集合（あれば exact 一致まで見る）
const covInfo = (r, id) => {
  const a = id==='E' ? (r && r.legs) : (r && r.horses)
  if (!Array.isArray(a)) return { ok:false, n:-1, why:'配列なし' }
  const s = new Set()
  for (const x of a) { const no = x && x.no; if (Number.isInteger(no)) s.add(no) }
  // exact set 一致（expected_nos があれば別馬混入99も止まる）。無ければ size で代替。
  const setOK = EXP.size ? (s.size === EXP.size && [...EXP].every(n => s.has(n))) : (s.size === args.field_size)
  const ok = a.length === args.field_size && setOK
  const why = ok ? '' : (EXP.size
      ? `馬番集合不一致(行数${a.length} 欠け=${[...EXP].filter(n=>!s.has(n))} 余分=${[...s].filter(n=>!EXP.has(n))})`
      : `行数${a.length}/有効馬番${s.size}≠${args.field_size}(重複/非int/欠落)`)
  return { ok, n:s.size, why }
}
for (const x of research) {
  const c = covInfo(x.r, x.p.id)
  if (!c.ok) {
    log(`不完全 ${x.p.id}: ${c.why} → 1回再促し`)
    const r2 = await runOne(x.p).catch(()=>null)
    if (r2 && covInfo(r2, x.p.id).n >= c.n) x.r = r2
  }
}
// --- 欠落ゲート（P6対策・PaceSynthesis前の必須チェック）: parse失敗等で落ちた観点を本体内で同期リトライ ---
// `.filter(x=>x.r)` は失敗を黙って落とすため、ここで「期待観点セット − 返ってきた観点」を欠落として検出し、
// 本体内で1回だけ再起動（P2: 本体完了後の直列再取得でなく合成前に回収）。それでも欠落なら必ず log で明示して縮退（黙って進めない）。
{
  const expected = ordered.map(p => p.id)
  const got = new Set(research.map(x => x.p.id))
  let missing = expected.filter(id => !got.has(id))
  if (missing.length) {
    log(`欠落観点 ${missing.join(',')} → 本体内で同期リトライ`)
    const retried = await parallel(missing.map(id => () => runOne({id}).then(r=>({p:{id},r})).catch(()=>({p:{id},r:null}))))
    for (const x of retried) if (x.r) research.push(x)
    missing = expected.filter(id => !new Set(research.map(x => x.p.id)).has(id))
    // 必須停止: リトライ後も欠落＝部分証拠での合成を中止（黙って進めない・合成トークンも浪費しない）。
    // 当該観点を再取得してから resume（Workflow resumeFromRunId で成功分はキャッシュ再利用）。
    // ※どうしても縮退合成するなら、ここを throw でなく missing を合成プロンプト＋report header_notes に明示する形に置換する（既定は停止）。
    if (missing.length) throw new Error(`欠落観点 ${missing.join(',')} がリトライ後も解消せず＝部分証拠での合成を中止（必須停止）。当該観点を再取得して resume すること`)
  }
  // 完全性の必須停止: 返ってきたが不完全（行数≠field / 馬番重複 / 別馬混入 / no欠損）な観点があれば、壊れた証拠なので合成しない（合成トークンを浪費しない）。
  // ※ファイル保存自体（返却はあるが research-X.json 未保存）は workflow に fs アクセスが無いため見られない＝STEP5 の validate_research_bundle で担保する。
  const incomplete = research.filter(x => !covInfo(x.r, x.p.id).ok)
                            .map(x => `${x.p.id}:${covInfo(x.r, x.p.id).why}`)
  if (incomplete.length) throw new Error(`不完全な観点 ${incomplete.join(', ')} がリトライ後も解消せず＝壊れた証拠での合成を中止（必須停止）。当該観点を再取得して resume すること`)
}
const researchResults = research.map(x => x.r)

// --- Phase 2: 展開合成（複数パターンを1回だけ構築）---
const paceModel = await agent(
  `あなたは展開合成器。pace-synthesis.md に従い、以下の全証拠を突き合わせ、全馬の配置から創発する` +
  `複数の名前付き展開パターン（確率＋発動トリガー＋脚質別有利不利＋隊列＋段階フロー phase_flow）を構築せよ。Σprob=1。` +
  `各パターンに phase_flow{early,mid,late,result} を「序盤→A_early→中盤→A_cruise→終盤→A_finish→結果」の因果文で必ず著作する。` +
  `関係者の戦法宣言＞推測、近走の実脚質＞一般ラベル、先行争いが不確実なら別パターンに分岐。\n` +
  // 全証拠は決定論 TOON で渡す（合成入力のトークン削減・読み手は合成器=LLM）
  `# 全証拠(TOON)\n${toToon(researchResults)}\n# 条件\n${args.condition}`,
  { label:'pace-synthesis', phase:'PaceSynthesis', schema: PACE_MODEL_SCHEMA, agentType:'general-purpose' }
)
return { research: researchResults, paceModel }
```

> Workflow が使えない/重すぎる場合のフォールバック: `Agent` ツールで各観点の subagent（`subagent_type: obs-<id>`）を1メッセージ内に並列起動し（観点の手順は agent 定義が持つので渡すのはデータ＋共通鉄則＋schema のみ）、
> 返り（バリア相当）を待ってから、メイン文脈で `pace-synthesis.md` に従い展開パターンを合成する。

### STEP 4a. 展開合成（成果物1）

`pace-synthesis.md` に従い（STEP3 の PaceSynthesis が未実施なら）メイン文脈で、全証拠から
**複数の展開パターン**（可能性ティア・発動トリガー・脚質別有利不利・隊列・**段階フロー phase_flow**・反証条件）を構築する。これが **展開予想**。
- 各パターンに **`phase_flow{early,mid,late,result}`** を著作する＝「序盤→A_early→中盤→A_cruise→終盤→A_finish→結果」の因果文。これが §2 の段階フロー（1行テキスト）と §3 展開感度の素。
- 報告は確率%でなく **可能性ティア（本線/対抗/伏線）**。内部の `prob` はログにのみ残す（`output-template.md` 参照）。
- **`pace_factors`（展開トリガー早見）を著作する**＝「どの展開が来そうか」をユーザーが判断・当日に再ティアするための材料を race-level で並べる（`{factor, reads, day_check}`。最低限 `先行勢の数と質`／`枠の効き`／`コース形状`／`例年傾向（過去開催）`／`当日で動く点`）。**新規調査はせず**既収集の証拠＋カタログ＋seed から導出。`例年傾向` 行は **`tools/fetch_result.py history <過去開催id…>`** のペース署名を素材に定性で書く（過去idは web 特定・NARはweb補完）。詳細は `pace-synthesis.md`。

### STEP 4b. 着順合成（成果物2 / 論理ファースト・相変位再帰を因果骨格に）

**着順の並びは論理で決める**。各馬を相変位再帰の因果（序盤A_early→中盤A_cruise→終盤A_finish×余力、A_class=地力の変調）で相対比較し、
最有力パターンの phase_flow に沿って **印 ◎◯▲△× と行順**を付ける。**% は出さない**（`scoring-model.md` の相別能力 A_early/cruise/finish/class が並びの論拠の語彙）。手順：

1. 各馬の相別能力の高低を定性で確定（観点評価＋スクレイパの `ten_speed`/`style`/`agari_best`/`recent[]` から）。序盤の速さ（A_early）と終盤の決め手（A_finish）を**別々に**見て、逃げ馬と追込馬を単一尺度で比べない。
2. 最有力パターンの phase_flow に各馬を通し、どの相で浮く/沈むかを **展開感度** に書く。好材料/懸念点を**観点タグ付きで厚く**列挙する。
2b. さらに**§2-2 の全パターン**に各馬を通し、各パターンでの圏内/強弱（`◎`中心/`○`圏内/`△`条件付き、圏外は記載なし）を符号化して §3 の**展開列**に入れる。源は展開合成の `per_horse_fit`・`leg_advantage`・各パターンの浮上/沈む馬（矛盾したら §2-2 を見直す）。これが「想定パターン別に無駄なく箱を組む」ための一目表＝`predictions.jsonl` の `pattern_fit` にも残す。
    あわせて展開列の**転置版「パターン別おすすめ馬」表**（パターン → 中心◎/圏内○/一発△/消し）を **§3 の直前**に置く（体裁は `output-template.md`。源は同じ＝矛盾させない）。
2c. **展開⇔着順の整合ルール（2026-06-07 レビュー由来）**: §2 の `formation_head`/`formation_last_corner`・falsification の分岐点に**馬番を名指しした馬は、必ず rank レコード（印 or 注）の対象に含める**。
    無印で切る場合は「展開には登場するが着順候補から外す理由」を cons に明記する（黙って落とさない）。
    根拠: 展開に載せながら着順候補から外した馬の馬券内が3レースで再発（t11④ formation_head 記載→無印1着・t12⑪「分岐点」名指し→無印2着・h09⑭）。
2d. **勝負気配度（`intent` ↑↑/↑/→/↓）を全馬1頭1記号で確定**＝陣営がこの一戦に賭けているか。**能力・印とは独立**（強い馬の叩き台は `→`/`↓`、人気薄の一変狙いは `↑` も）。源は **F追い切り差分＋K起用方向(`jockey_change`)＋H関係者コメント自信度**を束ねる（**新規調査はしない**＝既収集の証拠から導出＝別ステップ不要）。**% も市場も使わない**。事前(F+K)で確定し、当日 H（パドック気配・直前コメント）で**±1段だけ更新可**（§0当日可変）。記号の基準は `output-template.md` の `intent` 定義。
    差分は**厩舎の型ラベル（`references/stable-intent-rubric.md` の"普段の基準"＝仕上げ型/追い切り常態/騎手起用）で割り引き/増幅**する（フレッシュ型の休み明け=本気↑／叩き型の休み明け=叩き台→ 等）。catalog に該当厩舎が無ければ generic で読み**確信度を下げる**（総合力=勝率は intent に混ぜない）。
3. これらを総合して**並び（印＋行順）を論理で決める**。
4. **任意のサニティチェック**: `python3 tools/score_race.py --in race.json --json`（＋`--self-check`）を回せる場合は回し、その**並び順**が論理の並びと食い違わないか確認するだけ（%は転記しない）。
   食い違ったら**論理側を正**とし、理由を一言残す（食い違いそのものが点検シグナル＝どちらかの読みに穴がある）。`engine_check{order_pos,agree}` をログに残す。

> 相変位再帰の因果骨格・語彙の正本は `scoring-model.md v5.0`（相別能力§2 → 3相再帰§6）。エンジンは並びの整合確認に降格（%の正本ではない）。
> **市場・妙味・EV・Kelly・買い目は無い**（馬券は人間判断）。確信度が低い観点の影響は懸念点に明示する。

### STEP 5. 出力（構造化正本 report.json）& 自動ログ投影

`output-template.md` の **report.json スキーマ**に従い構造化正本を作成し、`data/races/<race-id>/report.json` に保存（**report.md は廃止＝手書きしない**）。
**§2 `pace`（複数パターン＋`phase_flow`＋ティア）と §3 `rank`（全馬・印・`pattern_fit` 展開列・展開感度・好材料/懸念）の2本柱。% は出さない（数値 `prob`/`pace_level` はログ専用＝web 非描画。mermaid・サマリ・観点別ハイライトは持たない）。**
**§0 `day_board` には*分析時点で本当に未知のものだけ*を残す**（確定枠・乗替・回避は `leg_table`/`patterns`/`rank` 本文へ織り込み済み。当日の参考R観察値・馬場・パドック・馬体重のみ空欄）。

書込後に**必須3コマンド**（順に。エラーが出たら直してから次へ）:
1. `python3 tools/validate_report.py <race-id>` — スキーマ＋**I2(%/％)＋I1(市場・予想語=人気/オッズ/配当/払戻/予想印/専門紙/odds/market)**＋**I5 複数パターン必須**＋**全頭カバー（rank=leg_table=field_size・馬番集合一致・int）**のゲート。
2. `python3 tools/validate_research_bundle.py <race-id>` — **`used_observations` と実 `research-<観点>.json` の対応ゲート（P6＝欠落無検知の塞ぎ）**。観点が使われたのに artifact が無ければエラー＝合成が返り値で通っても欠落を検出する。エラーなら欠落観点を再取得 or 保存し直す。
3. `python3 tools/project_predictions.py <race-id>` — report.json から `predictions.jsonl` へ pace/rank を**自動投影**（review-prediction はこの jsonl を読む。源は report.json 一本＝drift 無し）。

人間向け閲覧は **keiba-web（Astro）が report.json をレンダリングした web サイト**で行う。

### STEP 6. 補強の案内 & 当日可変

- 確信度が低かった観点（特に H 当日気配・パドック・関係者コメント）を明示し、
  ユーザーが URL or 貼り付けで補強できることを案内。補強を受けたら該当観点だけ再調査 → 再合成。
- **当日可変**: §0 ボードの当日情報（**前半参考Rで採取したバイアス**・パドック・馬場変化・当日発表の乗替/取消など）を受けたら、
  `pace-synthesis.md` の当日手順で **可能性ティアを付け替える / 1パターンに固定 → 展開感度と並び（印）を論理で再評価**（素の能力読み＝好材料/懸念点は再調査不要）。
  参考Rで「想定と馬場の質が違った」場合のみ観点D適性の読みを部分見直し。エンジンを併用する場合は新しい `prob`/`pace_level` で再実行し並びの整合だけ確認。
  **report.json を更新 → `tools/validate_report.py <race-id>` → `tools/project_predictions.py <race-id> --update`**（`note:"当日更新"` で履歴 append・上書きしない）。

## 注意

- このハーネスは**展開予想と着順予想の精度に全振り**。市場（オッズ・人気・妙味・EV・買い目）は一切持たず、馬券選択は人間が行う。
- 証拠は馬の内在情報のみ（純粋情報の原則）。他人の予想・印・オッズは使わない。
- **論理ファースト**: レポートに % は出さない。並びは論理（印＋行順）、根拠は展開感度・好材料・懸念点（観点タグ）で表す。`score_race.py` は任意のサニティチェック。
- web 取得の信頼性が低い項目は確信度「低」とし、点推定を過信せず懸念点に明示する。
- 展開合成の手順・段階フローは `pace-synthesis.md`、相別能力の因果骨格・語彙は `scoring-model.md` が調整点。ここを書き換えて改善する。
