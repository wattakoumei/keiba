#!/usr/bin/env python3
"""確定結果を取得する（競馬ラボDB・SSR・UTF-8）。

/review-prediction の照合元。レース確定後の 着順・馬番・馬名・タイム・着差・通過順・上り3F・馬体重 を取得し、
results.jsonl 記入と pace_actual（実効ペース層）復元のための素材 pace_aids を決定論で算出する。
★市場ゼロ: 人気・単勝オッズは parse 時に物理的に捨てる（証拠にもログにも入れない）。

使い方:
  python3 tools/fetch_result.py <race_id> [--json]                  # 1レースの確定結果
  python3 tools/fetch_result.py history <race_id> [<race_id> ...] [--json]  # 過去開催のペース署名（例年傾向の素材）
  race_id = YYYYMMDD + 場2桁 + R2桁（例 阪神12R=202606060912。JRAのみ＝NARは対象外）

history: 同一レースの過去開催 race_id を複数渡すと、各開催のペース署名（勝ち馬の通過位置・上位3頭の1角位置・
  上がり最速馬の着順・最終角×着順の順位相関）と、それらの素材集計を返す。これが pace-synthesis の
  pace_factors「例年傾向」行の源（前残り基調か差し決着多めか）。NAR(地方)は keibalab DB 経路の制約で
  取得不確実＝取れない開催は {race_id,error} で個別に欠落させ全体は落とさない（web で補完）。**結論(H/M/S)は出さない＝素材**。

出力フィールド（results.jsonl の finish[] に対応）:
  rank(int) / no(int) / name / passing("3-3-4-2" 正規化) / agari(float|null) / time_sec(float|null) ほか
  status: 完走以外（中止・除外・取消・失格）は rank=null + status に区分を残す（review の C 仕分け用）
  pace_aids: label_reconstructed の判断素材（上位3頭の1角/最終角位置・上がり最速馬の着順・最終角位置と着順の順位相関）
    ※ pace_aids は素材であり結論ではない。H/M/S の認定と reconstructed_from の文章化は /review-prediction が行う。

エラー時は {"error","stage","url"} を stderr に出して非ゼロ終了。
仕様: .claude/skills/analyze-race/references/scraping.md（標準ライブラリのみ）。
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
STATUS = re.compile(r'(中止|除外|取消|失格)')


def clean(s):
    s = TAG.sub('', s)
    s = re.sub(r'\s+', '', s)
    return s.strip()


def parse_agari(s):
    """'34.5' / '(34.5)' → float。欠損は None。"""
    m = re.search(r'(\d{2}\.\d)', s)
    return float(m.group(1)) if m else None


def parse_passing(s):
    """通過順を '3-3-4-2' に正規化し、コーナー位置の int リストも返す。

    競馬ラボは丸数字（②②＝各角1文字）で持つので ①〜⑳/㉑〜㉟ を数値化。
    '3-3' のようなプレーン数字表記にもフォールバック対応。
    """
    pos = []
    for ch in s:
        o = ord(ch)
        if 0x2460 <= o <= 0x2473:        # ①〜⑳
            pos.append(o - 0x2460 + 1)
        elif 0x3251 <= o <= 0x325F:      # ㉑〜㉟
            pos.append(o - 0x3251 + 21)
    if not pos:
        pos = [int(n) for n in re.findall(r'\d+', s)]
    return ("-".join(map(str, pos)), pos) if pos else ("", [])


def parse_time_sec(s):
    """'1:33.5' / '93.5' → 秒 float。欠損は None。"""
    m = re.match(r'(?:(\d+):)?(\d+\.\d)', s)
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + float(m.group(2))


def spearman(xs, ys):
    """簡易 Spearman ρ（タイは平均順位）。n<3 は None。"""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def pace_aids(finishers):
    """pace_actual.label_reconstructed の判断素材（結論は出さない＝review 側の仕事）。"""
    top3 = finishers[:3]
    first_c = [h["passing_pos"][0] for h in top3 if h["passing_pos"]]
    last_c = [h["passing_pos"][-1] for h in top3 if h["passing_pos"]]
    with_agari = [h for h in finishers if h["agari"] is not None]
    fastest = min(with_agari, key=lambda h: h["agari"]) if with_agari else None
    xs = [h["passing_pos"][-1] for h in finishers if h["passing_pos"]]
    ys = [h["rank"] for h in finishers if h["passing_pos"]]
    return {
        "top3_first_corner": first_c,        # 上位3頭の1角位置（前残りか差し決着かの素材）
        "top3_last_corner": last_c,          # 上位3頭の最終角位置
        "agari_fastest": ({"no": fastest["no"], "agari": fastest["agari"], "rank": fastest["rank"]}
                          if fastest else None),  # 上がり最速馬の着順（届いたか）
        "rho_lastcorner_rank": spearman(xs, ys),  # 最終角位置×着順の順位相関（+1に近い=前残り、低い=差し台頭）
    }


class FetchError(Exception):
    """取得・パース失敗（呼び出し側で個別処理＝history が1件失敗で全滅しないため）。"""
    def __init__(self, stage, msg, url):
        super().__init__(msg)
        self.stage, self.msg, self.url = stage, msg, url


def _fetch(race_id):
    """確定結果を取得して構造化（失敗時は FetchError を送出）。"""
    url = f"https://www.keibalab.jp/db/race/{race_id}/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=25).read()
    except Exception as e:
        raise FetchError("fetch", str(e), url)
    txt = data.decode('utf-8', 'replace')
    title_m = re.search(r'<title>([^<]*)</title>', txt)
    title = title_m.group(1) if title_m else ""

    # 結果テーブル本体 <tbody>...</tbody> の最初の塊（結果表）
    tb = re.search(r'<tbody>(.*?)</tbody>', txt, re.S)
    if not tb:
        raise FetchError("parse_tbody", "no tbody", url)
    rows = ROW.findall(tb.group(1))
    horses = []
    for r in rows:
        tds = TD.findall(r)
        if len(tds) < 13:
            continue
        cells = [clean(c) for c in tds]
        # 列順: 0着順 1枠 2馬番 3馬名 4性齢 5斤量 6騎手 7人気 8単勝 9タイム 10着差 11通過順 12上り 13調教師 14馬体重
        if not cells[3]:
            continue
        st = STATUS.search(cells[0])
        status = st.group(1) if st else None
        rank_digits = re.sub(r'\D', '', cells[0])
        rank = int(rank_digits) if (rank_digits and not status) else None
        passing, passing_pos = parse_passing(cells[11])
        # ★市場ゼロ: 人気(7)・単勝(8) は捨てる
        horses.append({
            "rank": rank,
            "status": status,            # 完走なら None。中止/除外/取消/失格は review で C（偶然）候補
            "waku": cells[1],
            "no": int(re.sub(r'\D', '', cells[2]) or 0),
            "name": cells[3],
            "sex_age": cells[4],
            "weight": cells[5],
            "jockey": cells[6],
            "time": cells[9],
            "time_sec": parse_time_sec(cells[9]),
            "margin": cells[10],
            "passing": passing,
            "passing_pos": passing_pos,
            "agari": parse_agari(cells[12]),
            "body_weight": cells[14] if len(cells) > 14 else "",
        })
    finishers = sorted([h for h in horses if h["rank"]], key=lambda h: h["rank"])
    non_finishers = [h for h in horses if not h["rank"]]
    if not finishers:
        raise FetchError("parse_no_horses", "no horses found", url)
    return {"race_id": race_id, "source": "keibalab", "title": title,
            "n": len(finishers), "horses": finishers, "non_finishers": non_finishers,
            "pace_aids": pace_aids(finishers), "url": url}


def fetch(race_id):
    """単一レースCLI用ラッパ（失敗時は stderr 出力＋非ゼロ終了で従来挙動を保つ）。"""
    try:
        return _fetch(race_id)
    except FetchError as e:
        print(json.dumps({"error": e.msg, "stage": e.stage, "url": e.url}), file=sys.stderr)
        sys.exit(1)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def history(race_ids):
    """同一レースの過去開催から「ペース署名」を集めて素材化する（結論=H/M/S は出さない）。

    各開催: 勝ち馬の通過位置・上位3頭の1角位置・上がり最速馬の着順・ρ(最終角,着順)。
    集計: 勝ち馬の平均1角位置・前々(1角≤3)で勝った開催数・上がり最速が勝った(差し決着)開催数・平均ρ。
    → pace-synthesis が「前残り基調／差し決着多め」を定性で著作する素材（pace_factors の例年傾向行）。
    """
    editions = []
    for rid in race_ids:
        try:
            r = _fetch(rid)
        except FetchError as e:
            editions.append({"race_id": rid, "error": e.stage})
            continue
        fin = r["horses"]
        w = fin[0] if fin else None
        a = r["pace_aids"]
        editions.append({
            "race_id": rid,
            "year": rid[:4],
            "n": r["n"],
            "winner_no": w["no"] if w else None,
            "winner_passing": w["passing"] if w else "",
            "winner_first_corner": (w["passing_pos"][0] if w and w["passing_pos"] else None),
            "winner_last_corner": (w["passing_pos"][-1] if w and w["passing_pos"] else None),
            "top3_first_corner": a["top3_first_corner"],
            "agari_fastest_rank": (a["agari_fastest"]["rank"] if a["agari_fastest"] else None),
            "rho_lastcorner_rank": a["rho_lastcorner_rank"],
        })
    ok = [e for e in editions if "error" not in e]
    wfc = [e["winner_first_corner"] for e in ok]
    agg = {
        "editions_fetched": len(ok),
        "editions_requested": len(race_ids),
        "avg_winner_first_corner": _mean(wfc),                                    # 低い=前/好位で勝つ開催が多い
        "front_winner_count": sum(1 for x in wfc if x is not None and x <= 3),     # 1角3番手以内で勝った開催数（前残り基調）
        "closer_decided_count": sum(1 for e in ok if e["agari_fastest_rank"] == 1),  # 上がり最速が勝った=差し決着の開催数
        "avg_rho_lastcorner_rank": _mean([e["rho_lastcorner_rank"] for e in ok]),  # +寄り=前残り基調・低い=差し台頭
    }
    return {"record": "pace_history", "editions": editions, "aggregate": agg}


def cmd_history(args, as_json):
    ids = [a for a in args if a.isdigit() and len(a) == 12]
    bad = [a for a in args if a not in ids]
    if bad:
        print(json.dumps({"error": f"12桁数字でない race_id: {bad}", "stage": "validate"}), file=sys.stderr)
        sys.exit(2)
    if not ids:
        print("usage: fetch_result.py history <race_id12桁> [<race_id> ...] [--json]", file=sys.stderr)
        sys.exit(2)
    out = history(ids)
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    ag = out["aggregate"]
    print(f"# ペース署名（過去 {ag['editions_fetched']}/{ag['editions_requested']} 開催）")
    print(f"{'race_id':<13} {'頭':>2} {'勝1角':>5} {'勝最終角':>7} {'上速着':>6} {'ρ':>6}  通過")
    for e in out["editions"]:
        if "error" in e:
            print(f"{e['race_id']:<13} -- 取得不可({e['error']})")
            continue
        rho = f"{e['rho_lastcorner_rank']}" if e["rho_lastcorner_rank"] is not None else "-"
        print(f"{e['race_id']:<13} {e['n']:>2} {str(e['winner_first_corner']):>5} "
              f"{str(e['winner_last_corner']):>7} {str(e['agari_fastest_rank']):>6} {rho:>6}  {e['winner_passing']}")
    print(f"-- 素材集計: 勝ち馬平均1角={ag['avg_winner_first_corner']} 前々勝ち={ag['front_winner_count']}"
          f" 差し決着={ag['closer_decided_count']} 平均ρ={ag['avg_rho_lastcorner_rank']}"
          f"（結論=H/M/S は pace-synthesis 側）")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print("usage: fetch_result.py <race_id> [--json] | history <race_id> [...] [--json]", file=sys.stderr)
        sys.exit(2)
    if args[0] == "history":
        cmd_history(args[1:], as_json)
        return
    if not (len(args[0]) == 12 and args[0].isdigit()):
        print(json.dumps({"error": "race_id は12桁数字（YYYYMMDD+場2桁+R2桁）", "stage": "validate"}), file=sys.stderr)
        sys.exit(2)
    out = fetch(args[0])
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"# {out['title']}  ({out['n']}頭)  src={out['source']}")
        print(f"{'着':>2} {'馬番':>3} {'馬名':<12} {'タイム':>7} {'着差':>5} {'通過':>10} {'上り':>5} {'馬体重':>9}")
        for h in out["horses"]:
            agari = f"{h['agari']:.1f}" if h["agari"] is not None else "-"
            print(f"{h['rank']:>2} {h['no']:>3} {h['name']:<12} {h['time']:>7} {h['margin']:>5} "
                  f"{h['passing']:>10} {agari:>5} {h['body_weight']:>9}")
        for h in out["non_finishers"]:
            print(f"{h['status']:>2} {h['no']:>3} {h['name']:<12}")
        a = out["pace_aids"]
        print(f"-- pace_aids: top3 1角={a['top3_first_corner']} 最終角={a['top3_last_corner']} "
              f"上がり最速={a['agari_fastest']} ρ(最終角,着順)={a['rho_lastcorner_rank']}")


if __name__ == "__main__":
    main()
