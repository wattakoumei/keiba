# スクレイピング仕様（核データ取得）

`tools/fetch_racecard.py`（リポジトリルート）の仕様書＝唯一の正。出走表・脚質・血統・当日カードを
**JRA公式を最優先**に決定論的に取得する。WebFetch/WebSearch が WAF/JS/ログインで弾かれ、
小型モデルが馬名・脚質を捏造する箇所（実害確認済み）を置き換える。

> **市場ゼロは不変**: 取得するのは 馬名・性齢・斤量・騎手・脚質・テン速・枠・血統など**純粋情報**のみ
> （`observation-points.md` の純粋情報の原則）。**JRA出馬表は単勝オッズ・人気を含むが、これは parse 冒頭で物理除去し一切取り込まない**。

## 取得優先順位（ユーザー指定）
```
① JRA公式（jra.go.jp）   ← スパイン＋通過順を1ページで。最も完全・権威
② 競馬ラボ（keibalab.jp） ← JRAが今週外/障害のときのフォールバック。任意日付OK
③ netkeiba              ← 完全CSR＋ログインで stdlib スクレイプ不可 → web調査専用（本ツール対象外）
```
`race` コマンドは ①→② を自動でフォールバックする。出力 `source` フィールドでどちらが使われたか分かる。

## なぜ動くか（共通）
- **標準ライブラリのみ**（urllib＋正規表現、pip不要）。Python 3.14 で lxml/requests/playwright の wheel が無くても壊れない。
- WAF/UA判定は**実ブラウザ UA**で正規通過。競馬ラボ robots.txt は `/db/race/` を **Allow**。
- **netkeiba は完全 CSR**＝urllib では空。だから②は競馬ラボ。netkeiba を取るには Playwright 等が要る（重い・ログイン壁・JRAで足りるため不採用）。

## CLI
```
python3 tools/fetch_racecard.py race <race_id> [--json] [--self-check]   # JRA優先→競馬ラボ
python3 tools/fetch_racecard.py day  <YYYYMMDD> <場2桁> [--json]          # 当日全Rカード（§0-1用）
python3 tools/fetch_racecard.py jra  <YYYYMMDD> <場2桁> [<R>] [--json]    # JRA直接（R省略でトークン一覧）
python3 tools/fetch_racecard.py <race_id>          # 12桁数字は race にディスパッチ（後方互換）
```
- `race`: 1レースの 馬名・性齢・斤量・騎手・血統・枠/馬番・脚質（JRA時は通過順由来＝精密）。`source` 付き。
- `day`: その競馬場の全Rカード `[{r, post_time, surface(芝/ダ), distance, headcount, race_name}]`（競馬ラボ。§0-1参考R選定用）。
- `jra`: JRA出馬表を直接（スパイン＋通過順）。
- `--json`: 構造化出力。既定は人間可読。
- `--self-check`: HTMLドリフト検知（頭数>0・馬名非空、source別の追加検査）。

## フォールバック契約（重要）
- `race` は **JRA→競馬ラボ** を内部で自動フォールバック。**両方落ちて初めて exit≠0**（`{"error","stage"}` を stderr）。
- SKILL 側はこの終了コードを見て **WebFetch → ユーザー貼り付け** に最終フォールバックする（スクレイパは fast-path であって必須依存ではない）。

## race_id・場コード
- **race_id = `YYYYMMDD + 場2桁 + R2桁`**（例 安田11R=`202606070511`、8R=`202606070508`）。JRAナビの開催回/日は内部で収穫するので不要。
- ハーネスのディレクトリ id は **romaji**（`data/races/20260607-tokyo-11/`）＝別物。下表で 2桁に変換。

| コード | 競馬場 | コード | 競馬場 |
|:--:|:--|:--:|:--|
| 01 | 札幌 | 06 | 中山 |
| 02 | 函館 | 07 | 中京 |
| 03 | 福島 | 08 | 京都 |
| 04 | 新潟 | 09 | 阪神 |
| 05 | 東京 | 10 | 小倉 |

## ① JRA出馬表（主ソース・Shift_JIS・POST連鎖）
出馬表1ページに**スパイン＋近走通過順**が全部入る。通過順から「誰が本当に前に行くか」を数字で判定（粗い傾向バーより精密）。

- **取得経路（POST連鎖）**: accessD への POST でトークンを動的生成。
  安定インデックス `pw01dli00/F3` → POST → 開催選択（`pw01drl00<場2><開催8><日付8>/<hash>` を収穫）
  → POST → レース選択（全Rの `pw01dde…<R2>…/<hash>` を収穫）→ 目的レースの出馬表 → パース。
  **末尾2桁hashは構成不能**＝各段でページから収穫。エンコーディングは **Shift_JIS**（要 decode）。
- **★市場ゼロ**: 出馬表ビューは `<div class="odds">`（単勝オッズ・人気）を含む → `PATTERNS["jra_strip_odds"]` で**物理除去してからパース**。フィールドは純粋情報のみを whitelist 抽出。
- **データ位置**: 枠=`<td class="waku">` 内 `alt="枠N"`／馬番=`td.num`／馬名=`div.name` の `accessU`／性齢=`p.age`／斤量=`p.weight`／騎手=`p.jockey`(accessK)／血統=`li.sire`・`母の父：`／通過順=`<li title="Nコーナー通過順位">`。
- **脚質判定**: 近走の第1コーナー位置÷頭数 → 逃(≤1)/先(≤0.30)/差(≤0.65)/追。多数決。テン速=平均比で 速/中/遅。
- **限界**: **JRA今週インデックス依存＝過去/未来週は非対応**（→②へフォールバック）。海外帰り等で近走JRA成績が無い馬は脚質 `null`（スパインは取れる）。

## ② 競馬ラボ（フォールバック・SSR）/db/race/<race_id>/
任意日付OK。脚質は**粗い傾向バー**（JRAの通過順ほどの精度は無い）。レイアウト変化時は `PATTERNS` と本マップを同時に直す。

| データ | DOM 位置 |
|--------|----------|
| 馬名 | `data-hsnm="馬名"` |
| 脚質傾向 | `<ul class="dbrunstyle2 legs">` の 4×`<li>` ＝ 左から **[逃, 先, 差, 追]**（◎>○>▲>△、最大位置が主脚質） |
| 血統 | `<dd class="chichi …">`＝父、`<dd class="haha …">`＝母 |
| 枠/馬番 | `<select class="user_mark" … data-umano data-wakno>`（枠順未確定なら空） |

- **重複テーブル注意**: 横/縦2テーブルで重複表示 → 馬名 `seen` でデデュープ（実装済み）。

## day ページ（競馬ラボ /db/race/<YYYYMMDD>/）
| データ | DOM 位置 |
|--------|----------|
| 芝/ダ | `rCorner … turf|dirt` クラス |
| R番号・発走時刻 | raceNum セル内 `<a href="/db/race/<id>/">NR</a>` ＋ 直後 `<span class="std11">HH:MM</span>` |
| 距離・頭数 | `<span class="std11">芝1600m&nbsp;17頭</span>` |
| レース名 | `href="/db/race/<id>/" itemprop="url">レース名</a>` |
| 内/外回り | day 一覧には無い → 必要なら race 条件側で補う |

## 既知の制約
- **netkeiba は使えない**（完全 CSR＋ログイン）。web調査の一ソースに留める。
- HTML 構造はサイト改修で変わりうる → `--self-check` と本マップで早期検知・一箇所修正（JRAは `PATTERNS["jra_*"]`／競馬ラボは他）。

## ハーネスでの使われ方
- **STEP1 核データ収集**: `race … --json` で 馬名・性齢・斤量・騎手・血統・枠/馬番・脚質を取得し `出走表.md` のスパインに（JRA時は前走通過順も）。web 調査の負担が大きく減る。
- **§0-1 当日参考レース**: `day … --json` でカード取得し参考R（芝/ダ必須＞時間帯＞回り＞距離）を自動充填。脚質は `jra` で精密化可。
- **STEP3 証拠ファンアウト**: 脚質(観点E)・血統(観点C)・近走通過順(観点B) を **seed** として各エージェントに渡し、ゼロから取得せず**検証・補強**させる。
