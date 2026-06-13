# 分析コンテキスト（静的・正本／web再調査しない）

## レース条件
函館日刊スポーツ杯 / 2026-06-14(日)15:15 / 函館 芝1200m 右回り(洋芝) / 3勝クラス / 16頭・枠確定。コース: 直線262.1m(JRA最短)・2角奥ポケット発走で初角まで約490m・終盤下りで前残り(逃げ先行有利)・洋芝で時計かかる・開催後半は内荒れ・芝スタート無し。

## コース物理形状（course-geometry.md 正本・D/E/展開合成用）
函館 芝1200: 2角奥ポケット発走/初角まで約490m/直線262.1m(JRA最短・洋芝)/起伏=ゴール過ぎ→2角下り(2角が最低)→向正面〜3角上り→3-4角内に頂上→直線半ばまで緩い下り→ゴール前平坦/終盤が下り=前が止まりにくく逃げ先行有利の構造/開催後半は内荒れで馬場差大/芝スタート無し。函館SS型(上り区間が長いのにテン速い→下りで前残り)。

# 血統カタログ該当行(pedigree-catalog.md・カタログ内は再調査しない/カタログ外は web 調査して追記候補で報告)
## 巻頭原則(要点)
- すべて傾向=一次フィルタ。個体の近走・馬体・実績が血統を上書きする。
- 母父は系統名で決め打たず「供給する質」を見る。決め手: 瞬発→A_finish/持続・スタミナ→A_cruise+A_finish/先行力→A_early。
- 道悪・成長型は系統で一次フィルタ→着度数で本判定(系統名だけの機械決め打ち禁止)。
## 父(カタログ内)
- ロードカナロア: キンカメ系/芝短〜マイル(母系で2400も)/芝主ダこなす/高速良◎道悪割引/やや晩成(4歳完成)/瞬発+スピード持続/母系の質を引き出す/確信度高
- アドマイヤマーズ: ダイワメジャー系(SS系)/芝〜1200・マイルも/芝主ダも/良/早熟/先行+瞬発/左回り・ローカル短距離A級/確信度中  [#2マーブルパレス・#15ベビーズブレスの父]
- スワーヴリチャード: ハーツ系/1600以上/芝/良の速い時計◎洋芝も/標準〜早/瞬発+持続/確信度高  [#6ライツユーアップの父]
- ジャスタウェイ: ハーツ系/牡中距離・牝1200-1600/芝ダ両用/道悪可/やや晩成/持続/牝1200-1600で適性/確信度中高  [#16フミサウンドの父]
## 母父(カタログ内)
- クロフネ: ND系/短縮/パワー+スピード・ダート化/ダ化道悪◎/母父でダート・パワー供給の典型/確信度中高  [#2マーブルパレスの母父]
- シンボリクリスエス: ロベルト系/中立〜短(ダ1700-1800芯)/スタミナ+パワー(頑健)ダ寄り/道悪◎高速×/確信度中高  [#3ムチャスグラシアスの母父]
- アグネスタキオン: SS系/非根幹(1400/1800/2200)/スピード+体力・瞬発/高速◎道悪も/地力供給源/確信度中  [#7リリーフィールドの母父]
- ブラックタイド: SS系/牡2000牝1400/芝ダ兼用/やや早熟/先行・器用/確信度中  [#8ガットネロの母父]
## カタログ外(C が web 調査): 父=カリフォルニアクローム/リアルインパクト/モズアスコット/アメリカンペイトリオット/ミスターメロディ/ニューイヤーズデイ/ゴールドアクター/インディチャンプ/サトノクラウン/Iffraaj/Kingman, 母父=Hard Spun/Frankel/ヨハネスブルグ/エアジハード/ファスリエフ/ダイワメジャー/ケイムホーム/Kittens Joy/タイキシャトル/Dark Angel/Galileo/Redoutes Choice

## スクレイパ seed（fetch_racecard JRA・E/C/B の検証起点／ゼロから取り直さない）
```json
{
 "race_id": "202606140211",
 "source": "jra",
 "n": 16,
 "surface": "芝",
 "distance": 1200,
 "headcount": 16,
 "draw_fixed": true,
 "horses": [
  {
   "no": 1,
   "waku": 1,
   "name": "ハリウッドメモリー",
   "sex_age": "牝4/黒鹿",
   "weight": "56.0",
   "jockey": "横山 和生",
   "sire": "ロードカナロア",
   "damsire": "Hard Spun",
   "style": "差",
   "ten_speed": "中",
   "agari_best": 33.9,
   "recent": [
    {
     "first_corner": 6,
     "field": 18,
     "agari": 34.7,
     "date": "2026-02-15",
     "venue": "小倉",
     "race": "大濠特別",
     "pos": 5
    },
    {
     "first_corner": 6,
     "field": 15,
     "agari": 33.9,
     "date": "2026-02-01",
     "venue": "小倉",
     "race": "周防灘特別",
     "pos": 2
    },
    {
     "first_corner": 11,
     "field": 16,
     "agari": 33.9,
     "date": "2025-11-29",
     "venue": "京都",
     "race": "2勝クラス",
     "pos": 10
    },
    {
     "first_corner": 7,
     "field": 16,
     "agari": 34.5,
     "date": "2025-09-06",
     "venue": "札幌",
     "race": "札幌スポニチ",
     "pos": 3
    }
   ]
  },
  {
   "no": 2,
   "waku": 1,
   "name": "マーブルパレス",
   "sex_age": "牝3/芦",
   "weight": "53.0",
   "jockey": "斎藤 新",
   "sire": "アドマイヤマーズ",
   "damsire": "クロフネ",
   "style": "逃",
   "ten_speed": "中",
   "agari_best": 33.9,
   "recent": [
    {
     "first_corner": 2,
     "field": 9,
     "agari": 34.7,
     "date": "2026-02-28",
     "venue": "阪神",
     "race": "マーガレット",
     "pos": 5
    },
    {
     "first_corner": 5,
     "field": 9,
     "agari": 34.8,
     "date": "2026-01-17",
     "venue": "京都",
     "race": "紅梅S",
     "pos": 7
    },
    {
     "first_corner": 1,
     "field": 13,
     "agari": 33.9,
     "date": "2025-12-13",
     "venue": "中山",
     "race": "黒松賞",
     "pos": 1
    },
    {
     "first_corner": 1,
     "field": 12,
     "agari": 34.8,
     "date": "2025-11-01",
     "venue": "京都",
     "race": "ファンタジー",
     "pos": 9
    }
   ]
  },
  {
   "no": 3,
   "waku": 2,
   "name": "ムチャスグラシアス",
   "sex_age": "牝5/栗",
   "weight": "56.0",
   "jockey": "国分 恭介",
   "sire": "カリフォルニアクローム",
   "damsire": "シンボリクリスエス",
   "style": "追",
   "ten_speed": "遅",
   "agari_best": 34.6,
   "recent": [
    {
     "first_corner": 12,
     "field": 16,
     "agari": 34.6,
     "date": "2026-04-11",
     "venue": "福島",
     "race": "花見山特別",
     "pos": 12
    },
    {
     "first_corner": 12,
     "field": 16,
     "agari": 34.9,
     "date": "2025-12-27",
     "venue": "中山",
     "race": "ベストウィッ",
     "pos": 13
    },
    {
     "first_corner": 14,
     "field": 16,
     "agari": 37.1,
     "date": "2025-11-09",
     "venue": "東京",
     "race": "2勝クラス",
     "pos": 13
    },
    {
     "first_corner": 3,
     "field": 16,
     "agari": 35.4,
     "date": "2025-09-06",
     "venue": "札幌",
     "race": "札幌スポニチ",
     "pos": 7
    }
   ]
  },
  {
   "no": 4,
   "waku": 2,
   "name": "エクストラバック",
   "sex_age": "牡5/鹿",
   "weight": "58.0",
   "jockey": "池添 謙一",
   "sire": "Iffraaj",
   "damsire": "Frankel",
   "style": "差",
   "ten_speed": "中",
   "agari_best": 33.8,
   "recent": [
    {
     "first_corner": 14,
     "field": 18,
     "agari": 34.3,
     "date": "2026-02-28",
     "venue": "阪神",
     "race": "2勝クラス",
     "pos": 12
    },
    {
     "first_corner": 7,
     "field": 13,
     "agari": 34.6,
     "date": "2026-02-10",
     "venue": "京都",
     "race": "2勝クラス",
     "pos": 6
    },
    {
     "first_corner": 5,
     "field": 16,
     "agari": 33.8,
     "date": "2026-01-17",
     "venue": "中山",
     "race": "2勝クラス",
     "pos": 6
    },
    {
     "first_corner": 3,
     "field": 15,
     "agari": 34.6,
     "date": "2025-11-16",
     "venue": "京都",
     "race": "2勝クラス",
     "pos": 11
    }
   ]
  },
  {
   "no": 5,
   "waku": 3,
   "name": "ゴキゲンサン",
   "sex_age": "牝6/鹿",
   "weight": "56.0",
   "jockey": "岩田 康誠",
   "sire": "リアルインパクト",
   "damsire": "ヨハネスブルグ",
   "style": "追",
   "ten_speed": "遅",
   "agari_best": 33.5,
   "recent": [
    {
     "first_corner": 12,
     "field": 16,
     "agari": 34.1,
     "date": "2026-04-11",
     "venue": "福島",
     "race": "花見山特別",
     "pos": 10
    },
    {
     "first_corner": 8,
     "field": 18,
     "agari": 36.1,
     "date": "2026-01-17",
     "venue": "京都",
     "race": "2勝クラス",
     "pos": 17
    },
    {
     "first_corner": 7,
     "field": 16,
     "agari": 34.9,
     "date": "2025-12-27",
     "venue": "中山",
     "race": "ベストウィッ",
     "pos": 11
    },
    {
     "first_corner": 14,
     "field": 16,
     "agari": 33.5,
     "date": "2025-09-27",
     "venue": "中山",
     "race": "勝浦特別",
     "pos": 11
    }
   ]
  },
  {
   "no": 6,
   "waku": 3,
   "name": "ライツユーアップ",
   "sex_age": "牝4/栗",
   "weight": "56.0",
   "jockey": "吉田 隼人",
   "sire": "スワーヴリチャード",
   "damsire": "エアジハード",
   "style": "先",
   "ten_speed": "中",
   "agari_best": 33.8,
   "recent": [
    {
     "first_corner": 6,
     "field": 11,
     "agari": 33.8,
     "date": "2026-04-26",
     "venue": "東京",
     "race": "牝2勝クラス",
     "pos": 9
    },
    {
     "first_corner": 4,
     "field": 16,
     "agari": 34.0,
     "date": "2026-04-11",
     "venue": "福島",
     "race": "牝1勝クラス",
     "pos": 1
    },
    {
     "first_corner": 3,
     "field": 14,
     "agari": 34.3,
     "date": "2026-03-29",
     "venue": "阪神",
     "race": "1勝クラス",
     "pos": 4
    },
    {
     "first_corner": 15,
     "field": 17,
     "agari": 34.4,
     "date": "2026-02-07",
     "venue": "小倉",
     "race": "牝1勝クラス",
     "pos": 8
    }
   ]
  },
  {
   "no": 7,
   "waku": 4,
   "name": "リリーフィールド",
   "sex_age": "牝4/栗",
   "weight": "56.0",
   "jockey": "佐々木 大輔",
   "sire": "モズアスコット",
   "damsire": "アグネスタキオン",
   "style": "先",
   "ten_speed": "中",
   "agari_best": 33.6,
   "recent": [
    {
     "first_corner": 3,
     "field": 9,
     "agari": 33.6,
     "date": "2026-04-04",
     "venue": "阪神",
     "race": "2勝クラス",
     "pos": 3
    },
    {
     "first_corner": 3,
     "field": 13,
     "agari": 35.2,
     "date": "2026-02-10",
     "venue": "京都",
     "race": "2勝クラス",
     "pos": 10
    },
    {
     "first_corner": 4,
     "field": 16,
     "agari": 38.7,
     "date": "2025-11-08",
     "venue": "京都",
     "race": "亀岡特別",
     "pos": 9
    }
   ]
  },
  {
   "no": 8,
   "waku": 4,
   "name": "ガットネロ",
   "sex_age": "牝6/黒鹿",
   "weight": "56.0",
   "jockey": "小沢 大仁",
   "sire": "アメリカンペイトリオット",
   "damsire": "ブラックタイド",
   "style": "先",
   "ten_speed": "中",
   "agari_best": 33.3,
   "recent": [
    {
     "first_corner": 9,
     "field": 12,
     "agari": 33.3,
     "date": "2026-04-18",
     "venue": "中山",
     "race": "袖ケ浦特別",
     "pos": 11
    },
    {
     "first_corner": 7,
     "field": 13,
     "agari": 35.9,
     "date": "2026-02-10",
     "venue": "京都",
     "race": "2勝クラス",
     "pos": 12
    },
    {
     "first_corner": 2,
     "field": 16,
     "agari": 34.5,
     "date": "2025-11-22",
     "venue": "福島",
     "race": "1勝クラス",
     "pos": 1
    },
    {
     "first_corner": 2,
     "field": 16,
     "agari": 34.8,
     "date": "2025-11-08",
     "venue": "福島",
     "race": "1勝クラス",
     "pos": 4
    }
   ]
  },
  {
   "no": 9,
   "waku": 5,
   "name": "ミニョンマルーン",
   "sex_age": "牝4/鹿",
   "weight": "56.0",
   "jockey": "長浜 鴻緒",
   "sire": "ミスターメロディ",
   "damsire": "ファスリエフ",
   "style": "逃",
   "ten_speed": "速",
   "agari_best": 33.5,
   "recent": [
    {
     "first_corner": 1,
     "field": 16,
     "agari": 38.4,
     "date": "2026-04-12",
     "venue": "福島",
     "race": "喜多方特別",
     "pos": 10
    },
    {
     "first_corner": 3,
     "field": 15,
     "agari": 34.5,
     "date": "2026-02-01",
     "venue": "小倉",
     "race": "周防灘特別",
     "pos": 9
    },
    {
     "first_corner": 1,
     "field": 16,
     "agari": 35.6,
     "date": "2025-12-27",
     "venue": "中山",
     "race": "ベストウィッ",
     "pos": 8
    },
    {
     "first_corner": 4,
     "field": 13,
     "agari": 33.5,
     "date": "2025-12-06",
     "venue": "中山",
     "race": "2勝クラス",
     "pos": 5
    }
   ]
  },
  {
   "no": 10,
   "waku": 5,
   "name": "スミレファースト",
   "sex_age": "牝5/鹿",
   "weight": "56.0",
   "jockey": "小崎 綾也",
   "sire": "ニューイヤーズデイ",
   "damsire": "ダイワメジャー",
   "style": "追",
   "ten_speed": "遅",
   "agari_best": 36.6,
   "recent": [
    {
     "first_corner": 14,
     "field": 16,
     "agari": 36.9,
     "date": "2026-03-22",
     "venue": "中山",
     "race": "鎌ケ谷特別",
     "pos": 12
    },
    {
     "first_corner": 13,
     "field": 16,
     "agari": 37.8,
     "date": "2026-03-01",
     "venue": "中山",
     "race": "2勝クラス",
     "pos": 16
    },
    {
     "first_corner": 9,
     "field": 15,
     "agari": 37.4,
     "date": "2025-11-24",
     "venue": "東京",
     "race": "牝2勝クラス",
     "pos": 10
    },
    {
     "first_corner": 6,
     "field": 16,
     "agari": 36.6,
     "date": "2025-11-09",
     "venue": "東京",
     "race": "2勝クラス",
     "pos": 4
    }
   ]
  },
  {
   "no": 11,
   "waku": 6,
   "name": "エクセルゴールド",
   "sex_age": "牡5/青",
   "weight": "58.0",
   "jockey": "小林 美駒",
   "sire": "ゴールドアクター",
   "damsire": "ケイムホーム",
   "style": "追",
   "ten_speed": "遅",
   "agari_best": 33.5,
   "recent": [
    {
     "first_corner": 6,
     "field": 16,
     "agari": 34.8,
     "date": "2026-03-08",
     "venue": "中山",
     "race": "2勝クラス",
     "pos": 10
    },
    {
     "first_corner": 13,
     "field": 16,
     "agari": 33.5,
     "date": "2026-01-17",
     "venue": "中山",
     "race": "2勝クラス",
     "pos": 11
    },
    {
     "first_corner": 13,
     "field": 15,
     "agari": 34.4,
     "date": "2025-11-16",
     "venue": "京都",
     "race": "2勝クラス",
     "pos": 14
    }
   ]
  },
  {
   "no": 12,
   "waku": 6,
   "name": "フェアリーライズ",
   "sex_age": "牝3/黒鹿",
   "weight": "53.0",
   "jockey": "黛 弘人",
   "sire": "インディチャンプ",
   "damsire": "Kitten's Joy",
   "style": "差",
   "ten_speed": "中",
   "agari_best": 36.8,
   "recent": [
    {
     "first_corner": 7,
     "field": 16,
     "agari": 36.8,
     "date": "2026-03-14",
     "venue": "中山",
     "race": "アネモネS",
     "pos": 14
    }
   ]
  },
  {
   "no": 13,
   "waku": 7,
   "name": "ヴィヴァクラウン",
   "sex_age": "牡5/鹿",
   "weight": "58.0",
   "jockey": "横山 琉人",
   "sire": "サトノクラウン",
   "damsire": "タイキシャトル",
   "style": "先",
   "ten_speed": "中",
   "agari_best": 33.3,
   "recent": [
    {
     "first_corner": 8,
     "field": 12,
     "agari": 33.3,
     "date": "2026-04-18",
     "venue": "中山",
     "race": "袖ケ浦特別",
     "pos": 6
    },
    {
     "first_corner": 2,
     "field": 11,
     "agari": 35.2,
     "date": "2026-03-29",
     "venue": "中山",
     "race": "2勝クラス",
     "pos": 9
    },
    {
     "first_corner": 4,
     "field": 18,
     "agari": 35.4,
     "date": "2026-03-01",
     "venue": "小倉",
     "race": "1勝クラス",
     "pos": 1
    },
    {
     "first_corner": 4,
     "field": 16,
     "agari": 34.4,
     "date": "2026-01-25",
     "venue": "小倉",
     "race": "八幡特別",
     "pos": 10
    }
   ]
  },
  {
   "no": 14,
   "waku": 7,
   "name": "フードマン",
   "sex_age": "牡4/鹿",
   "weight": "58.0",
   "jockey": "鮫島 克駿",
   "sire": "Kingman",
   "damsire": "Dark Angel",
   "style": "差",
   "ten_speed": "中",
   "agari_best": 33.7,
   "recent": [
    {
     "first_corner": 5,
     "field": 11,
     "agari": 34.8,
     "date": "2026-03-28",
     "venue": "阪神",
     "race": "仲春特別",
     "pos": 4
    },
    {
     "first_corner": 5,
     "field": 15,
     "agari": 33.7,
     "date": "2026-03-14",
     "venue": "阪神",
     "race": "讃岐特別",
     "pos": 4
    },
    {
     "first_corner": 11,
     "field": 15,
     "agari": 33.8,
     "date": "2026-02-01",
     "venue": "小倉",
     "race": "周防灘特別",
     "pos": 11
    },
    {
     "first_corner": 5,
     "field": 18,
     "agari": 34.2,
     "date": "2026-01-10",
     "venue": "京都",
     "race": "鹿ケ谷特別",
     "pos": 5
    }
   ]
  },
  {
   "no": 15,
   "waku": 8,
   "name": "ベビーズブレス",
   "sex_age": "牝4/栗",
   "weight": "56.0",
   "jockey": "舟山 瑠泉",
   "sire": "アドマイヤマーズ",
   "damsire": "Galileo",
   "style": "差",
   "ten_speed": "中",
   "agari_best": 34.4,
   "recent": [
    {
     "first_corner": 8,
     "field": 15,
     "agari": 34.5,
     "date": "2026-03-14",
     "venue": "阪神",
     "race": "讃岐特別",
     "pos": 14
    },
    {
     "first_corner": 2,
     "field": 18,
     "agari": 36.6,
     "date": "2026-02-15",
     "venue": "小倉",
     "race": "大濠特別",
     "pos": 16
    },
    {
     "first_corner": 7,
     "field": 16,
     "agari": 34.4,
     "date": "2025-11-29",
     "venue": "京都",
     "race": "2勝クラス",
     "pos": 7
    },
    {
     "first_corner": 1,
     "field": 16,
     "agari": 35.3,
     "date": "2025-09-06",
     "venue": "札幌",
     "race": "札幌スポニチ",
     "pos": 5
    }
   ]
  },
  {
   "no": 16,
   "waku": 8,
   "name": "フミサウンド",
   "sex_age": "牡6/黒鹿",
   "weight": "58.0",
   "jockey": "浜中 俊",
   "sire": "ジャスタウェイ",
   "damsire": "Redoute's Choice",
   "style": "差",
   "ten_speed": "遅",
   "agari_best": 33.4,
   "recent": [
    {
     "first_corner": 9,
     "field": 16,
     "agari": 33.4,
     "date": "2026-05-23",
     "venue": "東京",
     "race": "高尾特別",
     "pos": 6
    },
    {
     "first_corner": 12,
     "field": 16,
     "agari": 33.6,
     "date": "2026-04-25",
     "venue": "福島",
     "race": "医王寺特別",
     "pos": 14
    },
    {
     "first_corner": 5,
     "field": 16,
     "agari": 37.0,
     "date": "2026-02-15",
     "venue": "東京",
     "race": "2勝クラス",
     "pos": 12
    },
    {
     "first_corner": 10,
     "field": 16,
     "agari": 37.7,
     "date": "2025-11-30",
     "venue": "東京",
     "race": "アプローズ賞",
     "pos": 14
    }
   ]
  }
 ],
 "h2h": [
  {
   "date": "2026-04-18",
   "venue": "中山",
   "race": "袖ケ浦特別",
   "horses": [
    {
     "no": 13,
     "name": "ヴィヴァクラウン",
     "first_corner": 8,
     "pos": 6
    },
    {
     "no": 8,
     "name": "ガットネロ",
     "first_corner": 9,
     "pos": 11
    }
   ]
  },
  {
   "date": "2026-04-11",
   "venue": "福島",
   "race": "花見山特別",
   "horses": [
    {
     "no": 3,
     "name": "ムチャスグラシアス",
     "first_corner": 12,
     "pos": 12
    },
    {
     "no": 5,
     "name": "ゴキゲンサン",
     "first_corner": 12,
     "pos": 10
    }
   ]
  },
  {
   "date": "2026-03-14",
   "venue": "阪神",
   "race": "讃岐特別",
   "horses": [
    {
     "no": 14,
     "name": "フードマン",
     "first_corner": 5,
     "pos": 4
    },
    {
     "no": 15,
     "name": "ベビーズブレス",
     "first_corner": 8,
     "pos": 14
    }
   ]
  },
  {
   "date": "2026-02-15",
   "venue": "小倉",
   "race": "大濠特別",
   "horses": [
    {
     "no": 15,
     "name": "ベビーズブレス",
     "first_corner": 2,
     "pos": 16
    },
    {
     "no": 1,
     "name": "ハリウッドメモリー",
     "first_corner": 6,
     "pos": 5
    }
   ]
  },
  {
   "date": "2026-02-10",
   "venue": "京都",
   "race": "2勝クラス",
   "horses": [
    {
     "no": 7,
     "name": "リリーフィールド",
     "first_corner": 3,
     "pos": 10
    },
    {
     "no": 4,
     "name": "エクストラバック",
     "first_corner": 7,
     "pos": 6
    },
    {
     "no": 8,
     "name": "ガットネロ",
     "first_corner": 7,
     "pos": 12
    }
   ]
  },
  {
   "date": "2026-02-01",
   "venue": "小倉",
   "race": "周防灘特別",
   "horses": [
    {
     "no": 9,
     "name": "ミニョンマルーン",
     "first_corner": 3,
     "pos": 9
    },
    {
     "no": 1,
     "name": "ハリウッドメモリー",
     "first_corner": 6,
     "pos": 2
    },
    {
     "no": 14,
     "name": "フードマン",
     "first_corner": 11,
     "pos": 11
    }
   ]
  },
  {
   "date": "2026-01-17",
   "venue": "中山",
   "race": "2勝クラス",
   "horses": [
    {
     "no": 4,
     "name": "エクストラバック",
     "first_corner": 5,
     "pos": 6
    },
    {
     "no": 11,
     "name": "エクセルゴールド",
     "first_corner": 13,
     "pos": 11
    }
   ]
  },
  {
   "date": "2025-12-27",
   "venue": "中山",
   "race": "ベストウィッ",
   "horses": [
    {
     "no": 9,
     "name": "ミニョンマルーン",
     "first_corner": 1,
     "pos": 8
    },
    {
     "no": 5,
     "name": "ゴキゲンサン",
     "first_corner": 7,
     "pos": 11
    },
    {
     "no": 3,
     "name": "ムチャスグラシアス",
     "first_corner": 12,
     "pos": 13
    }
   ]
  },
  {
   "date": "2025-11-29",
   "venue": "京都",
   "race": "2勝クラス",
   "horses": [
    {
     "no": 15,
     "name": "ベビーズブレス",
     "first_corner": 7,
     "pos": 7
    },
    {
     "no": 1,
     "name": "ハリウッドメモリー",
     "first_corner": 11,
     "pos": 10
    }
   ]
  },
  {
   "date": "2025-11-16",
   "venue": "京都",
   "race": "2勝クラス",
   "horses": [
    {
     "no": 4,
     "name": "エクストラバック",
     "first_corner": 3,
     "pos": 11
    },
    {
     "no": 11,
     "name": "エクセルゴールド",
     "first_corner": 13,
     "pos": 14
    }
   ]
  },
  {
   "date": "2025-11-09",
   "venue": "東京",
   "race": "2勝クラス",
   "horses": [
    {
     "no": 10,
     "name": "スミレファースト",
     "first_corner": 6,
     "pos": 4
    },
    {
     "no": 3,
     "name": "ムチャスグラシアス",
     "first_corner": 14,
     "pos": 13
    }
   ]
  },
  {
   "date": "2025-09-06",
   "venue": "札幌",
   "race": "札幌スポニチ",
   "horses": [
    {
     "no": 15,
     "name": "ベビーズブレス",
     "first_corner": 1,
     "pos": 5
    },
    {
     "no": 3,
     "name": "ムチャスグラシアス",
     "first_corner": 3,
     "pos": 7
    },
    {
     "no": 1,
     "name": "ハリウッドメモリー",
     "first_corner": 7,
     "pos": 3
    }
   ]
  }
 ]
}
```

## 追い切り好時計 seed（fetch_oikiri・F用／当該馬不在=Fは全頭web補完）
```json
{"source": "keibabook_bestcyokyo", "n": 3, "note": "週のベスト調教ランキング＝好時計馬の抜粋。全出走馬ではない（不在馬はFがweb補完）", "horses": [{"name": "マイユニバース", "cond": "古馬オープン", "race": "6/14 阪神 11R", "train_date": "6/10", "course": "栗東ＣＷ", "going": "良", "laps": [78.6, 63.1, 49.3, 35.6, 11.4], "load": "馬なり余力", "last_1f": 11.4}, {"name": "エティエンヌ", "cond": "古馬オープン", "race": null, "train_date": "6/11", "course": "栗東ＣＷ", "going": "良", "laps": [78.9, 63.2, 49.8, 36.1, 11.6], "load": "馬なり余力", "last_1f": 11.6}, {"name": "ゴールデンクラウド", "cond": "古馬オープン", "race": "6/13 阪神 11R", "train_date": "6/10", "course": "栗東ＣＷ", "going": "良", "laps": [79.0, 63.7, 49.6, 35.9, 11.7], "load": "一杯", "last_1f": 11.7}], "url": "https://p.keibabook.co.jp/cyuou/bestcyokyo"}
```
