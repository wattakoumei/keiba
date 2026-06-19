# 競馬予想ハーネス — 専門家レビュー依頼ブリーフ

> **依頼内容**: 以下に現状の「予想フロー・構成・実測された問題」をまとめた。
> **問題点の優先度付けと、制約（無料/標準ライブラリ/mac/有料DB不可・web調査主体・市場ゼロ）の中での解決策**を依頼したい。
> 主たる関心は **実行コスト（トークン）と所要時間（壁時計）と信頼性（部分失敗）**。予想精度そのものの是非は別レビューでよい。
> 作成日: 2026-06-19 / 対象実行例: 府中牝馬ステークス2026（東京・芝1800・16頭・牝馬ハンデ）
>
> **対象名前空間（レビュー範囲）**: これは **Claude Code 版（`.claude/...` が実体・正本）** のレビュー依頼。
> 本ワークスペースには Codex 移植版（`.codex/agents/*.toml`・`.agents/skills/`・`AGENTS.md`）も同居するが**別物**。
> なお Codex 版 `AGENTS.md` は正本を `.Codex/rules/` と記すが**その実体は存在しない**（実体の rules は `.claude/rules/`）＝
> 名前空間・大文字小文字のドリフトがある。**本ブリーフのレビュー対象は `.claude` 版に限定**し、Codex 移植版は別レビューとする。

---

## 1. システム概要（何を作っているか）

- **Claude Code（CLIエージェント）上のハーネス**。ユーザーが「○○レースを分析して」と言うだけで、観点別の並列web調査 → 全証拠の統合 → **展開予想（成果物1）と着順予想（成果物2）を独立した2成果物**として出力する。
- レース後に2成果物を別個に採点し、読み筋・重み・展開合成手順を改善するループを回す（`/review-prediction`）。

### 設計思想（不変則・`.claude/rules/harness-invariants.md` が正本）
| 不変則 | 内容 |
|---|---|
| I1 市場ゼロ | オッズ・人気・他人の予想（専門紙の印・予想記事）を**証拠にもログにも一切使わない**。買い目・EV・期待値も出さない。予測は馬の内在情報のみ。 |
| I2 %禁止 | レポートに百分率を一切出さない。強弱は**印 ◎◯▲△×注 と行順**、確からしさは**可能性ティア 本線/対抗/伏線**。 |
| I4 2成果物の独立 | 展開予想（§2）と着順予想（§3）を別個に測り・別個に改善。展開→着順の因果は維持。 |
| I5 複数パターン＋当日可変 | 展開は単一に潰さず**名前付きパターン群**（ティア＋発動トリガー＋pace_level＋段階フロー）で持つ。当日情報でティア付け替え。 |
| I10 静的データのワンソース化 | コース形状・血統傾向・厩舎傾向は**正本ファイルから一度だけ供給**しweb再調査しない。 |

### 制約（解決策の境界条件）
- **無料・Python標準ライブラリのみ・mac・有料DB不使用**（JRA-VAN DataLab等は方針外）。
- データは**web調査が主体**（市場ゼロ＝オッズを使わない以上、内在情報をwebから集める必要がある）。
- スクレイパは fast-path（JRA公式→競馬ラボ）で核データ（出走表・脚質・血統・前走通過順）を決定論取得するが、**観点調査自体はweb（WebSearch/WebFetch）**。

---

## 2. 構成（アーキテクチャ）

```
.claude/
  rules/            harness-invariants.md（不変則の正本）, editing-map.md（編集ルーティング）  ※セッション自動ロード
  skills/
    analyze-race/   SKILL.md（手順STEP1-6・Workflow骨子）
      references/   observation-points / research-protocol / pace-synthesis /
                    scoring-model(v5.0) / output-template / course-geometry /
                    pedigree-catalog / stable-intent-rubric
    review-prediction/SKILL.md（2スコアカード採点）
  agents/           obs-*.md × 11（観点ごとの専属subagent。ペルソナ・手順・ソース・スコア指針を内蔵）
tools/（依存ゼロpython）
  fetch_racecard.py 出走表/当日カード（JRA→競馬ラボ自動フォールバック・h2h直接対戦）
  fetch_oikiri.py   追い切り好時計seed（競馬ブック・上位抜粋）
  fetch_result.py   確定結果・例年ペース署名（history）
  score_race.py     並びの任意サニティチェック（%の正本ではない）
  validate_report.py report.jsonスキーマ＋I2(%)ゲート
  project_predictions.py report.json → predictions.jsonl 自動投影
data/
  races/<race-id>/  出走表.md, research-<観点>.json, report.json（構造化正本）
  predictions.jsonl（report.jsonからの投影）, results.jsonl（実結果）
keiba-web/          Astro。report.jsonをレンダリングして閲覧（report.mdは廃止）
```

### 11観点（観点 = 1専属subagent = 並列起動の最小単位）
A 能力指数/時計・B 近走内容・C 血統・D コース/距離/馬場適性・E 展開証拠・F 調教/厩舎仕上げ・
G ローテ/馬体/間隔・H 当日気配/パドック・I リスク/割引・K 騎手/乗替・L 条件実績/リピーター。
（頭数で 5/7/11 観点を選択。16頭フルゲートのGⅡは11観点フル。）

---

## 3. 予想フロー（実際の処理）

```
STEP1 核データ収集    fetch_racecard.py race <id> → 出走表.md（馬名/性齢/斤量/騎手/調教師/血統/枠/脚質/前走通過順/h2h）
                      fetch_oikiri.py week → 追い切りseed。枠順確定なら確定材料を先取り。
STEP2 観点モード決定   頭数・情報量で 5/7/11 観点を選ぶ
STEP3 証拠ファンアウト  ★Workflowツールで実行★
        Phase1 Research      観点subagentを【並列】起動（agentType=obs-*）。各々がweb調査し
                             research-<観点>.json を保存＋構造化要約を返す（schema強制 StructuredOutput）
        ── バリア（全spawn完了を待つが、成功分だけで進む。失敗は null 化して落ちる） ──
        ── ★欠落ゲート（2026-06実装・必須停止）: 期待観点−返却観点／返却が全頭未満 を検出→同期リトライ→なお残れば throw（部分証拠で合成しない。当該観点を再取得して resume）。※合成前に止められるのは返却欠損まで＝未保存ファイルはfs不可でSTEP5検出（合成は返却値を読むため浪費は無し） ──
        Phase2 PaceSynthesis 全証拠をTOON化して合成器(general-purpose)に渡し、複数の展開パターンを1回で構築
STEP4a 展開合成（成果物1） 名前付きパターン（ティア＋トリガー＋pace_level＋段階フロー＋per_horse_fit＋pace_factors）
STEP4b 着順合成（成果物2） 最有力パターンのphase_flowに各馬を通し、相別能力で論理判断 → 印◎◯▲△×注＋行順＋展開列
STEP5 出力             report.json保存 → validate_report.py → project_predictions.py
STEP6 当日可変         参考R/馬場/パドックでティア付け替え → 再投影
```

各観点subagentへの**spawn時注入**: レース条件・全馬リスト・スクレイパseed（E/C/Bに）・コース形状（D/E）・血統カタログ（C）・追い切りseed（F）・厩舎rubric（F/K）・出力スキーマ・共通鉄則（全頭カバー/出典必須/捏造禁止/並列発行/市場不使用）。

---

## 4. 今回の実測（府中牝馬S2026・16頭・11観点）

### 全体テレメトリ
| 実行単位 | agents | subagent_tokens | tool_uses | 所要 | 結果 |
|---|--:|--:|--:|--:|---|
| 本体Workflow | 12 | 714,446 | 250（WebSearch158/WebFetch65） | 835秒 | **D・K がparse失敗** |
| K 再取得（別Agent） | 1 | 84,586 | 70 | 717秒 | 成功 |
| D 再取得① | 1 | 0 | 0 | 11秒 | 失敗(parse) |
| D 再取得② | 1 | 60,728 | 31 | 394秒 | 成功 |
| **概算合計** | 15 | **≈860,000** | **≈351** | **壁時計≈32〜40分** | 全11観点を最終的に report へ反映（ただし artifact は10ファイル＝`research-A.json` 欠落・後述P6） |

### 本体Workflowの per-agent 内訳（agent-*.jsonl を解析）
| 観点 | tool数 | WebSearch | WebFetch | 所要(秒) | 備考 |
|---|--:|--:|--:|--:|---|
| obs-g-rotation | **47** | 24 | 20 | **469** | 予算目安(~18)を大幅超過・最長 |
| obs-c-pedigree | 20 | 18 | 0 | 376 | |
| obs-h-paddock | 10 | 3 | 4 | 332 | |
| obs-b-recent | 22 | 20 | 0 | 329 | |
| obs-l-repeater | 27 | 16 | 9 | 328 | |
| obs-i-risk | 25 | 20 | 1 | 318 | |
| obs-f-training | 19 | 14 | 3 | 316 | |
| obs-a-index | 30 | 14 | 14 | 279 | |
| obs-k-jockey | 35 | 20 | 13 | **269** | **35ツール走破後に最終出力がparse失敗→全破棄** |
| obs-e-pace | 12 | 9 | 1 | 202 | |
| general-purpose（合成） | 3 | 0 | 0 | 164 | |
| obs-d-aptitude | 0 | 0 | 0 | **11** | parse失敗（調査せず即死） |

> 「最大6頭×3バッチ≒18ツール」という共通鉄則の目安に対し、g=47/k=35/a=30/l=27/i=25 と**多くの観点が超過**。WebFetchはページ全文をmarkdown化＝1回が高トークン。

---

## 5. 問題点（実測ベース・寄与の大きい順）

| # | 問題 | 証拠 | 区分 |
|---|---|---|---|
| **P1** | **schema強制の最終出力がparse失敗 → その時点までの調査を丸ごと破棄 → 再取得（二重払い）** | obs-kは35ツール・269秒を走破した後に最終StructuredOutput tool callがparse失敗→破棄。再取得で70ツール・717秒・8.5万tokを再消費。**Kのweb調査を実質2回**。Dも同様。なお**再取得時はschemaを外しファイル保存+短文返しにしたら一発成功**＝schema強制が事故の引き金。 | 回避可能（最大） |
| **P2** | **部分失敗の再取得が本体完了後に直列実行** | 本体835秒の後に再取得が重ねられず壁時計に+約19分 | 回避可能 |
| **P3** | **観点ごとのツール数が予算規律を超過** | g=47（目安18の2.6倍）等。打ち切り規律（「完全性優先」の文言）がツール数増を止められていない | 回避可能 |
| **P4** | **規模の床（不可避コスト）** | 16頭×11観点で WebSearch158＋WebFetch65。市場ゼロ＝web調査必須なので一定量は不可避 | ほぼ不可避 |
| **P5** | **観測可能性の欠如** | per-agentのコスト/失敗が自動で出ず、`agent-*.jsonl`を手解析して初めて長尺・過剰fetch・失敗を特定できた。失敗時の生tool-call内容は残らず「なぜparseできなかったか」は未確定 | 構造的 |
| **P6** | **部分失敗が後段を止めない（縮退の設計不在）＋欠落の無検知** | Workflow骨子は失敗を `catch(()=>({p,r:null}))` に落とし `.filter(x=>x.r)` で消すため、**欠落観点があるまま PaceSynthesis に進む**（`SKILL.md` 該当行）。今回はD・Kがnullで落ち、人間が気付いて補填しなければ2観点欠落のまま成果物が出ていた。**さらに本実行ではA観点のartifact `research-A.json` が保存されず**＝合成器はworkflow返り値からAを読めたため report には反映されたがディスクは10ファイル。`used_observations` にAはあるのに実ファイルが無く、**`validate_report.py` は used_observations と research-*.json の対応を検証しないため通過した**＝欠落が無検知で最終成果物まで到達する経路の実例。**→ §6 G(欠落+部分欠損ゲート)・E(合成前の同期リトライ→なお欠落なら throw＝必須停止)で塞いだ。残るP1根絶（agent側のファイル保存優先化＝二重払いの解消）は未着手。** | 設計上の穴（最重要級） |

### P1の根因（仮説・要検証）
- 9/11観点はschema強制でも成功 → schema自体が常に致命ではない。**D・Kは出力が長く/複雑で、最終tool callの生成が途中で崩れる（トークン上限 or 整形崩れ）と推測**。retryも同様に失敗。
- 「なぜparseできなかったか」の生ログは未取得（P5）＝確証は取れていない。**再取得（schema無し・保存+短文返し）で両方成功した**という対照だけが手がかり。
- **根因はschema強制単独ではない**: parse失敗時に**保存済み research file を再読込して救済する経路が無い**ことも根因（観点によっては最終出力前に research-X.json を書けているのに、返り値nullで全破棄される）。→ 対策は「schemaを外す」だけでなく**保存ファイル検証＋救済をセット**にすべき。

### 既知のドキュメントドリフト（観測済み・参考／本ブリーフの瑕疵ではない）
- `.claude/rules/editing-map.md` に**古い観点数**が残存（「10個・A〜I,K」「5/7/10」＝現行は **11個 A〜I,K,L・5/7/11**）。現行SKILL・本ブリーフは11観点で整合。
- Codex版 `AGENTS.md` の `.Codex/rules/` は実体なし（前掲・名前空間ドリフト）。
- いずれも「観測済みのドリフト」としてレビュアーに共有（修正は別途）。

---

> **追記（2026-06・systemic確認）**: research artifact 欠落は今回限りでない。**既存 report 2件中2件**で発生（`20260617-kawasaki-11`=B欠落 / `20260621-tokyo-11`=A欠落）。schema強制下で agent が StructuredOutput を優先し Write をスキップする経路が常態化していた疑い＝P1とP6は同根。
>
> **対応状況（2026-06実装済み）**: 「警告で通す場所」を**error/必須停止に落とし切った**（§6◎）。残るは P1根絶（agent側のファイル保存優先化）と設計判断（review投影・tool予算）＝§7。
>
> **合成前ゲートの線引き（正直な制約）**: Workflow script は **fs アクセス不可**。よって PaceSynthesis 前に見られるのは**返却データの全頭数**まで（上記(b)で throw）。「返却はあるが `research-X.json` が未保存」（A欠落型）は fs が要るため**合成前には検出できない**＝STEP5 の `validate_research_bundle` が担保する。ただし合成は**返却値**（TOON 化）を読み**ファイルは読まない**ので、未保存でも**合成の証拠は欠けない**＝この型での合成トークン浪費は無い（浪費が起きるのは返却が全頭未満の(b)型で、それは合成前 throw 済み）。

## 6. 打ち手（◎=実装済み・必須ゲート化／△=未着手・要判断）

| 状態 | 案 | 中身 | 狙う問題 |
|:--:|---|---|---|
| ◎ | **G** | `tools/validate_research_bundle.py` 新設＝`used_observations`↔実 `research-<観点>.json` の**対応ゲート**。STEP5必須化。**欠落＝error／`report.rank` との馬番集合一致＋構造検証**（行が list か・各行 dict・`no` が int・重複なし・行数=`field_size`）。同数でも**重複・別馬混入・N+1行**を捕捉、壊れた artifact は validator を落とさず error 化（CI向き）。kawasaki=B欠落+E空+I空を検出、tokyoはA復元で全16頭一致し通過 | P5・P6 |
| ◎ | **E** | 本体内で同期リトライ＝PaceSynthesis前の必須停止を2段に: **(a) 観点欠落（返却なし）→throw**、**(b) 返却はあるが全頭未満（非E=horses, E=legs < field_size）→throw**。いずれもリトライ後に残れば部分証拠での合成を中止（再取得して resume＝成功分キャッシュ再利用）。本体完了後の直列再取得も解消 | P1・P2・P6 |
| ◎ | **I5/全頭/順序** | `validate_report.py` 強化＝**複数パターン必須（patterns≥2）**・**全頭カバー（rank・leg_table=field_size）**・**leg_table↔rank の馬番集合一致**・**rank_order の連番**を warning→**error**。さらに **rank_order・全馬番（rank/leg_table/pattern の隊列・risers/sinkers/contesters・box_reverse）を int 必須化**（`"1"` 文字列混入で集合一致や `horse_no` 投影が壊れる／`sorted()` クラッシュを防止）。退化・破損出力を遮断。既存2レース通過 | P2/P3（退化/破損/型遮断） |
| ◎ | **I1市場スキャン** | 両validatorに**市場語スキャン**（人気・オッズ・配当・払戻）を追加＝report/ログだけでなく **research JSON に残っても I1 違反として error**。実害例: tokyo research-H/G/L に「N番人気」混入→言い換えで除去、CREED にも「市場語は1文字も書かない・除外宣言も書かない」を明記（発生源を塞ぐ） | P1（I1漏れ） |
| ◎ | **合成前 distinct-no** | SKILL の合成前ゲートを length だけ→**行数=field・各 no が int・重複なし（distinct な int no 数=field）**に強化。N行でも馬番重複/別馬混入で壊れた TOON が合成に渡るのを停止 | P2 |
| ◎ | **無印統一** | 無印を全角 **`—` に統一**（`MARKS` から `-` を除去）＝投影器の skip 判定（`—` のみ）とのズレを解消。既存 report は全て `—` 使用で無影響 | P3（印の表記ゆれ） |
| ◎ | **docstring** | `validate_research_bundle.py` の冒頭説明を実装（部分欠損/集合/構造/市場語=error）に同期 | P3（説明ズレ） |
| △ | C | 観点subagentの**schema強制を廃止 → Write＋短文返し**に。**かつ parse失敗時は保存済みファイルを再読込して救済**（schema除去単独でなく「保存検証＋救済」をセット）。※Gで欠落は捕捉できるが、P1の二重払い根絶には agent 側の保存優先化が要る | P1（最大・未着手） |
| △ | A | `tools/wf_cost_report.py` 新設：`agent-*.jsonl` を集計し per-agent コスト/失敗を自動出力 | P5 |
| △ | B | parse失敗時に最後のtool-call生contentを保存 or 失敗エージェントをschema無しで1回再投げ | P5 |
| △ | D' | **総tool数・WebSearch数・同一ソース重複も予算化**（WebFetch cap単独ではg=24WS/20WF・b=20WSを塞げない） | P3 |
| △ | F | **観点の統合・削減**（11→7等）や seed活用拡大で WebFetch を減らす | P4 |

---

## 7. 専門家に判断・提案を仰ぎたい論点

> 注: §6◎で**欠落ゲート・同期リトライ・退化遮断は実装済み**。以下は残る設計判断（コードだけでは決められない／トレードオフを伴う）。

1. **P1の根絶（最優先・未着手）**: 「schema強制 vs ファイル保存+短文返し」のどちらを fan-out の既定にすべきか。今回はGの欠落ゲートで**検出**はできるが、parse失敗時にそれまでの調査を捨てる**二重払い**は agent 側を「保存優先＋短文返し」に変えないと消えない。schema を捨てると下流の構造化検証が緩む懸念とどう両立させるか。
2. ~~review loop と jsonl 投影の不整合~~ **【解決済・2026-06】option(b)採用**: 全馬順位相関は **review が `report.json` の `rank[]`（全馬）を正本に読む**よう review-prediction SKILL を更新。`predictions.jsonl` は印持ち投影のまま（的中率・好材料/懸念照合に使用）＝I10「report.json 正本」と整合し投影契約も不変。
3. **コスト削減（精度を落とさず）**: 16頭×11観点のweb I/O（特にWebFetch全文）を減らす設計。観点統合・seed活用・検索回数規律・キャッシュなど、どれが効くか。市場ゼロ（内在情報のみ）の制約は維持したい。
4. **ツール予算の効かせ方（P3）**: 「完全性優先（全頭カバー）」と「ツール数上限」は今回衝突し上限が無視された（g=24WS/20WF）。プロンプト規律でなく**機構で総tool数・WebSearch数・同一ソース重複を予算化**すべきか。WebFetch cap単独では不足。
5. **観測可能性**: per-agentのコスト/失敗/長尺を**毎回・自動で**可視化する最小の計装（案A・P5）。
6. **アーキテクチャ全体の妥当性**: 「観点ごと専属subagentを全並列 → バリア → 合成」という現方式自体が、この規模・制約に対して妥当か。別構成（重要観点優先の段階実行、2段階の粗→精、頭数に応じた動的縮退など）の提案があれば。

---

## 付録: 関連ファイル（レビュー時の参照点）
- 不変則: `.claude/rules/harness-invariants.md` / 編集マップ: `.claude/rules/editing-map.md`
- 手順: `.claude/skills/analyze-race/SKILL.md`（Workflow骨子＝fan-out）
- 観点定義: `.claude/agents/obs-*.md`（11個）
- 合成: `.claude/skills/analyze-race/references/pace-synthesis.md`
- 出力契約: `.claude/skills/analyze-race/references/output-template.md`
- 実行例の成果物: `data/races/20260621-tokyo-11/report.json`＋`research-*.json`
