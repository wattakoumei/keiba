---
name: analyze-race
description: 競馬レースを観点別の並列web調査で分析し、全証拠を突き合わせて複数の展開パターン（確率付き）を合成、各パターンで条件づけた着順分布を出力する。展開予想と着順予想を独立した2成果物として提示。市場（オッズ・人気）は一切使わず、馬券は人間判断。「◯◯レースを分析して」「<netkeiba URL>を分析」「(出走表貼り付け)を分析」で起動。
---

# analyze-race — 競馬予想オーケストレータ（展開予想＋着順予想エンジン）

観点ごとに web 調査サブエージェントを**並列起動**して証拠を集め、それを束ねて**展開パターンを合成**し、
**展開予想（成果物1）と着順予想（成果物2）**を出力する。モデル哲学とデータ配置は repo ルートの `CLAUDE.md` 参照。

> **市場ゼロの原則**: オッズ・人気・他人の予想（専門紙の印・予想展開記事）は**証拠にもログにも一切使わない**。
> 予測は馬の内在情報のみで完結する。

参照ファイル（このSkillの references/）:
- `observation-points.md` — 観点カタログ（10/7/5観点）と因子マッピング、純粋情報の原則
- `research-protocol.md` — 各観点の調査手順・推奨ソース・出力スキーマ（E は PACE_EVIDENCE_SCHEMA）
- `pace-synthesis.md` — **STEP4a 展開合成**の手順・矛盾解決・複数パターン構築・当日可変
- `scoring-model.md` — ability0→パターン条件づけ→着順分布 の計算式と現行重み（v3.0）
- `output-template.md` — 最終レポートの体裁（2成果物）と predictions.jsonl の2レコード形式

## 手順

### STEP 1. レース特定 & 核データ収集

入力（レース名 / URL / 貼り付け出走表）からレースを特定し、以下を集める：
- レース名・日付・競馬場・距離・コース（芝/ダ・回り）・馬場状態・頭数
- **出走表**（馬番・馬名・性齢・斤量・騎手・脚質・前走）

WebSearch / WebFetch で取得。`netkeiba` の出走表ページが基本ソース。
**オッズ・人気は取得しない**（市場は使わない）。
**取得が不確実 or 曖昧なら、ここでユーザーに URL 指定か貼り付けでの補強を依頼する**
（出走表は崩れやすい核データなので無理に推定しない）。

`race-id` を `YYYYMMDD-開催-レース番号` で決め、
`data/races/<race-id>/出走表.md` に整形保存する（全馬リスト＋レース条件。オッズ列は持たない）。

**当日の参考レース特定（§0-1 用）**: 本命は後半R（11R 等）が多く、前半Rは当日バイアスの採取に使える。
同開催（同競馬場・同日）のレースカードを引き、対象レースと**条件が一致する前半Rを名指しで拾う**。
一致の優先順位は **芝/ダート（必須）＞ 同日・時間帯（必須・直前ほど重い）＞ 回り内外・右左 ＞ 距離帯**
（芝/ダは絶対に混ぜない。回り・距離は近いもので代用し割引）。
取得できたR番号・発走時刻・コースを §0-1 の表に埋める。カードが取れなければ一致基準だけ記し「当日特定」と注記。

### STEP 2. 観点モードの決定

`observation-points.md` に従い、頭数・情報量で観点数を決める（既定 10 観点 A〜I, K。市場Jは無い）：
- 多頭数(14〜18) / GⅠ等の情報が厚いレース → **10 観点**（A〜I, K 全部）
- 標準(10〜13頭) → **7 観点**
- 少頭数(〜10) / 情報が薄い → **5 観点**

騎手の乗り替わりが鍵になるレース（主戦離脱・強化乗り替わり・テン乗り多数）では、
観点数を絞る場合でも **K を単独観点として残す**ことを推奨。
**いずれのモードでも STEP4a 展開合成は必ず実施する。**

### STEP 3. 証拠ファンアウト（Workflow）→ 展開合成

観点ごとに調査サブエージェントを**並列起動して証拠を集め**（Research フェーズ）、
全証拠が出揃ってから**展開合成を1回だけ走らせる**（PaceSynthesis フェーズ）。
多数のエージェントを使う重い処理なので **Workflow ツールで実行**する。各 Research エージェントに渡す：
- 担当観点の調査手順（`research-protocol.md` の該当セクション）と推奨ソース
- `出走表.md` の全馬リスト＋レース条件（**オッズは渡さない**）
- 出力スキーマ（`research-protocol.md` 末尾。**観点E は PACE_EVIDENCE_SCHEMA**で生証拠のみ）

各エージェントは web 調査の上、結果全文を `data/races/<race-id>/research-<観点ID>.md` に保存し、構造化要約を返す。
その後、**PaceSynthesis エージェント**が全証拠（E の脚質・先行争い、B の近走脚質、D のバイアス、K の騎手の出方、
関係者コメント、出走表の枠）を突き合わせ、`pace-synthesis.md` に従って **複数の名前付き展開パターン**（PACE_MODEL）を作る。

Workflow スクリプトの骨子（Research 並列 → バリア → PaceSynthesis）：

```js
export const meta = {
  name: 'race-fanout-and-pace',
  description: '観点ごとに証拠をweb調査し、全証拠を突き合わせて展開パターンを合成する',
  phases: [{ title: 'Research' }, { title: 'PaceSynthesis' }],
}
// args = { raceId, condition, horses, points:[{id,name,protocol,sources}] }  ※ odds は渡さない

const RESULT_SCHEMA = { /* point, overall_confidence, field_note, horses:[{no,name,pros,cons,score(-2..+2 / Iは0..-2),confidence,sources}], note */ }
const PACE_EVIDENCE_SCHEMA = { /* legs:[{no,name,style,ten_speed,expected_pos}], lead_contenders:[{no,stance}], bias:{track,detail,key_horses}, draw:[{no,note}] */ }
const PACE_MODEL_SCHEMA = { /* patterns:[{id,name,prob,trigger,first_600m,leg_advantage,formation_head,formation_last_corner,bias,per_horse_fit}], falsification, field_note */ }

// --- Phase 1: 全観点を並列で証拠収集（E だけ証拠スキーマ）---
const research = await parallel(args.points.map(p => () =>
  agent(
    `あなたは競馬の「${p.name}」観点の専門調査員。全出走馬について web 調査し、` +
    (p.id === 'E'
      ? `脚質・テン速・先行争いの当事者・馬場バイアス・枠の“生証拠だけ”を返す（有利不利スコアやパターンは作らない）。`
      : `好材料/懸念/評価(-2..+2)/確信度/出典を返す。`) +
    `\n\n# レース条件\n${args.condition}\n\n# 出走馬\n${args.horses}\n\n# 調査手順\n${p.protocol}\n` +
    `推奨ソース: ${p.sources}\n※オッズ・人気・他人の予想は使わない。捏造せず欠損は確信度を下げる。`,
    { label:`research:${p.id}`, phase:'Research', schema: p.id==='E'?PACE_EVIDENCE_SCHEMA:RESULT_SCHEMA, agentType:'general-purpose' }
  ).catch(()=>null)
)).then(rs => rs.filter(Boolean))   // ← await 完了が暗黙バリア

// --- Phase 2: 展開合成（複数パターンを1回だけ構築）---
const paceModel = await agent(
  `あなたは展開合成器。pace-synthesis.md に従い、以下の全証拠を突き合わせ、全馬の配置から創発する` +
  `複数の名前付き展開パターン（確率＋発動トリガー＋脚質別有利不利＋隊列）を構築せよ。Σprob=1。` +
  `関係者の戦法宣言＞推測、近走の実脚質＞一般ラベル、先行争いが不確実なら別パターンに分岐。\n` +
  `# 全証拠\n${JSON.stringify(research)}\n# 条件\n${args.condition}`,
  { label:'pace-synthesis', phase:'PaceSynthesis', schema: PACE_MODEL_SCHEMA, agentType:'general-purpose' }
)
return { research, paceModel }
```

> Workflow が使えない/重すぎる場合のフォールバック: `Agent`（general-purpose）で観点分を1メッセージ内に並列起動し、
> 返り（バリア相当）を待ってから、メイン文脈で `pace-synthesis.md` に従い展開パターンを合成する。

### STEP 4a. 展開合成（成果物1）

`pace-synthesis.md` に従い（STEP3 の PaceSynthesis が未実施なら）メイン文脈で、全証拠から
**複数の展開パターン**（確率・発動トリガー・脚質別有利不利・隊列・反証条件）を構築する。これが **展開予想**。

### STEP 4b. 着順合成（成果物2 / scoring-model v3.0）

`scoring-model.md` の計算式に厳密に従い、各馬について：
1. 観点評価 → base（潜在能力）→ apt（適性=D）→ cond（状態）→ discount（割引）
2. ペース中立の素の力 `ability0 = base*apt*cond - discount`（§6）
3. **各展開パターンで条件づけ** `ability_i,p = ability0_i * pace_fit`（§7、パターンの leg_advantage/per_horse_fit を使用）
4. パターンごとに softmax(T) → 条件付き勝率 `p_i,p`、**パターン確率で加重**して `p_i`（§8）
5. Harville で着順分布（連対率・複勝率・期待着順）（§9）。**各パターンの条件付き着順も保持**
6. 偶然 = パターン間ばらつき＋確信度から勝率レンジ（§10）

> **市場・妙味・EV・Kelly・買い目は無い**（馬券は人間判断）。出力は展開と着順の予測のみ。
計算過程の要点を残し、確信度が低い観点の影響を明示する。

### STEP 5. 出力 & 2系統ログ

`output-template.md` の体裁でレポートを作成し、画面に出力 ＋ `data/races/<race-id>/report.md` に保存。
**§2 展開予想（パターン）と §3 着順予想表（加重＋パターン別条件付き）の2本柱が主役**。
**§0 当日アップデート・ボードを最上部に置く**（当日の参考R・馬場・パドック枠）。分析時点では参考Rと馬場の質欄を埋め、観察値・パドック・馬体重は空欄（当日記入）でよい。
最後に `predictions.jsonl` に**2レコード**を追記する（市場フィールド無し）：
- `record:"pace"`（1レース1行）: patterns・falsification
- `record:"rank"`（1馬1行・上位馬）: win_prob(加重)・place_prob・predicted_rank・win_range・conditional[パターン別]

### STEP 6. 補強の案内 & 当日可変

- 確信度が低かった観点（特に H 当日気配・パドック・関係者コメント）を明示し、
  ユーザーが URL or 貼り付けで補強できることを案内。補強を受けたら該当観点だけ再調査 → 再合成。
- **当日可変**: §0 ボードの当日情報（**前半参考Rで採取したバイアス**・パドック・乗り替わり・馬場変化・取消など）を受けたら、
  `pace-synthesis.md` の当日手順で **パターン確率を付け替える / 1パターンに固定 → scoring §8-9 だけ再計算**（素の力 ability0 は再調査不要）。
  参考Rで「想定と馬場の質が違った」場合のみ §6 適性（ability0）を部分見直し。
  更新後の pace/rank レコードを `note:"当日更新"` 付きで**追記**（上書きしない）。

## 注意

- このハーネスは**展開予想と着順予想の精度に全振り**。市場（オッズ・人気・妙味・EV・買い目）は一切持たず、馬券選択は人間が行う。
- 証拠は馬の内在情報のみ（純粋情報の原則）。他人の予想・印・オッズは使わない。
- web 取得の信頼性が低い項目は確信度「低」とし、点推定を過信せずレンジで示す。
- スコアリングの重み・閾値は `scoring-model.md`、展開合成の手順は `pace-synthesis.md` が調整点。ここを書き換えて改善する。
