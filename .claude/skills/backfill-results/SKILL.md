---
name: backfill-results
description: 確定結果の未記録レースを洗い出し、Sonnet並列エージェントで公開結果（着順・通過順・上がり・前半ペース）を収集・検証して results.jsonl に追記する。確定払戻も record:"payout" 行として収集（I1-R・箱ROI検証用）。判断ゼロの事実収集レイヤー＝採点(/review-prediction)はしない。「結果をバックフィルして」「未記録の結果を埋めて」で起動。レース翌日〜週明けの定期実行を想定。
---

# backfill-results — 確定結果の収集バックフィル（機械層）

予測済みレースの確定結果が未記録のまま溜まると較正コーパスが痩せる（2026-07: 25件溜め込みの反省）。
このスキルは**事実収集のみ**を Sonnet に並列委譲して埋める。採点（pace_review / miss_class / label_reconstructed）は
判断の仕事＝ `/review-prediction` の担当（本体モデル or Opus 委譲）。

## STEP 1. 欠落の特定

```bash
python3 tools/missing_results.py --json
```
`result_missing` と `payout_missing` が対象。両方0件なら終了（`review_missing` 等が残っていれば `/review-prediction` を案内）。

## STEP 2. Sonnet 収集エージェントの並列 spawn

- **開催日×競馬場でバッチ化**（1エージェント1〜5レース）。model は **sonnet**（機械収集＝本体モデル不要）。
- 各エージェントへの指示（テンプレ・要点）:
  1. `data/races/<race_id>/出走表.md` を Read → 出走馬（馬番・馬名）とレース名を把握。
  2. web で確定結果（推奨: `tools/fetch_result.py`＝競馬ラボを最優先・JRA公式。地方は keiba.go.jp・WebSearch スニペット。netkeiba は検索結果スニペットの参照のみ＝WebFetch で直接一括取得しない）。
     **WebFetch 要約は馬名を誤ることがある＝生HTML抽出か2ソース突合を推奨**。
  3. scratchpad に 1レース1ファイルで JSON 出力（下記スキーマ）。
  4. **禁止: オッズ・人気は一切記録しない**（I1）。**払戻は finish 行には書かず**、別途 `record:"payout"` 行として収集する（I1-R・下記 STEP 2.5）。
  5. 全頭カバーを出走表と照合してから書き出す。

出力スキーマ（`results.jsonl` の結果行と同形）:
```json
{"race_id": "YYYYMMDD-場-RR", "date": "YYYY-MM-DD",
 "finish": [{"no": 5, "name": "馬名", "pos": 1, "passing": "3-3-2-1", "agari": 34.5, "style": "差"}],
 "pace_actual": {"first_600m": 34.8, "label": "M", "label_reconstructed": null, "reconstructed_from": []}}
```
- 競走中止/失格は `pos: null, status: "中止"`、出走取消はトップレベル `"scratched": [...]`。
- `label` は情報源の明示表記（媒体のペース欄等）の転記のみ＝**推定させない**。`label_reconstructed` は null 固定（review の担当）。
- `first_600m` はラップの600m境界値が無ければ null（補間推定禁止）。

## STEP 2.5. 払戻の収集（`payout_missing` 対象・I1-R）

- **JRA**: web 調査不要＝ツールで決定論取得（単一プロセスの逐次ループ＝礼儀装備は `_polite` が担保）:
  ```bash
  python3 tools/fetch_result.py payout <dir-race-id> --append   # 例 20260628-hakodate-11
  ```
  組番×実着順の**相互検証**（馬連組=実1-2着集合・三連複組=実1-3着集合・単勝=実1着）をツールが内蔵＝NG なら追記されない。
- **NAR・取得不能**: 公式払戻表（keiba.go.jp 等）のテキストを貼り付け:
  ```bash
  cat 払戻.txt | python3 tools/fetch_result.py paste-payout <dir-race-id> --append
  ```
  finish 行が既にあれば同じ相互検証が走る。Sonnet 収集エージェントに委譲する場合も**最終追記は必ずこのツール経由**（手書き JSON を直接 append しない＝検証を迂回させない）。

## STEP 3. 機械検証 → 追記

追記前に必ず全ファイルを一括検証する（1件でも error があれば追記しない）:
- JSON 妥当・`race_id` がファイル名と一致・ID形式 `\d{8}-[a-z]+-\d{2}`（RR は 0埋め2桁）
- **finish 行**に禁止語（オッズ/人気/払戻/odds/payout）混入なし（払戻は `record:"payout"` 行のみ許可＝I1-R。payout 行にもオッズ・人気は書かない）
- `pos` が 1..N 連番（null は status 付きのみ）・`style` ∈ {逃,先,差,追,-}・`label` ∈ {H,M,S,null}
- **report.json の rank[] と頭数・馬名集合が完全一致**（scratched 含めて勘定）
- 既存 results.jsonl と race_id 重複なし
- payout 行: `comb`×実着順の相互検証（`fetch_result.py` の verify が担保。手動追記した行は再検証）

検証通過後に results.jsonl へ追記し、`python3 tools/missing_results.py` で `result_missing: 0件`・`payout_missing: 0件`（NAR 取得不能分は明示リストで残す）を確認。

## STEP 4. 後続の案内

- 採点バックログ（`review_missing`/`missclass_missing`/`pace_unlabeled`）が残っていれば `/review-prediction` を提案。
- コーパスが+5件以上増えたら `/calibrate-T` と `tools/backtest.py` の再実行を提案（率の較正が動く可能性）。
