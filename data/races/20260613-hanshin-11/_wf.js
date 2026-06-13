export const meta = {
  name: 'race-fanout-and-pace',
  description: '三宮S(阪神ダ1800・16頭)を観点別subagentで並列web調査→展開合成',
  phases: [{ title: 'Research' }, { title: 'PaceSynthesis' }],
}

const DATA = {
  raceId: "20260613-hanshin-11",
  condition: "三宮ステークス（オープン特別・別定相当） 阪神ダート1800m（右回り）16頭立て 発走15:20。初角まで約303mで先行争いが起きやすい・発走直後＋ゴール前の坂2回・ダ直線352.7m・1周1517.6m。馬場状態は当日記入（分析時点未知。良想定だが当日要確認）。斤量はハピ57.5/テーオーグランビル・モックモック57.0が重め、ピースオブザライフ52.0・クインズショコラ53.0が軽量。",
  horses: `| 馬番 | 枠 | 馬名 | 性齢 | 斤量 | 騎手 | 父 | 母父 | 脚質 | テン速 | 上り最速 |
| 1 | 1 | リチュアル | せん7 | 56.0 | 坂井瑠星 | キングカメハメハ | Rockport Harbor | 差 | 中 | 37.8 |
| 2 | 1 | マリアナトレンチ | 牡6 | 55.0 | 松若風馬 | ハーツクライ | Saint Liam | 差 | 遅 | 36.8 |
| 3 | 2 | サンマルパトロール | 牡6 | 54.0 | 田口貫太 | ビーチパトロール | ゴールドアリュール | 追 | 遅 | 36.4 |
| 4 | 2 | クインズショコラ | 牝4 | 53.0 | 田山旺佑 | Tiz the Law | Candy Ride | 差 | 中 | 36.8 |
| 5 | 3 | テーオーグランビル | 牡6 | 57.0 | 岩田望来 | Lea | Tapit | 先 | 中 | 34.9 |
| 6 | 3 | ハギノサステナブル | 牡6 | 56.0 | 松山弘平 | サトノダイヤモンド | タートルボウル | 追 | 遅 | 35.5 |
| 7 | 4 | モックモック | 牡6 | 57.0 | 武豊 | ダノンレジェンド | Singspiel | 先 | 中 | 35.8 |
| 8 | 4 | ピースオブザライフ | 牝6 | 52.0 | 吉村誠之助 | キタサンブラック | シンボリクリスエス | 追 | 遅 | 35.0 |
| 9 | 5 | グランドプラージュ | 牡4 | 56.5 | 川田将雅 | シニスターミニスター | キングカメハメハ | 先 | 中 | 35.0 |
| 10 | 5 | ヴィヴァン | 牡8 | 54.0 | 高杉吏麒 | ハーツクライ | Kitten's Joy | 差 | 遅 | 35.1 |
| 11 | 6 | レヴォントゥレット | 牡5 | 56.0 | 国分優作 | ロードカナロア | マンハッタンカフェ | 先 | 速 | 37.9 |
| 12 | 6 | ハピ | 牡7 | 57.5 | 幸英明 | キズナ | キングカメハメハ | 追 | 遅 | 35.7 |
| 13 | 7 | メイショウズイウン | 牡4 | 55.0 | 太宰啓介 | ホッコータルマエ | エンパイアメーカー | 差 | 遅 | 36.6 |
| 14 | 7 | メイショウユズルハ | 牡7 | 54.0 | 菱田裕二 | ディスクリートキャット | スペシャルウィーク | 差 | 遅 | 36.5 |
| 15 | 8 | ラインオブソウル | 牡7 | 54.0 | 角田大和 | シニスターミニスター | スマートボーイ | 追 | 遅 | 36.8 |
| 16 | 8 | ゴールデンクラウド | 牡4 | 56.0 | 西村淳也 | Cloud Computing | Medaglia d'Oro | 先 | 中 | 35.6 |`,
  course: "阪神ダ1800: 発走スタンド前（4角寄り）・初角まで約303m・発走直後＋ゴール前の坂2回。ダ直線352.7m・1周1517.6m・高低差1.6m。ゴール前残り約200mから勾配約1.5%の急坂。瞬発＋パワーの総合力、坂2回で消耗が出る。右回り。",
  pedigree: `【カタログ内＝再調査しない】
- キングカメハメハ(父/①, 母父/⑨⑫): 芝ダ兼用・ダ1700+・万能先行・距離穴なし。BMS=バランス(スピード+機動+底力)中立・芝ダ兼用。
- ハーツクライ(父/②⑩): 牡2400+/牝1400-1800・芝主だが持続スタミナ・晩成・後方一気。ダは母系次第。
- サトノダイヤモンド(父/⑥): ディープ系1800-2400・持続パワー・小回りローカル◎・稍重◎。芝主。
- キタサンブラック(父/⑧): 牡1800以上・芝・持続スタミナ・持続成長。
- シンボリクリスエス(母父/⑧): ロベルト系・中立〜短(ダ1700-1800芯)・スタミナ+パワー(頑健)ダ寄り・道悪◎高速×。
- シニスターミニスター(父/⑨⑮): A.P.Indy系・ダ1200-2100・道悪寄り・晩成・パワー・先行〜差し。代表テーオーケインズ。
- ロードカナロア(父/⑪): キンカメ系・芝短〜マイル・芝主だがダこなす・高速良◎/道悪割引・瞬発+スピード持続・やや晩成。
- マンハッタンカフェ(母父/⑪): SS系・スタミナ供給(晩成・牝強い)・中立〜道悪。
- キズナ(父/⑫): ディープ系1600以上・芝主だがダこなす・持続パワー・小回り◎・母父シンクリ相性。
- ホッコータルマエ(父/⑬): キンカメ系/ミスプロ・ダ2000最良(勝率18%)1000-2400・重◎・スタミナ持続パワー・成長力叩き良化・地方高適性。
- エンパイアメーカー(母父/⑬): ミスプロ系Unbridled系・中立〜短(ダ1300-2000)・パワー+持続(ダ底力)・道悪◎ダ向き。
- スペシャルウィーク(母父/⑭): SS系・スタミナ+地力底上げ・瞬発も・高速良。
- ゴールドアリュール(母父/③): 日本ダート王道のBMS。ダート全般・パワー先行(カタログ本文はエスポワールシチー経由＝砂深い地方向きパワー・延長○)。
【カタログ外＝Cがweb調査(追記候補)】
- ビーチパトロール(父/③・米Lemon Drop Kid系・芝GⅠ馬), Tiz the Law(父/④・米Constitution系3冠級), Lea(父/⑤・米Tapit産駒のダート), Tapit(母父/⑤・米ダート大BMS), ダノンレジェンド(父/⑦・Macho Uno系ダート短距離), ディスクリートキャット(父/⑭・Forestry系米ダート), Cloud Computing(父/⑯・英Bernardini系), Medaglia d'Oro(母父/⑯・米ダート/芝兼用大種牡馬), Candy Ride(母父/④), Kitten's Joy(母父/⑩・米芝), Singspiel(母父/⑦), Saint Liam(母父/②・米), Rockport Harbor(母父/①), タートルボウル(母父/⑥・欧), スマートボーイ(母父/⑮・地方ダート)。`,
  oikiri: [{name:"ゴールデンクラウド",cond:"古馬オープン",race:"6/13 阪神 11R",train_date:"6/10",course:"栗東CW",going:"良",laps:[79.0,63.7,49.6,35.9,11.7],load:"一杯",last_1f:11.7}],
  seed: {horses:[{no:1,name:"リチュアル",style:"差",ten_speed:"中",agari_best:37.8,recent:[{first_corner:7,field:15,agari:38.4,date:"2026-03-08",venue:"中山",race:"総武S",pos:8},{first_corner:3,field:16,agari:38.1,date:"2026-01-11",venue:"中山",race:"ポルックスS",pos:3},{first_corner:5,field:12,agari:37.8,date:"2025-10-19",venue:"東京",race:"ブラジルC",pos:7},{first_corner:4,field:16,agari:37.8,date:"2025-08-30",venue:"中京",race:"名古屋城S",pos:2}]},{no:2,name:"マリアナトレンチ",style:"差",ten_speed:"遅",agari_best:36.8,recent:[{first_corner:9,field:15,agari:37.9,date:"2026-04-11",venue:"福島",race:"吾妻小富士S",pos:7},{first_corner:8,field:15,agari:38.1,date:"2026-02-01",venue:"小倉",race:"門司S",pos:13},{first_corner:11,field:15,agari:38.3,date:"2025-11-16",venue:"福島",race:"福島民友C",pos:12},{first_corner:8,field:14,agari:36.8,date:"2025-10-26",venue:"京都",race:"カノープスS",pos:4}]},{no:3,name:"サンマルパトロール",style:"追",ten_speed:"遅",agari_best:36.4,recent:[{first_corner:14,field:15,agari:36.4,date:"2026-02-01",venue:"小倉",race:"門司S",pos:5},{first_corner:16,field:16,agari:37.9,date:"2026-01-11",venue:"中山",race:"ポルックスS",pos:8},{first_corner:10,field:15,agari:38.7,date:"2025-09-20",venue:"中山",race:"イサ殿下来場",pos:10},{first_corner:14,field:16,agari:38.6,date:"2025-08-30",venue:"中京",race:"名古屋城S",pos:13}]},{no:4,name:"クインズショコラ",style:"差",ten_speed:"中",agari_best:36.8,recent:[{first_corner:5,field:15,agari:38.1,date:"2026-05-02",venue:"新潟",race:"三条S",pos:1},{first_corner:5,field:13,agari:37.8,date:"2026-03-21",venue:"中山",race:"韓国馬事会杯",pos:4},{first_corner:3,field:15,agari:37.3,date:"2026-02-28",venue:"阪神",race:"牝2勝クラス",pos:1},{first_corner:4,field:10,agari:36.8,date:"2026-01-04",venue:"京都",race:"牝1勝クラス",pos:1}]},{no:5,name:"テーオーグランビル",style:"先",ten_speed:"中",agari_best:34.9,recent:[{first_corner:9,field:16,agari:38.2,date:"2026-05-10",venue:"京都",race:"平城京S",pos:12},{first_corner:2,field:16,agari:36.8,date:"2026-03-22",venue:"阪神",race:"レグルスS",pos:1},{first_corner:2,field:16,agari:39.5,date:"2026-01-11",venue:"中山",race:"ポルックスS",pos:12},{first_corner:1,field:13,agari:34.9,date:"2025-11-01",venue:"京都",race:"ハロウィンS",pos:1}]},{no:6,name:"ハギノサステナブル",style:"追",ten_speed:"遅",agari_best:35.5,recent:[{first_corner:12,field:16,agari:36.1,date:"2026-05-03",venue:"東京",race:"ブリリアント",pos:5},{first_corner:16,field:16,agari:35.5,date:"2026-03-22",venue:"阪神",race:"レグルスS",pos:4},{first_corner:15,field:15,agari:36.2,date:"2026-02-01",venue:"小倉",race:"門司S",pos:2},{first_corner:12,field:16,agari:37.7,date:"2026-01-11",venue:"中山",race:"ポルックスS",pos:4}]},{no:7,name:"モックモック",style:"先",ten_speed:"中",agari_best:35.8,recent:[{first_corner:4,field:16,agari:35.8,date:"2026-04-18",venue:"阪神",race:"アンタレスS",pos:2},{first_corner:5,field:16,agari:36.6,date:"2026-03-22",venue:"阪神",race:"レグルスS",pos:3},{first_corner:6,field:16,agari:36.0,date:"2026-01-12",venue:"京都",race:"雅ステークス",pos:1},{first_corner:3,field:14,agari:35.8,date:"2025-11-23",venue:"京都",race:"2勝クラス",pos:1}]},{no:8,name:"ピースオブザライフ",style:"追",ten_speed:"遅",agari_best:35.0,recent:[{first_corner:13,field:16,agari:37.4,date:"2026-03-22",venue:"阪神",race:"レグルスS",pos:14},{first_corner:12,field:15,agari:37.3,date:"2026-02-01",venue:"小倉",race:"門司S",pos:7},{first_corner:15,field:15,agari:37.5,date:"2025-11-16",venue:"福島",race:"福島民友C",pos:5},{first_corner:2,field:16,agari:35.0,date:"2025-10-12",venue:"東京",race:"アイルランド",pos:15}]},{no:9,name:"グランドプラージュ",style:"先",ten_speed:"中",agari_best:35.0,recent:[{first_corner:4,field:16,agari:36.0,date:"2026-05-10",venue:"京都",race:"平城京S",pos:2},{first_corner:3,field:10,agari:35.0,date:"2026-02-15",venue:"京都",race:"北山S",pos:1},{first_corner:8,field:13,agari:35.9,date:"2026-01-04",venue:"京都",race:"天ケ瀬特別",pos:1},{first_corner:5,field:14,agari:35.6,date:"2025-11-23",venue:"京都",race:"2勝クラス",pos:2}]},{no:10,name:"ヴィヴァン",style:"差",ten_speed:"遅",agari_best:35.1,recent:[{first_corner:8,field:15,agari:36.2,date:"2026-04-26",venue:"東京",race:"オアシスS",pos:10},{first_corner:8,field:16,agari:35.1,date:"2026-02-15",venue:"東京",race:"バレンタイン",pos:3},{first_corner:7,field:16,agari:35.8,date:"2026-01-31",venue:"東京",race:"白嶺S",pos:1},{first_corner:7,field:13,agari:36.6,date:"2025-07-20",venue:"小倉",race:"宮崎S",pos:3}]},{no:11,name:"レヴォントゥレット",style:"先",ten_speed:"速",agari_best:37.9,recent:[{first_corner:4,field:16,agari:37.9,date:"2026-05-03",venue:"東京",race:"ブリリアント",pos:12},{first_corner:1,field:15,agari:40.5,date:"2026-03-29",venue:"中山",race:"マーチS",pos:15},{first_corner:2,field:15,agari:38.7,date:"2026-03-08",venue:"中山",race:"総武S",pos:5}]},{no:12,name:"ハピ",style:"追",ten_speed:"遅",agari_best:35.7,recent:[{first_corner:13,field:16,agari:35.7,date:"2026-04-18",venue:"阪神",race:"アンタレスS",pos:7},{first_corner:14,field:16,agari:37.7,date:"2026-02-28",venue:"阪神",race:"仁川S",pos:10},{first_corner:16,field:16,agari:35.9,date:"2026-01-25",venue:"京都",race:"プロキオンS",pos:6}]},{no:13,name:"メイショウズイウン",style:"差",ten_speed:"遅",agari_best:36.6,recent:[{first_corner:4,field:16,agari:37.8,date:"2026-05-03",venue:"東京",race:"ブリリアント",pos:11},{first_corner:15,field:16,agari:37.0,date:"2026-04-18",venue:"阪神",race:"アンタレスS",pos:13},{first_corner:8,field:16,agari:36.6,date:"2026-03-22",venue:"阪神",race:"レグルスS",pos:6},{first_corner:5,field:11,agari:36.7,date:"2025-12-20",venue:"中京",race:"尾頭橋S",pos:1}]},{no:14,name:"メイショウユズルハ",style:"差",ten_speed:"遅",agari_best:36.5,recent:[{first_corner:6,field:16,agari:37.3,date:"2026-05-03",venue:"東京",race:"ブリリアント",pos:10},{first_corner:15,field:16,agari:36.5,date:"2026-03-22",venue:"阪神",race:"レグルスS",pos:11},{first_corner:7,field:16,agari:38.3,date:"2026-02-07",venue:"京都",race:"アルデバラン",pos:5},{first_corner:13,field:16,agari:38.1,date:"2025-05-11",venue:"京都",race:"平城京S",pos:15}]},{no:15,name:"ラインオブソウル",style:"追",ten_speed:"遅",agari_best:36.8,recent:[{first_corner:5,field:16,agari:36.8,date:"2026-03-22",venue:"阪神",race:"レグルスS",pos:7},{first_corner:14,field:16,agari:38.8,date:"2026-01-11",venue:"中山",race:"ポルックスS",pos:15},{first_corner:13,field:14,agari:38.2,date:"2025-09-27",venue:"阪神",race:"シリウスS",pos:12},{first_corner:9,field:12,agari:38.6,date:"2025-08-03",venue:"中京",race:"名鉄杯",pos:10}]},{no:16,name:"ゴールデンクラウド",style:"先",ten_speed:"中",agari_best:35.6,recent:[{first_corner:2,field:15,agari:36.8,date:"2026-03-29",venue:"中京",race:"伊勢S",pos:1},{first_corner:2,field:10,agari:35.6,date:"2026-02-15",venue:"京都",race:"北山S",pos:2},{first_corner:5,field:16,agari:37.7,date:"2025-11-16",venue:"京都",race:"2勝クラス",pos:1},{first_corner:3,field:15,agari:37.9,date:"2025-10-18",venue:"新潟",race:"1勝クラス",pos:1}]}],h2h:[{date:"2026-05-10",venue:"京都",race:"平城京S",horses:[{no:9,pos:2},{no:5,pos:12}]},{date:"2026-05-03",venue:"東京",race:"ブリリアント",horses:[{no:11,pos:12},{no:13,pos:11},{no:14,pos:10},{no:6,pos:5}]},{date:"2026-04-18",venue:"阪神",race:"アンタレスS",horses:[{no:7,pos:2},{no:12,pos:7},{no:13,pos:13}]},{date:"2026-03-22",venue:"阪神",race:"レグルスS",horses:[{no:5,pos:1},{no:7,pos:3},{no:15,pos:7},{no:13,pos:6},{no:8,pos:14},{no:14,pos:11},{no:6,pos:4}]},{date:"2026-02-15",venue:"京都",race:"北山S",horses:[{no:16,pos:2},{no:9,pos:1}]},{date:"2026-02-01",venue:"小倉",race:"門司S",horses:[{no:2,pos:13},{no:8,pos:7},{no:3,pos:5},{no:6,pos:2}]},{date:"2026-01-11",venue:"中山",race:"ポルックスS",horses:[{no:5,pos:12},{no:1,pos:3},{no:6,pos:4},{no:15,pos:15},{no:3,pos:8}]},{date:"2025-11-23",venue:"京都",race:"2勝クラス",horses:[{no:7,pos:1},{no:9,pos:2}]}]},
  points: [{id:"A"},{id:"B"},{id:"C"},{id:"D"},{id:"E"},{id:"F"},{id:"G"},{id:"H"},{id:"I"},{id:"K"},{id:"L"}],
}

const AGENT_OF = { A:'obs-a-index', B:'obs-b-recent', C:'obs-c-pedigree', D:'obs-d-aptitude', E:'obs-e-pace',
                   F:'obs-f-training', G:'obs-g-rotation', H:'obs-h-paddock', I:'obs-i-risk', K:'obs-k-jockey',
                   L:'obs-l-repeater' }

const RESULT_SCHEMA = {
  type:'object',
  properties:{
    point:{type:'string'},
    overall_confidence:{type:'string'},
    field_note:{type:'string'},
    horses:{type:'array', items:{type:'object', properties:{
      no:{type:'integer'}, name:{type:'string'},
      pros:{type:'array', items:{type:'string'}},
      cons:{type:'array', items:{type:'string'}},
      score:{type:'number'}, confidence:{type:'string'},
      sources:{type:'array', items:{type:'string'}}
    }, required:['no','name','pros','cons','score','confidence']}},
    note:{type:'string'}
  }, required:['point','overall_confidence','horses']
}

const PACE_EVIDENCE_SCHEMA = {
  type:'object',
  properties:{
    point:{type:'string'},
    overall_confidence:{type:'string'},
    legs:{type:'array', items:{type:'object', properties:{
      no:{type:'integer'}, name:{type:'string'}, style:{type:'string'},
      ten_speed:{type:'string'}, expected_pos:{type:'string'}, note:{type:'string'}
    }, required:['no','name','style']}},
    lead_contenders:{type:'array', items:{type:'object', properties:{
      no:{type:'integer'}, name:{type:'string'}, stance:{type:'string'}
    }, required:['no','stance']}},
    draw:{type:'array', items:{type:'object', properties:{
      no:{type:'integer'}, note:{type:'string'}
    }}},
    field_note:{type:'string'}
  }, required:['point','legs','lead_contenders']
}

const PACE_MODEL_SCHEMA = {
  type:'object',
  properties:{
    patterns:{type:'array', items:{type:'object', properties:{
      id:{type:'string'}, name:{type:'string'}, prob:{type:'number'},
      likelihood_tier:{type:'string'}, trigger:{type:'string'},
      first_600m:{type:'string'}, pace_level:{type:'number'},
      leg_advantage:{type:'string'},
      formation_head:{type:'string'}, formation_last_corner:{type:'string'},
      bias:{type:'string'},
      phase_flow:{type:'object', properties:{
        early:{type:'string'}, mid:{type:'string'}, late:{type:'string'}, result:{type:'string'}
      }, required:['early','mid','late','result']},
      per_horse_fit:{type:'array', items:{type:'object', properties:{
        no:{type:'integer'}, name:{type:'string'}, fit:{type:'string'}, why:{type:'string'}
      }, required:['no','fit']}}
    }, required:['id','name','prob','likelihood_tier','trigger','pace_level','leg_advantage','phase_flow']}},
    falsification:{type:'string'},
    field_note:{type:'string'}
  }, required:['patterns']
}

const CREED =
  `# 鉄則（全観点共通）\n` +
  `- 対象は全出走馬、1頭ずつ漏れなく。馬番・馬名を必ず明記。\n` +
  `- 出典URL必須。推定は「推定」と明記し確信度を下げる。捏造しない＝取得できない項目は欠損として確信度「低」。\n` +
  `- 純粋情報のみ: オッズ・人気・オッズ変動・他人の予想/印/予想展開記事は使わない。関係者コメント・媒体の主観評価(調教/パドック点)は採用可。`

phase('Research')
const research = await parallel(DATA.points.map(p => () =>
  agent(
    `# レース条件\n${DATA.condition}\n\n# 出走馬（全頭）\n${DATA.horses}\n` +
    (['E','C','B'].includes(p.id) ? `\n# スクレイパ seed（検証・補強の起点／ゼロから取り直さない）\n${JSON.stringify(DATA.seed)}\n` : ``) +
    (p.id==='C' ? `\n# 血統カタログ該当行（pedigree-catalog.md・カタログ内は再調査しない／カタログ外の血だけweb調査）\n${DATA.pedigree||''}` : ``) +
    (['D','E'].includes(p.id) ? `\n# コース物理形状（course-geometry.md 該当行・再調査しない）\n${DATA.course||''}` : ``) +
    (p.id==='F' ? `\n# 追い切り好時計 seed（fetch_oikiri.py・好時計の上位抜粋＝全頭でない。不在馬はweb補完）\n${JSON.stringify(DATA.oikiri||[])}` : ``) +
    `\n${CREED}\n- 結果全文を data/races/${DATA.raceId}/research-${p.id}.md に保存し、スキーマの構造化要約を返す。`,
    { label:`research:${p.id}`, phase:'Research', schema: p.id==='E'?PACE_EVIDENCE_SCHEMA:RESULT_SCHEMA, agentType: AGENT_OF[p.id] }
  ).catch(()=>null)
)).then(rs => rs.filter(Boolean))

phase('PaceSynthesis')
const paceModel = await agent(
  `あなたは展開合成器。pace-synthesis.md に従い、以下の全証拠を突き合わせ、全馬の配置から創発する` +
  `複数の名前付き展開パターン（確率＋発動トリガー＋脚質別有利不利＋隊列＋段階フロー phase_flow＋per_horse_fit）を構築せよ。Σprob=1。` +
  `各パターンに phase_flow{early,mid,late,result} を「序盤→A_early→中盤→A_cruise→終盤→A_finish→結果」の因果文で必ず著作する。` +
  `関係者の戦法宣言＞推測、近走の実脚質＞一般ラベル、先行争いが不確実なら別パターンに分岐。` +
  `阪神ダ1800は初角まで約303mで先行争いが起きやすく坂2回で消耗する点を必ず織り込む。\n` +
  `# 全証拠\n${JSON.stringify(research)}\n# 条件\n${DATA.condition}`,
  { label:'pace-synthesis', phase:'PaceSynthesis', schema: PACE_MODEL_SCHEMA, agentType:'general-purpose' }
)
return { research, paceModel }
