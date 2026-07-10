---
name: ev-board
description: 分析済みレースの馬連・三連複・ワイドオッズをユーザーが貼り付け、エンジン確率（ペア/トリオ）×オッズの EV を箱候補ごとに提示する（I1-E EVレイヤー・買う瞬間の隔離判断板）。金額・Kelly・購入指示は出さない＝買うかは人間判断。「◯◯レースのEVを見せて」「オッズ貼るからEV出して」で起動。前提=report.json 確定済み。
---

# ev-board — 馬連・三連複・ワイド EVボード（I1-E EVレイヤー）

> 🚧 **I1-E 市場の隔離（正本: `.claude/rules/harness-invariants.md`）**
> 1. オッズ・EV の入出力は **`data/ev/` のみ**。予想成果物（report.json／predictions.jsonl／research-*.json）と選別の X 軸には**一切流さない**。
> 2. 確率は**確定済み report.json のエンジン再生**（`score_race.compute_exotics`）のみ＝**オッズを見て確率・印・並びを変えない**。report 未確定なら実行拒否（ツールが強制）。
> 3. 出力は「箱候補×点数×的中確率×オッズ×EV」の表まで。**金額・Kelly・購入指示は出さない**（買うか・いくら買うかは人間）。
> 4. 内在確率は市場較正前＝**EV は参考値**である旨を毎回表示（較正は results.jsonl の蓄積・`/calibrate-T`・`box_sim` で改善）。

## STEP 0. 前提確認

- `data/races/<race-id>/report.json` が確定済み（`/analyze-race` 完了・inject_probs 済み・predictions 投影済み）。
- **以後 report.json は触らない**（時系列の壁）。当日情報でティア替えが必要なら**先に** `/analyze-race` の当日可変手順で report を更新→再投影→それからオッズ。

## STEP 1. オッズの貼り付け（ユーザー）

JRA公式のオッズページ（馬連・三連複・ワイド）を**人間がブラウザで開いてコピー**してもらう（発走直前の値ほど良い＝オッズ変動注記）。
形式は柔軟: `1-5 12.3` 行（`--bet` で券種指定）／`馬連 1-5 12.3` プレフィクス行／JSON。
自動スクレイプ fast-path は VERIFY-pending（JRAオッズページは別POSTトークン経路＝実地調査後に検討。取得ポリシーは `scraping.md`）。

## STEP 2. 実行

```bash
cat odds.txt | python3 tools/ev_board.py <race-id> --bet umaren --save
```
- `--save` で `data/ev/ev-<race-id>.json` に保存（オッズ生値同梱＝レース後の EV 事後検証用）。
- `Σ1/odds` が 1.2〜1.3 から大きくズレたら**貼り付け不完全**（全組が入っていない）＝EV は歪む。上位人気帯だけの部分貼りでも動くが、その旨を添える。

## STEP 3. 提示

ツール出力の2表（箱候補×EV・EV上位組）をそのまま提示し、以下だけ添える:
- 的中確率（箱）と EV の読み方: **EV>1.0 = エンジン確率が市場より強気**の組。ただし較正前＝過信しない。
- box_sim の実測（該当戦略の過去的中率・回収率）を参考として並記してよい（`python3 tools/box_sim.py`）。
- **買い目・金額は提示しない**。締めは「購入判断は人間」で固定。

## レース後（任意）

`/backfill-results` で払戻が入ったら、保存済み `data/ev/ev-*.json` と突合して「EV>1 の組は実際に儲かったか」を検証できる（box_sim の別トラック＝精度採点に混ぜない）。
