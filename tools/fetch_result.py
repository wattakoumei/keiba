#!/usr/bin/env python3
"""確定結果を取得する（競馬ラボDB・SSR・UTF-8）。

/review-prediction の照合元。レース確定後の 着順・馬番・馬名・タイム・着差・通過順・上り3F・馬体重 を取得。
★市場ゼロ: 人気・単勝オッズは parse 時に物理的に捨てる（証拠にもログにも入れない）。

使い方:
  python3 tools/fetch_result.py <race_id> [--json]
  race_id = YYYYMMDD + 場2桁 + R2桁（例 阪神12R=202606060912）

エラー時は {"error","stage","url"} を stderr に出して非ゼロ終了。
仕様: .claude/skills/analyze-race/references/scraping.md（取得元は fetch_racecard.py と同方針＝標準ライブラリのみ）。
"""
import sys
import re
import json
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

TD = re.compile(r'<td[^>]*>(.*?)</td>', re.S)
TAG = re.compile(r'<[^>]+>')
ROW = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S)


def clean(s):
    s = TAG.sub('', s)
    s = re.sub(r'\s+', '', s)
    return s.strip()


def fetch(race_id):
    url = f"https://www.keibalab.jp/db/race/{race_id}/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=25).read()
    except Exception as e:
        print(json.dumps({"error": str(e), "stage": "fetch", "url": url}), file=sys.stderr)
        sys.exit(1)
    txt = data.decode('utf-8', 'replace')
    title_m = re.search(r'<title>([^<]*)</title>', txt)
    title = title_m.group(1) if title_m else ""

    # 結果テーブル本体 <tbody>...</tbody> の最初の塊（結果表）
    tb = re.search(r'<tbody>(.*?)</tbody>', txt, re.S)
    if not tb:
        print(json.dumps({"error": "no tbody", "stage": "parse", "url": url}), file=sys.stderr)
        sys.exit(1)
    rows = ROW.findall(tb.group(1))
    horses = []
    for r in rows:
        tds = TD.findall(r)
        if len(tds) < 13:
            continue
        cells = [clean(c) for c in tds]
        # 列順: 0着順 1枠 2馬番 3馬名 4性齢 5斤量 6騎手 7人気 8単勝 9タイム 10着差 11通過順 12上り 13調教師 14馬体重
        try:
            rank = int(re.sub(r'\D', '', cells[0]) or 0)
        except ValueError:
            rank = None
        if not cells[3]:
            continue
        # ★市場ゼロ: 人気(7)・単勝(8) は捨てる
        horses.append({
            "rank": rank,
            "waku": cells[1],
            "no": int(re.sub(r'\D', '', cells[2]) or 0),
            "name": cells[3],
            "sex_age": cells[4],
            "weight": cells[5],
            "jockey": cells[6],
            "time": cells[9],
            "margin": cells[10],
            "passing": cells[11],
            "agari": cells[12],
            "body_weight": cells[14] if len(cells) > 14 else "",
        })
    horses = [h for h in horses if h["rank"]]
    horses.sort(key=lambda h: h["rank"])
    return {"race_id": race_id, "source": "keibalab", "title": title,
            "n": len(horses), "horses": horses, "url": url}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print("usage: fetch_result.py <race_id> [--json]", file=sys.stderr)
        sys.exit(2)
    out = fetch(args[0])
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"# {out['title']}  ({out['n']}頭)  src={out['source']}")
        print(f"{'着':>2} {'馬番':>3} {'馬名':<12} {'タイム':>7} {'着差':>5} {'通過':>8} {'上り':>5} {'馬体重':>9}")
        for h in out["horses"]:
            print(f"{h['rank']:>2} {h['no']:>3} {h['name']:<12} {h['time']:>7} {h['margin']:>5} "
                  f"{h['passing']:>8} {h['agari']:>5} {h['body_weight']:>9}")


if __name__ == "__main__":
    main()
