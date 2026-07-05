---
name: fetch-racecard-via-curl
description: 出走表/脚質/血統/当日カードは tools/fetch_racecard.py で取得（JRA優先・WebFetch不可の核データ）
metadata:
  type: reference
---

WebFetch/WebSearch では出走表・脚質・血統が取れない（netkeiba=ログイン、競馬ラボ=WAF403、各サイト=JS後読み、小型モデルが捏造）。

**正式ツール化済み**: `tools/fetch_racecard.py`（標準ライブラリのみ・取得は tools/_polite.py 経由＝robots尊重/1.5s間隔/UA一元。取得ポリシーは scraping.md）。**取得優先順位＝JRA公式 → 競馬ラボ**（ユーザー指定。netkeibaは完全CSR+ログインで不可＝web調査専用）。
```
python3 tools/fetch_racecard.py race <race_id> --json   # JRA優先→競馬ラボ自動FB。source で判別
python3 tools/fetch_racecard.py day  <YYYYMMDD> <場2桁>  # 当日全Rカード（§0-1参考R用・競馬ラボ）
python3 tools/fetch_racecard.py jra  <YYYYMMDD> <場2桁> <R>  # JRA直接（スパイン＋通過順）
```
- **JRA経路**（今週開催）: 出馬表1ページに 馬名・性齢・斤量・騎手・血統(父母父)・枠・**前走通過順=精密脚質** が全部。Shift_JIS・POST連鎖（安定index pw01dli00→開催→レース→出馬表）。★出馬表はオッズ/人気を含むが parse 冒頭で物理除去（市場ゼロ）。
- **競馬ラボ経路**（過去/未来週・JRA障害時のFB）: 馬名・脚質傾向(粗バー)・血統・枠。任意日付OK。
- 詳細仕様は `.claude/skills/analyze-race/references/scraping.md`（唯一の正）。[[analyze-race]] STEP1/§0-1/STEP3 seed で使う。
仕様・データ位置マップ・race_id書式・場コード表・JS制約は **`.claude/skills/analyze-race/references/scraping.md`（唯一の正）** を参照。[[analyze-race]] の STEP1 核データ取得・§0-1・STEP3 seed で使う。
