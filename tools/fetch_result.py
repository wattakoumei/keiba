#!/usr/bin/env python3
"""確定結果＋払戻を取得する（競馬ラボDB・SSR・UTF-8）。

/review-prediction の照合元。レース確定後の 着順・馬番・馬名・タイム・着差・通過順・上り3F・馬体重 を取得し、
results.jsonl 記入と pace_actual（実効ペース層）復元のための素材 pace_aids を決定論で算出する。
★市場ゼロ（finish 系出力）: 人気・単勝オッズは parse 時に物理的に捨てる（証拠にもログにも入れない）。
★払戻（I1-R）: `payout`/`paste-payout` サブコマンドのみが確定払戻を `record:"payout"` 行として出す。
  払戻は市場予想値でなく公示事実＝結果層に記録可（用途は box_sim の箱ROI検証と EV 事後検証に限る）。
  組番×実着順の相互検証（馬連組=実1-2着集合 等）を内蔵＝転記ミスを決定論で弾く。

使い方:
  python3 tools/fetch_result.py <race_id> [--json]                  # 1レースの確定結果
  python3 tools/fetch_result.py history <race_id> [<race_id> ...] [--json]  # 過去開催のペース署名（例年傾向の素材）
  python3 tools/fetch_result.py payout <race_id12|dir-race-id> [--record <dir-race-id>] [--append] [--json]
      # 払戻を取得し record:"payout" 1行JSONを出力（--append で results.jsonl へ重複チェック付き追記）
  cat 払戻.txt | python3 tools/fetch_result.py paste-payout <dir-race-id> [--append]
      # NAR・取得不能時: 公式払戻表のテキスト貼り付け（「馬連 8-10 1,520円」行 or JSON）
  python3 tools/fetch_result.py --self-check                        # fixture でパース検査（ネット不要）
  race_id = YYYYMMDD + 場2桁 + R2桁（例 阪神12R=202606060912。JRAのみ＝NARは paste-payout）

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
import os
import json
import datetime

from _polite import polite_get, cache_evict, RefusedByRobots

# 確定結果ページは不変＝キャッシュ再取得を避ける（history の複数開催ループでの負荷対策）
CACHE_TTL = 7 * 86400

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_PATH = os.path.join(ROOT, "data", "results.jsonl")

# 券種名 → payouts キー（record:"payout" スキーマの正本）
BET_TYPES = {
    "単勝": "tansho", "複勝": "fukusho", "枠連": "wakuren", "枠単": "wakutan",
    "馬連": "umaren", "ワイド": "wide", "馬単": "umatan",
    "3連複": "sanrenpuku", "三連複": "sanrenpuku",
    "3連単": "sanrentan", "三連単": "sanrentan",
}
ORDERED_TYPES = {"umatan", "sanrentan", "wakutan"}   # 着順順＝comb をソートしない
# ディレクトリ race-id（romaji）→ JRA 場コード（NAR は無し＝paste-payout 経路）
PLACE_CODE = {"sapporo": "01", "hakodate": "02", "fukushima": "03", "niigata": "04",
              "tokyo": "05", "nakayama": "06", "chukyo": "07", "kyoto": "08",
              "hanshin": "09", "kokura": "10"}

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
    """確定結果を取得して構造化（失敗時は FetchError を送出）。

    取得は _polite 経由（robots 尊重・1.5s/req レート制限・確定ページはキャッシュ）。
    パース失敗＝未確定/変則ページの可能性があるのでキャッシュを無効化してから raise。
    """
    url = f"https://www.keibalab.jp/db/race/{race_id}/raceresult.html"   # 基底URLは出馬表ビュー＝結果・払戻はこちら
    try:
        data = polite_get(url, cache_ttl=CACHE_TTL)
    except RefusedByRobots as e:
        raise FetchError("robots", str(e), url)
    except Exception as e:
        raise FetchError("fetch", str(e), url)
    txt = data.decode('utf-8', 'replace')
    title_m = re.search(r'<title>([^<]*)</title>', txt)
    title = title_m.group(1) if title_m else ""

    # 結果テーブル本体 <tbody>...</tbody> の最初の塊（結果表）
    tb = re.search(r'<tbody>(.*?)</tbody>', txt, re.S)
    if not tb:
        cache_evict(url)
        raise FetchError("parse_tbody", "no tbody", url)
    rows = ROW.findall(tb.group(1))
    horses = []
    for r in rows:
        tds = TD.findall(r)
        if len(tds) < 14:
            continue
        cells = [clean(c) for c in tds]
        # 列順（o=オフセット）: o+0着順 1枠 2馬番 3馬名 4性齢 5斤量 6騎手 7人気 8単勝 9タイム 10着差 11通過順 12上り 13調教師 14馬体重
        # raceresult.html は先頭にアイコン列が入る（o=1）。旧レイアウトは o=0。着順らしさで自動判定。
        o = 0 if re.search(r'\d|中止|除外|取消|失格', cells[0]) else 1
        if len(cells) < o + 14 or not cells[o + 3]:
            continue
        st = STATUS.search(cells[o])
        status = st.group(1) if st else None
        rank_digits = re.sub(r'\D', '', cells[o])
        rank = int(rank_digits) if (rank_digits and not status) else None
        passing, passing_pos = parse_passing(cells[o + 11])
        # ★市場ゼロ: 人気(o+7)・単勝(o+8) は捨てる
        horses.append({
            "rank": rank,
            "status": status,            # 完走なら None。中止/除外/取消/失格は review で C（偶然）候補
            "waku": cells[o + 1],
            "no": int(re.sub(r'\D', '', cells[o + 2]) or 0),
            "name": cells[o + 3],
            "sex_age": cells[o + 4],
            "weight": cells[o + 5],
            "jockey": cells[o + 6],
            "time": cells[o + 9],
            "time_sec": parse_time_sec(cells[o + 9]),
            "margin": cells[o + 10],
            "passing": passing,
            "passing_pos": passing_pos,
            "agari": parse_agari(cells[o + 12]),
            "body_weight": cells[o + 14] if len(cells) > o + 14 else "",
        })
    finishers = sorted([h for h in horses if h["rank"]], key=lambda h: h["rank"])
    non_finishers = [h for h in horses if not h["rank"]]
    if not finishers:
        cache_evict(url)
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


# ---------------- 払戻（record:"payout"・I1-R） ----------------

def _cell_lines(raw):
    """<td> 生HTML → <br> 区切りの行リスト（同着・複勝複数的中は複数行になる）。"""
    return [clean(p) for p in re.split(r'<br\s*/?>', raw) if clean(p)]


def parse_payouts(txt):
    """競馬ラボ raceresult の払い戻しブロック（class="haraimodoshi"）→ payouts dict。

    行構造: <td class="bg…">券種</td><td>組番(複数は<br>)</td><td>払戻円(<br>)</td> が1行に2券種。
    返り値: {"umaren":[{"comb":[8,10],"yen":1520}], ...}（yen=100円あたり・順不同券種は comb 昇順）。
    ブロックが無ければ None（未確定・変則ページ）。
    """
    m = re.search(r'class="haraimodoshi"(.*?)</table>', txt, re.S)
    if not m:
        return None
    tds = TD.findall(m.group(1))
    payouts = {}
    i = 0
    while i < len(tds):
        name = clean(tds[i])
        typ = BET_TYPES.get(name)
        if not typ:
            i += 1
            continue
        combs = _cell_lines(tds[i + 1]) if i + 1 < len(tds) else []
        yens = _cell_lines(tds[i + 2]) if i + 2 < len(tds) else []
        for c_line, y_line in zip(combs, yens):
            nums = [int(x) for x in re.findall(r'\d+', c_line)]
            ydigits = re.sub(r'[^\d]', '', y_line)
            if not nums or not ydigits:
                continue   # 発売なし・特払い表記はスキップ
            comb = nums if typ in ORDERED_TYPES else sorted(nums)
            payouts.setdefault(typ, []).append({"comb": comb, "yen": int(ydigits)})
        i += 3
    return payouts or None


def verify_payouts(finishers, payouts):
    """組番×実着順の相互検証（転記ミス・ページ取り違えを決定論で弾く）。

    finishers: [{"no":int,"rank":int}, ...]。同着は rank<=k で自然に拾う。
    """
    errs = []
    def tops(k):
        return {h["no"] for h in finishers if h.get("rank") and h["rank"] <= k}
    checks = [("tansho", 1, "単勝組番が実1着と不一致"),
              ("umaren", 2, "馬連組番が実1-2着集合と不一致"),
              ("sanrenpuku", 3, "三連複組番が実1-3着集合と不一致")]
    for typ, k, msg in checks:
        entries = payouts.get(typ)
        if not entries:
            continue
        tk = tops(k)
        if not any(set(e["comb"]) <= tk for e in entries):
            errs.append(f"{msg}: {entries} vs 実{sorted(tk)}")
    return errs


def dir_to_id12(dir_id):
    """ディレクトリ race-id（YYYYMMDD-romaji-RR）→ JRA 12桁 race_id。NAR は None。"""
    m = re.match(r'^(\d{8})-([a-z]+)-(\d{2})$', dir_id)
    if not m:
        return None
    code = PLACE_CODE.get(m.group(2))
    return f"{m.group(1)}{code}{m.group(3)}" if code else None


def build_payout_record(record_race_id, race_id12, payouts, source):
    date = None
    for src in (race_id12, record_race_id):
        mm = re.match(r'^(\d{4})(\d{2})(\d{2})', src or "")
        if mm:
            date = f"{mm.group(1)}-{mm.group(2)}-{mm.group(3)}"
            break
    return {"record": "payout", "race_id": record_race_id, "race_id12": race_id12,
            "date": date, "source": source,
            "collected_at": datetime.date.today().isoformat(), "payouts": payouts}


def append_payout_record(rec, results_path=None):
    """results.jsonl へ追記（同一 race_id の payout 行が既にあればスキップ）。"""
    path = results_path or RESULTS_PATH
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("record") == "payout" and d.get("race_id") == rec["race_id"]:
                    return False
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True


def load_finish(race_id, results_path=None):
    """results.jsonl の finish 行 → verify 用 [{"no","rank"}]（無ければ None）。"""
    path = results_path or RESULTS_PATH
    if not os.path.exists(path):
        return None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("race_id") == race_id and "finish" in d:
            return [{"no": h.get("no"), "rank": h.get("pos")} for h in d["finish"]]
    return None


def parse_paste_payout(text):
    """公式払戻表の貼り付けテキスト → payouts dict（JSON 形式も許容）。

    行形式: 「馬連 8-10 1,520円」「三連複 2 8 10 4230」等。券種名で始まる行だけ拾う。
    """
    text = text.strip()
    if text.startswith("{"):
        d = json.loads(text)
        out = {}
        for name, entries in d.items():
            typ = BET_TYPES.get(name, name if name in set(BET_TYPES.values()) else None)
            if not typ:
                continue
            for e in entries:
                comb = list(e["comb"]) if typ in ORDERED_TYPES else sorted(e["comb"])
                out.setdefault(typ, []).append({"comb": comb, "yen": int(e["yen"])})
        return out or None
    z2h = str.maketrans("０１２３４５６７８９", "0123456789")
    payouts = {}
    for line in text.splitlines():
        line = line.strip().translate(z2h)
        if not line:
            continue
        typ, rest = None, ""
        for name in sorted(BET_TYPES, key=len, reverse=True):
            if line.startswith(name):
                typ, rest = BET_TYPES[name], line[len(name):]
                break
        if not typ:
            continue
        groups = re.findall(r'[\d,]+', rest)
        if len(groups) < 2:
            continue
        yen = int(groups[-1].replace(",", ""))
        comb = [int(g.replace(",", "")) for g in groups[:-1]]
        if typ not in ORDERED_TYPES:
            comb = sorted(comb)
        payouts.setdefault(typ, []).append({"comb": comb, "yen": yen})
    return payouts or None


def cmd_payout(args, as_json):
    """payout <race_id12|dir-race-id> [--record <dir-race-id>] [--append] [--json]"""
    if not args:
        print("usage: fetch_result.py payout <race_id12|dir-race-id> [--record <dir-id>] [--append]",
              file=sys.stderr)
        sys.exit(2)
    target = args[0]
    record_id = None
    for i, a in enumerate(sys.argv):
        if a == "--record" and i + 1 < len(sys.argv):
            record_id = sys.argv[i + 1]
    if len(target) == 12 and target.isdigit():
        id12 = target
    else:
        id12 = dir_to_id12(target)
        record_id = record_id or target
        if not id12:
            print(json.dumps({"error": f"JRA 12桁に変換不可（NARは paste-payout）: {target}",
                              "stage": "validate"}, ensure_ascii=False), file=sys.stderr)
            sys.exit(2)
    record_id = record_id or id12
    try:
        r = _fetch(id12)
        txt = polite_get(r["url"], cache_ttl=CACHE_TTL).decode("utf-8", "replace")
    except FetchError as e:
        print(json.dumps({"error": e.msg, "stage": e.stage, "url": e.url}), file=sys.stderr)
        sys.exit(1)
    payouts = parse_payouts(txt)
    if not payouts:
        cache_evict(r["url"])
        print(json.dumps({"error": "払戻ブロックが見つからない（未確定?）", "stage": "parse_payout",
                          "url": r["url"]}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    errs = verify_payouts(r["horses"], payouts)
    if errs:
        print(json.dumps({"error": "相互検証NG: " + "; ".join(errs), "stage": "verify"},
                         ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    rec = build_payout_record(record_id, id12, payouts, "keibalab")
    if "--append" in sys.argv:
        added = append_payout_record(rec)
        print(("追記: " if added else "既存スキップ: ") + record_id)
        return
    print(json.dumps(rec, ensure_ascii=False, indent=2 if as_json else None))


def cmd_paste_payout(args):
    """paste-payout <dir-race-id> [--append]  ← stdin に払戻表テキスト or JSON"""
    if not args:
        print("usage: cat 払戻.txt | fetch_result.py paste-payout <dir-race-id> [--append]",
              file=sys.stderr)
        sys.exit(2)
    record_id = args[0]
    payouts = parse_paste_payout(sys.stdin.read())
    if not payouts:
        print(json.dumps({"error": "払戻行をパースできない", "stage": "paste"},
                         ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    fin = load_finish(record_id)
    if fin:
        errs = verify_payouts(fin, payouts)
        if errs:
            print(json.dumps({"error": "相互検証NG: " + "; ".join(errs), "stage": "verify"},
                             ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    else:
        print(f"注意: {record_id} の finish 行が results.jsonl に無い＝相互検証スキップ", file=sys.stderr)
    rec = build_payout_record(record_id, dir_to_id12(record_id), payouts, "paste")
    if "--append" in sys.argv:
        added = append_payout_record(rec)
        print(("追記: " if added else "既存スキップ: ") + record_id)
        return
    print(json.dumps(rec, ensure_ascii=False))


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


# 実HTML断片（2025日本ダービー raceresult.html の払い戻しブロック・ドリフト検知 fixture）
PAYOUT_FIXTURE = '''<div class="haraimodoshi"> <h2>払い戻し</h2> <table class="DbTable stripe">
<tr> <td class="bgtan">単勝</td> <td class="tC">13</td> <td class="tR">210円</td>
<td class="bgutan">馬単</td> <td class="tC">13-17</td> <td class="tR">870円</td> </tr>
<tr> <td class="bgfuk">複勝</td> <td class="tC">13<br />17<br />2</td> <td class="tR">110円<br />190円<br />300円</td>
<td class="bgwide">ワイド</td> <td class="tC">13-17<br />2-13<br />2-17</td> <td class="tR">280円<br />620円<br />1,310円</td> </tr>
<tr> <td class="bgwak">枠連</td> <td class="tC">7-8</td> <td class="tR">420円</td>
<td class="bgtrio">3連複</td> <td class="tC">2-13-17</td> <td class="tR">2,990円</td> </tr>
<tr> <td class="bguren">馬連</td> <td class="tC">13-17</td> <td class="tR">560円</td>
<td class="bgtrif">3連単</td> <td class="tC">13-17-2</td> <td class="tR">8,460円</td> </tr> </table> </div>'''


def self_check():
    """ネット不要のパース検査（fixture＝実HTML断片・貼り付け・相互検証）。"""
    errs = []
    p = parse_payouts(PAYOUT_FIXTURE)
    expect = {
        "tansho": [{"comb": [13], "yen": 210}],
        "umatan": [{"comb": [13, 17], "yen": 870}],
        "fukusho": [{"comb": [13], "yen": 110}, {"comb": [17], "yen": 190}, {"comb": [2], "yen": 300}],
        "wide": [{"comb": [13, 17], "yen": 280}, {"comb": [2, 13], "yen": 620}, {"comb": [2, 17], "yen": 1310}],
        "wakuren": [{"comb": [7, 8], "yen": 420}],
        "sanrenpuku": [{"comb": [2, 13, 17], "yen": 2990}],
        "umaren": [{"comb": [13, 17], "yen": 560}],
        "sanrentan": [{"comb": [13, 17, 2], "yen": 8460}],
    }
    if p != expect:
        errs.append(f"parse_payouts fixture 不一致: {p}")
    fin = [{"no": 13, "rank": 1}, {"no": 17, "rank": 2}, {"no": 2, "rank": 3}, {"no": 18, "rank": 4}]
    if verify_payouts(fin, p):
        errs.append("verify_payouts: 正しい組番なのに NG")
    bad_fin = [{"no": 13, "rank": 1}, {"no": 5, "rank": 2}, {"no": 2, "rank": 3}]
    if not verify_payouts(bad_fin, p):
        errs.append("verify_payouts: 誤った着順なのに OK")
    pp = parse_paste_payout("馬連 8-10 1,520円\n三連複 2 8 10 4230\nワイド ８-１０ 620円")
    if pp != {"umaren": [{"comb": [8, 10], "yen": 1520}],
              "sanrenpuku": [{"comb": [2, 8, 10], "yen": 4230}],
              "wide": [{"comb": [8, 10], "yen": 620}]}:
        errs.append(f"parse_paste_payout 不一致: {pp}")
    pj = parse_paste_payout(json.dumps({"馬連": [{"comb": [10, 8], "yen": 1520}]}))
    if pj != {"umaren": [{"comb": [8, 10], "yen": 1520}]}:
        errs.append(f"parse_paste_payout(JSON) 不一致: {pj}")
    if dir_to_id12("20260601-tokyo-11") != "202606010511" or dir_to_id12("20260531-mizusawa-10") is not None:
        errs.append("dir_to_id12 不一致")
    return errs


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if "--self-check" in sys.argv:
        errs = self_check()
        if errs:
            print("SELF-CHECK FAIL: " + "; ".join(errs), file=sys.stderr)
            sys.exit(1)
        print("self-check OK (payout fixture / paste / verify / dir_to_id12)")
        return
    if not args:
        print("usage: fetch_result.py <race_id> [--json] | history … | payout … | paste-payout …", file=sys.stderr)
        sys.exit(2)
    if args[0] == "history":
        cmd_history(args[1:], as_json)
        return
    if args[0] == "payout":
        cmd_payout([a for a in args[1:] if a not in ()], as_json)
        return
    if args[0] == "paste-payout":
        cmd_paste_payout(args[1:])
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
