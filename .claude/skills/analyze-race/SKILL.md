---
name: analyze-race
description: 競馬レースを観点別の並列web調査で分析し、二層モデル（能力レイヤー→市場レイヤー）で勝率表・妙味・単複/三連系の買い目を出力する。「◯◯レースを分析して」「<netkeiba URL>を分析」「(出走表貼り付け)を分析」で起動。
---

# analyze-race — 競馬予想オーケストレータ

観点ごとに web 調査サブエージェントを**並列起動**し、結果をメイン文脈で統合して
**勝率表・妙味・買い目**を出力する。モデル哲学とデータ配置は repo ルートの `CLAUDE.md` 参照。

参照ファイル（このSkillの references/）:
- `observation-points.md` — 観点カタログと因子マッピング、グルーピング設定
- `research-protocol.md` — 各観点の調査手順・推奨ソース・検索クエリ・出力スキーマ
- `scoring-model.md` — 発揮能力→勝率→妙味→買い目 の計算式と現行重み
- `output-template.md` — 最終レポートの体裁と predictions.jsonl 追記形式

## 手順

### STEP 1. レース特定 & 核データ収集

入力（レース名 / URL / 貼り付け出走表）からレースを特定し、以下を集める：
- レース名・日付・競馬場・距離・コース（芝/ダ・回り）・馬場状態・頭数
- **出走表**（馬番・馬名・性齢・斤量・騎手・脚質・前走）
- **単勝/複勝オッズ・人気**（直近で取得できる最新値。前日・当日で異なれば日時を明記）

WebSearch / WebFetch で取得。`netkeiba` の出走表・オッズページが基本ソース。
**取得が不確実 or 曖昧なら、ここでユーザーに URL 指定か貼り付けでの補強を依頼する**
（出走表・オッズは崩れやすい核データなので無理に推定しない）。

`race-id` を `YYYYMMDD-開催-レース番号` で決め、
`data/races/<race-id>/出走表.md` に整形保存する（全馬リスト＋オッズ表）。

### STEP 2. 観点モードの決定

`observation-points.md` に従い、頭数・情報量で観点数を決める：
- 多頭数(14〜18) / GⅠ等の情報が厚いレース → **10 観点**
- 標準(10〜13頭) → **8 観点**
- 少頭数(〜10) / 情報が薄い → **6 観点**

### STEP 3. 並列ファンアウト（Workflow）

選んだ観点ごとに調査サブエージェントを**並列起動**する。
これは多数のエージェントを使う重い処理なので、**Workflow ツールで実行**する
（Skill が内部で Workflow を呼ぶ構成）。各エージェントには次を渡す：
- 担当観点の調査手順（`research-protocol.md` の該当セクション）と推奨ソース
- `出走表.md` の全馬リスト＋レース条件＋オッズ
- 出力スキーマ（`research-protocol.md` 末尾）

各エージェントは web 調査の上、結果全文を `data/races/<race-id>/research-<観点ID>.md` に
保存し、構造化要約（スキーマ準拠）を返す。**観点Eは場全体の展開図を、観点Jはオッズ表を**
「場全体メモ」に入れる。

Workflow スクリプトの骨子（観点配列を回して並列調査）：

```js
export const meta = {
  name: 'race-fanout',
  description: '観点ごとに競馬レースをweb調査し構造化要約を返す',
  phases: [{ title: 'Research' }],
}
// args = { raceId, condition, horses, odds, points: [{id,name,protocol,sources}] }
const RESULT_SCHEMA = {
  type: 'object',
  required: ['point', 'overall_confidence', 'horses'],
  properties: {
    point: { type: 'string' },
    overall_confidence: { enum: ['高','中','低'] },
    field_note: { type: 'string' },
    horses: { type: 'array', items: {
      type: 'object',
      required: ['no','name','pros','cons','score','confidence'],
      properties: {
        no: { type: 'number' }, name: { type: 'string' },
        pros: { type: 'array', items: { type: 'string' } },
        cons: { type: 'array', items: { type: 'string' } },
        score: { type: 'number' },           // -2..+2 (Iは0..-2 / Jは市場強度)
        confidence: { enum: ['高','中','低'] },
        sources: { type: 'array', items: { type: 'string' } },
      } } },
    note: { type: 'string' },
  },
}
const results = await parallel(args.points.map(p => () =>
  agent(
    `あなたは競馬の「${p.name}」観点の専門調査員。以下のレースの全出走馬について、` +
    `この観点で web 調査し、好材料/懸念/評価(-2..+2)/確信度/出典を返す。\n\n` +
    `# レース条件\n${args.condition}\n\n# 出走馬・オッズ\n${args.horses}\n${args.odds}\n\n` +
    `# 調査手順（必ず従う）\n${p.protocol}\n\n推奨ソース: ${p.sources}\n\n` +
    `web検索で根拠と出典URLを集めること。取得できない項目は捏造せず欠損として確信度を下げる。`,
    { label: `research:${p.id}`, phase: 'Research', schema: RESULT_SCHEMA, agentType: 'general-purpose' }
  ).catch(() => null)
)).then(rs => rs.filter(Boolean))
return results
```

> Workflow が使えない/重すぎる場合のフォールバック: `Agent`（general-purpose）を
> 1メッセージ内で観点分まとめて並列起動し、同じスキーマで返させる。

### STEP 4. 統合（scoring-model）

`scoring-model.md` の計算式に厳密に従い、各馬について：
1. 観点評価 → base（潜在能力）→ apt（適性）→ cond（状態）→ discount（割引）
2. 発揮能力 `ability = base*apt*cond - discount`
3. softmax(T) で正規化 → **自分の勝率**
4. オッズの overround 除去 → **市場勝率**
5. **妙味 = 自分の勝率 − 市場勝率**、EV、Kelly1/4
6. 三連系は Harville 近似で着順分布 → 組EV（§10）
7. 偶然 = 確信度・頭数から勝率レンジ（§11）

計算過程の要点を残し、確信度が低い観点の影響を明示する。

### STEP 5. 出力 & ログ

`output-template.md` の体裁でレポートを作成し、画面に出力 ＋
`data/races/<race-id>/report.md` に保存。
最後に各買い目候補馬を `output-template.md` の JSON 形式で
`data/predictions.jsonl` に追記する（後の `/review-prediction` 用）。

### STEP 6. 補強の案内

確信度が低かった観点（特に H 当日気配・直前オッズ・パドック）を明示し、
ユーザーが URL or 貼り付けで補強できることを案内する。補強を受けたら該当観点だけ
再調査 → 再統合する。

## 注意

- 賭けは自己責任。賭け金/Kelly は提示のみで実ベットは人間判断（CLAUDE.md 免責）。
- web 取得の信頼性が低い項目は確信度「低」とし、点推定を過信せずレンジで示す。
- スコアリングの重み・閾値は `scoring-model.md` が唯一の調整点。ここを書き換えて改善する。
