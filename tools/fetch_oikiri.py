#!/usr/bin/env python3
"""追い切り（調教）好時計リストを取得する（競馬ブック bestcyokyo・静的・無料）。

観点F（調教・厩舎仕上げ）の seed。**全出走馬の追い切りは無料・標準ライブラリでは取得不可**
（netkeiba oikiri は JS後読み、JRA公式は重賞のみ＋WAF、JRA-VANは有料Windows）。
そのため本ツールは「今週のベスト調教ランキング＝目立つ好時計馬」を取得する設計:
対象レースの出走馬がこのリストにいれば追い切り好材料、いなければ F が web 調査で補完 or 不明とする。

★市場ゼロ: bestcyokyo はオッズ・人気・他人の予想印を含まない（純粋な調教実測のみ）。

使い方:
  python3 tools/fetch_oikiri.py week [--date MMDD] [--json]
  --date 6/14 等で出走日フィルタ（省略時は今週全部）

出力フィールド（各馬）:
  name / cond(条件) / race(出走レース M/D 場 R) / train_date / course(栗東ＣＷ等) / going /
  laps(各ハロンの累計タイム[]) / last_1f(ラスト1F=lapsの最小値) / load(脚色 馬なり/強め/一杯+余力)

読み筋は obs-f-training.md（同一コース内で比較・ラスト1F重視・馬なりで好時計が最上・調教駆け注意）。
エラー時は {"error","stage"} を stderr に出して非ゼロ終了。仕様: references/scraping.md。
"""
import sys
import re
import json
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
URL = "https://p.keibabook.co.jp/cyuou/bestcyokyo"

TAG = re.compile(r'<[^>]+>')
ROW = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S)
CELL = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.S)
RACE = re.compile(r'(\d{1,2}/\d{1,2})\s*(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\s*(\d{1,2})R')
DATE = re.compile(r'^\d{1,2}/\d{1,2}$')
COURSE = re.compile(r'(栗東|美浦)\s*(坂路|ＣＷ|Ｗ|ポリ|ダ|芝)')
GOING = re.compile(r'^(良|稍|重|不|稍重|不良)$')
TIME = re.compile(r'^\d{2,3}\.\d$')
LOAD = re.compile(r'(馬なり|強め|一杯|直一)(?:余力)?')


def clean(s):
    return re.sub(r'\s+', '', TAG.sub('', s)).strip()


def parse_row(cells):
    """列位置に依存せず、各セルをパターンで分類して1頭分を組む。"""
    h = {"name": None, "cond": None, "race": None, "train_date": None,
         "course": None, "going": None, "laps": [], "load": None}
    laps = []
    for i, c in enumerate(cells):
        if not c:
            continue
        rm = RACE.search(c)
        if rm:
            h["race"] = f"{rm.group(1)} {rm.group(2)} {rm.group(3)}R"
            continue
        if COURSE.search(c):
            h["course"] = c
            continue
        if GOING.match(c):
            h["going"] = c
            continue
        if TIME.match(c):
            laps.append(float(c))
            continue
        lm = LOAD.search(c)
        if lm and h["load"] is None:
            h["load"] = lm.group(0)
            continue
        if DATE.match(c):
            h["train_date"] = c
            continue
        # 条件（古馬オープン等）
        if ("オープン" in c or "勝" in c or "新馬" in c or "未勝利" in c or "Ｇ" in c) and not h["cond"]:
            h["cond"] = c
    # 馬名: 2番目のセルが定番（リンクテキスト）。タイム/コース/日付でない最初の非数値長文
    if len(cells) >= 2 and cells[1] and not TIME.match(cells[1]):
        h["name"] = cells[1]
    h["laps"] = laps
    h["last_1f"] = min(laps) if laps else None   # ラスト1Fは最小の累計＝終い区間
    return h if h["name"] and laps else None


def fetch(date_filter=None):
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept-Language": "ja"})
        raw = urllib.request.urlopen(req, timeout=25).read()
    except Exception as e:
        print(json.dumps({"error": str(e), "stage": "fetch"}), file=sys.stderr)
        sys.exit(1)
    txt = raw.decode("utf-8", "replace")
    # 時計を含むテーブルを採用
    horses = []
    for tb in re.findall(r'<table[^>]*>(.*?)</table>', txt, re.S):
        rows = ROW.findall(tb)
        if not any(re.search(r'\d{2,3}\.\d', r) for r in rows):
            continue
        for r in rows:
            cells = [clean(c) for c in CELL.findall(r)]
            if not any(TIME.match(c) for c in cells):
                continue   # ヘッダ行
            h = parse_row(cells)
            if h:
                horses.append(h)
    if date_filter:
        horses = [h for h in horses if (h["race"] or "").startswith(date_filter)
                  or h["train_date"] == date_filter]
    if not horses:
        print(json.dumps({"error": "no oikiri rows parsed", "stage": "parse"}), file=sys.stderr)
        sys.exit(1)
    return {"source": "keibabook_bestcyokyo", "n": len(horses),
            "note": "週のベスト調教ランキング＝好時計馬の抜粋。全出走馬ではない（不在馬はFがweb補完）",
            "horses": horses, "url": URL}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    date_filter = None
    for i, a in enumerate(sys.argv):
        if a == "--date" and i + 1 < len(sys.argv):
            date_filter = sys.argv[i + 1]
    out = fetch(date_filter)
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"# 競馬ブック ベスト調教  ({out['n']}頭)  ※好時計ランキング（全頭ではない）")
    print(f"{'馬名':<14}{'コース':<8}{'馬場':<3}{'ラスト1F':>7} {'脚色':<10} 出走レース")
    for h in out["horses"]:
        l1 = f"{h['last_1f']:.1f}" if h["last_1f"] else "-"
        print(f"{h['name']:<14}{h.get('course') or '-':<8}{h.get('going') or '-':<3}{l1:>7} "
              f"{h.get('load') or '-':<10} {h.get('race') or ''}")


if __name__ == "__main__":
    main()
