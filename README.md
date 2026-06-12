# keiba — 競馬予想ハーネス

「◯◯レースを分析して」と頼むだけで、**観点別の並列web調査 → 全証拠の統合**を行い、
**展開予想と着順予想を独立した2つの成果物**として出力する Claude Code ハーネス。
レース確定後に2成果物の精度を**別個に検証**し、読み筋を改善するループを回せる。

> ⚠️ 出力は予測であり的中を保証しません。**市場（オッズ・人気・他人の予想）は一切使いません**。
> 買い目・期待値・Kelly は出しません＝**馬券選択・実ベットは人間判断**（賭けは自己責任）。

## モデル（v5.0 論理ファースト）

```
成果物1 展開予想: 全証拠 → 複数の名前付き展開パターン（可能性ティア 本線★★★/対抗★★/伏線★
                  ＋発動トリガー＋脚質別有利不利＋隊列＋段階フロー phase_flow）。当日情報でティアを付け替え可能
成果物2 着順予想: 最有力パターンの phase_flow に各馬を通し、相別能力
                  （A_early 序盤・A_cruise 中盤・A_finish 終盤・A_class 地力）で並びを論理判断
                  → 印 ◎◯▲△× と行順＋展開列・展開感度・好材料/懸念点（観点タグ付き）
```

- レポートは**表中心・% を一切出さない**（確からしさはティアと印で表す）。
- 根拠は数字でなく **[観点タグ]＋事実＋なぜそう読んだか** で厚く書く。
- 強制ルールの正本は `.claude/rules/harness-invariants.md`（市場ゼロ・%禁止・2成果物の独立 ほか）。

## 使い方

| コマンド | 役割 |
|----------|------|
| `/analyze-race <レース名 \| URL \| 出走表貼り付け>` | 観点別並列調査 → 展開合成 → 展開予想・着順予想を出力 |
| `/review-prediction <レース名> <結果>` | 予測 vs 実結果を**展開精度・着順精度の2スコアカード**で採点し改善案を提示 |

```
/analyze-race 2026 日本ダービーを分析して
/review-prediction 20260531-tokyo-11 の結果でレビュー
```

出走表など崩れやすい核データは `tools/fetch_racecard.py`（JRA優先→競馬ラボ）で決定論取得。
不確実なときは URL 指定/貼り付けでの補強を依頼します。**オッズは取得しません**。

## 仕組み（観点別ファンアウト）

`/analyze-race` は観点ごとの**専属 subagent**（`.claude/agents/obs-*.md`）を並列起動（内部で Workflow 使用）。
全証拠が揃ったら**展開合成（STEP4a）**が複数パターンを構築し、着順合成（STEP4b）が並びを論理で決めます。

| 因子 | 観点（既定 11 観点） |
|------|------|
| 潜在能力 | A 能力指数・時計 / B 近走内容・クラス通用度 / C 血統 |
| 適性 | D コース・距離・馬場適性（＋馬場バイアス担当） |
| 展開証拠 | E 脚質・先行争い・枠（生証拠のみ＝合成は STEP4a） |
| 状態 | F 調教・厩舎 / G ローテ・馬体 / H 当日気配 / K 騎手・乗り替わり |
| 割引 | I リスク/割引要因（減点専用） |
| 条件実績 | L リピーター・条件付き通算パターン（鮮度評価付き） |

頭数・情報量に応じて 5 / 7 / 11 観点を切り替え。**旧観点 J（市場）は撤廃済み**。

## ディレクトリ構成

```
keiba/
├── CLAUDE.md                    # モデル哲学・用語・データ配置・改善ループの概観
├── README.md                    # このファイル
├── .claude/
│   ├── rules/
│   │   ├── harness-invariants.md  # 強制ルールの正本（矛盾時はここが勝つ）
│   │   └── editing-map.md         # 何を変えたいか→どのファイルを触るか
│   ├── agents/obs-*.md          # 観点別の専属 subagent（11個・A〜I, K, L）
│   └── skills/
│       ├── analyze-race/
│       │   ├── SKILL.md         # オーケストレータ（STEP1-6・Workflow骨子）
│       │   └── references/
│       │       ├── observation-points.md  # 観点カタログ・相別マッピング・グルーピング
│       │       ├── research-protocol.md   # 共通規律・出力スキーマ
│       │       ├── pace-synthesis.md      # 展開合成（複数パターン・phase_flow・当日可変）
│       │       ├── scoring-model.md       # 相変位再帰の語彙・因果骨格
│       │       ├── output-template.md     # レポート体裁の正本＋predictions.jsonl形式
│       │       ├── course-geometry.md     # コース物理形状カタログ（距離別・静的正本）
│       │       ├── pedigree-catalog.md     # 血統カタログ（種牡馬の父/母父傾向・半静的正本）
│       │       └── scraping.md            # スクレイパ仕様（h2h直接対戦・pace_aids含む）
│       └── review-prediction/SKILL.md     # 2スコアカード採点・A/B/C仕分け
├── tools/
│   ├── fetch_racecard.py        # 出走表取得（JRA優先・脚質/テン速/血統/h2h。オッズ非取得）
│   ├── fetch_result.py          # 確定結果取得（通過順・上がり・pace_aids。JRAのみ）
│   ├── fetch_oikiri.py          # 追い切り好時計リスト（競馬ブック・観点Fのseed。全頭でなく上位抜粋）
│   └── score_race.py            # 任意のサニティチェック（並びの整合のみ・%の正本ではない）
└── data/
    ├── races/<race-id>/         # 出走表.md / research-<観点>.md / report.md
    ├── predictions.jsonl        # 予測ログ（pace/rank 2レコード・市場フィールド無し）
    ├── results.jsonl            # 実結果・採点ログ（result/pace_review/miss_class）
    └── samples/report-sample.md # レポート出力例
```

`race-id` は `YYYYMMDD-開催-RR`（**レース番号2桁0埋め**。例: `20260531-tokyo-01`）。

## 改善ループ（2スコアカード）

1. `/analyze-race` で予測 → `predictions.jsonl` に pace/rank レコード追記。
2. レース確定後 `/review-prediction` で結果記録（`fetch_result.py` が通過順・復元ペース素材を自動取得）。
3. **展開精度**（実現パターン・脚質有利不利・隊列・phase_flow の的中）と
   **着順精度**（並びの順位相関・◎的中・展開列/好材料/懸念の的中）を別個に採点。
4. 展開を先に採点して A（能力読み違い）/ B（展開読み違い）/ C（偶然）を一次仕分け →
   修正先をルーティング（A→observation-points の読み筋 / B→pace-synthesis）。
5. **同型ミスが3レース以上再発したときだけ**読み筋を更新 → これが1周。

## 推奨データソース

JRA 公式・競馬ラボ（スクレイパの正本）、netkeiba 成績、スポーツ紙の事実記事、JBIS（血統）。
**使わないもの**: オッズ・人気ページ、予想家・専門紙の印や予想展開記事。
詳細は `.claude/skills/analyze-race/references/research-protocol.md` を参照。
