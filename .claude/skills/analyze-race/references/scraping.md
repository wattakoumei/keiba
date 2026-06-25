# スクレイピング仕様（核データ取得）

`tools/fetch_racecard.py`（リポジトリルート）の仕様書＝唯一の正。出走表・脚質・血統・当日カードを
**JRA公式を最優先**に決定論的に取得する。WebFetch/WebSearch が WAF/JS/ログインで弾かれ、
小型モデルが馬名・脚質を捏造する箇所（実害確認済み）を置き換える。

> **市場ゼロは不変（予想本体）**: 取得するのは 馬名・性齢・斤量・騎手・脚質・テン速・枠・血統など**純粋情報**のみ
> （`observation-points.md` の純粋情報の原則）。**JRA出馬表は単勝オッズ・人気を含むが、これは parse 冒頭で物理除去し一切取り込まない**。
> **境界**: オッズを取るのは**選別レイヤー専用の `tools/fetch_odds.py`（I1-S 隔離）だけ**。本ツール `fetch_racecard.py`（予想本体の核データ）は従来どおりオッズを物理除去する＝両者を混ぜない。fetch_odds は出馬表ビューの odds 塊を **strip せず capture** するが出力は `data/screening/` に隔離（→ `screen-card`）。

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
**1レース=1`<tr>`行を“行単位”でまとめて取る**（`PATTERNS["day_row"]`）。コース種別・距離・頭数・発走・レース名を
同じ行ブロックから1回で取り出すので、行ごとに形が違っても他レースとズレない。
| データ | 行内 DOM 位置（day_row が1行から順に拾う） |
|--------|----------|
| コース種別 | 距離spanの先頭文字 `芝`/`ダ`/`障`（rCorner の turf/dirt/failure と整合） |
| R番号・発走時刻 | `rCorner…><a href="/db/race/<id>/">NR</a></div>` ＋ 直後 `<span class="std11…">HH:MM</span>`（`bgRedL`等の追加クラス許容） |
| レース名 | `itemprop="url">レース名</a>` |
| 距離・頭数 | `<span class="std11…">ダ1400m&nbsp;16頭</span>`（芝/ダ/**障**） |
| 内/外回り | day 一覧には無い → race 条件側で補う |

> ⚠️ **過去バグ（修正済み・2026-06）**: 旧実装はレース名リストと距離リストを別々に取り**位置 zip** で対応づけていた。
> 障害戦の距離「障Nm」を距離正規表現（芝|ダのみ）が拾えず1件欠けると、以降の全レースが**1つ後ろの距離・頭数**を
> 受け取る off-by-one を起こした（例: 加古川特別 実ダ1800/12頭→誤ダ2000/11頭、麦秋S 実ダ1400→誤ダ1600）。
> 頭数ズレは「除外の可能性」という幻の警告まで生んだ。**行単位パース＋`障`対応で解消**。

## JRA出馬表のレース条件（距離・コース＝権威ソース）
- `race`/`jra` コマンドは出馬表ページの `<td class="dist">ダート1,800<span>メートル</span>` から **距離・コース種別** も取る
  （`PATTERNS["jra_dist"]`。ダート→ダ/芝→芝/障害→障、カンマ除去）。**頭数は出走馬数 `len(horses)`** から数える。
- **二重ソース照合**: `race`(JRA成功時) は JRA距離 vs 競馬ラボ day一覧距離を突き合わせ、食い違えば `dist_mismatch` を出して警告（JRA優先）。
  距離は最重要かつ取り違えやすいフィールドなので、単一ソースに頼らない。
- 競馬ラボフォールバック時は race ページに距離が無い → day一覧（行単位）から距離・頭数を補完する。

## 既知の制約
- **netkeiba は使えない**（完全 CSR＋ログイン）。web調査の一ソースに留める。
- HTML 構造はサイト改修で変わりうる → `--self-check` と本マップで早期検知・一箇所修正（JRAは `PATTERNS["jra_*"]`／競馬ラボは `day_row`/他）。
- `--self-check` は JRA時に **距離が取れたか**も検査（`dist` セル構造変化を検知）。

## ハーネスでの使われ方
- **STEP1 核データ収集**: `race … --json` で 馬名・性齢・斤量・騎手・血統・枠/馬番・脚質を取得し `出走表.md` のスパインに（JRA時は前走通過順も）。web 調査の負担が大きく減る。
- **§0-1 当日参考レース**: `day … --json` でカード取得し参考R（芝/ダ必須＞時間帯＞回り＞距離）を自動充填。脚質は `jra` で精密化可。
- **STEP3 証拠ファンアウト**: 脚質(観点E)・血統(観点C)・近走通過順(観点B) を **seed** として各エージェントに渡し、ゼロから取得せず**検証・補強**させる。

## h2h 直接対戦（JRA経路のみ・観点Eの最優先証拠）

`race` コマンドの JRA 経路は、各馬の近走 `recent[]` に**レース特定情報**（`date` ISO・`venue`・`race`・`pos`着順）を持ち、
同一過去レースに今回の出走馬が2頭以上出ていた事実を **`h2h`** として返す（`compute_h2h`）:
- 各対戦は **1角通過順でソート**＝先頭が「実際に前を取った側」。ラベル（逃/先）や推測より強い、先行争いの決定論的証拠。
- human 出力は `対戦歴 <日付> <場><レース名>: A(1角2位・7着) → B(1角9位・4着)`。JSON は `h2h:[{date,venue,race,horses:[{no,name,first_corner,pos}]}]`。
- 観点 E は seed の h2h を lead_contenders の stance に最優先で反映する（`obs-e-pace.md` 傾斜配分）。
- ★市場ゼロ: 近走ブロックに併記される「番人気」は**抽出しない**。
- 競馬ラボ経路には近走レース特定情報が無い → h2h は出ない（E が web で当事者の対戦を補う）。

## クラス序列タグ（昇降級を機械的に効かせる・観点Bのseed）

`race` コマンドは各馬の `recent[]` と当該レースに**クラス序列 rank**（1=新馬/未勝利 2=1勝 3=2勝 4=3勝 5=OP 6=L 7=GⅢ 8=GⅡ 9=GⅠ／`classify_class`）を付ける。
昇降級は **rank の引き算**で機械的に出る＝観点Bは内容（不利/底見せ）の読みに集中できる。
- 各 `recent[]`: `class_rank`・`class_label`・`class_certain`（名前付き ○○S/賞 で格不明なら `null`＋`class_certain:false`、特別は `class_band:[2,5]`）。
- 各馬: `class_move:{last(前走rank), top(近走最高rank), vs_current(昇級/同級/降級)}`。`top > race_class_rank`＝格上経験、`vs_current=昇級`＝底未見せ。
- 当該レース: `race_class`・`race_class_rank`・`race_class_label`。**JRA経路は title 無し→ `--class=<クラス>` で渡す**（SKILL STEP1。競馬ラボ経路は title から自動）。
- **名前付き重賞/特別は `STAKES_CATALOG` を引く**（`fetch_racecard.py` 内・lazy・grade は JRA 公式準拠）。未登録は `class_certain:false`＝obs-b が web 確定＋human 承認で追記。
- 競馬ラボ経路は `recent[]` を持たない → per-past タグは付かない（`race_class` は title から拾える）。NAR/地方クラスはこの尺度外＝`null`（obs-b 補強）。

## fetch_result.py（確定結果の取得・review-prediction の照合元）

```
python3 tools/fetch_result.py <race_id12桁> [--json]   # race_id = YYYYMMDD+場2桁+R2桁（JRAのみ。NARは非対応→手動/貼り付け）
```

- 競馬ラボ DB（`keibalab.jp/db/race/<id>/`）から 着順・馬番・タイム(`time_sec` float)・着差・**通過順**・上り3F(`agari` float)・馬体重 を取得。
  **人気(7列)・単勝(8列)は parse 時に物理的に捨てる**（市場ゼロ I1）。
- **通過順は丸数字**（`②②`＝各角1文字）→ ①〜⑳/㉑〜㉟ を int 化し `passing:"2-2"`／`passing_pos:[2,2]` に正規化。
- **完走以外**（中止・除外・取消・失格）は `rank:null`＋`status` 付きで `non_finishers[]` に分離（review の C＝偶然 仕分け用。rank=0 に丸めない）。
- **`pace_aids`**: `pace_actual.label_reconstructed` の判断**素材**を決定論で算出（結論は出さない＝H/M/S 認定と `reconstructed_from` は review 側）:
  `top3_first_corner`(上位3頭の1角位置=前残りか差し決着か) / `top3_last_corner` / `agari_fastest`(上がり最速馬の着順=届いたか) /
  `rho_lastcorner_rank`(最終角位置×着順の Spearman ρ。+1寄り=前残り、低い=差し台頭)。
- エラー stage: `validate`(12桁でない) / `fetch` / `parse_tbody` / `parse_no_horses`。

### history サブコマンド（例年ペース傾向の素材・展開合成用）

```
python3 tools/fetch_result.py history <race_id> [<race_id> ...] [--json]   # 同一レースの過去開催を複数渡す
```

- 同一レースの**過去開催 race_id（12桁）を複数**渡すと、各開催の**ペース署名**（勝ち馬の通過位置・上位3頭の1角位置・上がり最速馬の着順・ρ）と
  **素材集計**（勝ち馬の平均1角位置・前々で勝った開催数・上がり最速が勝った=差し決着の開催数・平均ρ）を返す。`pace_aids` を過去レースにループ集計するだけ。
- 用途: **`pace-synthesis` の `pace_factors`「例年傾向」行の源**（前残り基調か差し決着多めか）。**結論(H/M/S)は出さない＝素材**（定性傾向の著作は合成側）。
- 過去開催 id は **web 調査で特定**（同レースの過去開催の日付→`YYYYMMDD+場2桁+R2桁` に変換）。
- **耐障害**: 1開催が取れなくても全体は落とさず `{race_id, error}` で個別に欠落させる（集計は取得できた分のみ）。**NAR(地方)は keibalab DB 経路の制約で取得不確実**＝取れない開催は web で補完（川崎・船橋等）。

## fetch_oikiri.py（追い切り好時計リスト・観点Fのseed）

```
python3 tools/fetch_oikiri.py week [--date M/D] [--json]
```

- 競馬ブック ベスト調教（`p.keibabook.co.jp/cyuou/bestcyokyo`・**静的UTF-8・無料・urllib可**）から
  **今週の好時計ランキング**を取得。各馬: 馬名・条件・出走レース・調教日・コース(栗東ＣＷ等)・馬場・各ハロン累計・**ラスト1F**・脚色(馬なり/強め/一杯+余力)。
- ★市場ゼロ: bestcyokyo はオッズ・人気・予想印を含まない（純粋な調教実測）。
- **重要な制約**: これは**全出走馬ではなく好時計の上位抜粋**。対象レースの出走馬が載っていれば追い切り好材料の一次事実、載らない馬は F が web 補完（不在＝調教不良ではない）。
- 用途: 観点 F の seed。読み筋（横比較しない・縦比較優先・ラスト1F・馬なりで好時計・調教駆け注意）は `obs-f-training.md`。

### 追い切りデータ取得の現状（2026-06 調査）
- **全出走馬の追い切りタイムを無料・標準ライブラリで取る経路は存在しない**のが結論。
  - netkeiba `race/oikiri.html` は**JS後読み**（urllibでは tr=0・ajax `api_get_racev3_surf` 依存）＝静的取得不可。
  - JRA公式は重賞のみ＋数値表なし（動画/短評）＋WAF403。JRA-VAN DataLab は有料・Windows COM＝本ハーネス方針(無料/標準ライブラリ/mac)と不適合。
  - 競馬ラボに追い切りタブは**無い**（404確認）＝既存経路の延長では取れない。
- よって「競馬ブック好時計ランキング（上位抜粋）を seed・残りは F が web 補完」の二段構えが現実解。
