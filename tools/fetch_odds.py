#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_odds.py — 選別レイヤー(/screen-card)専用・単勝オッズ→団子度メトリクス（P1 隔離オッズ）。

★I1-S 隔離の壁（harness-invariants）:
  - これは**選別レイヤー専用**。出力は data/screening/ にのみ置く。
    research-*.json / report.json / predictions.jsonl には**一切流さない**。
  - /analyze-race（予想本体）はオッズを一切見ない。団子度を X(予想) の証拠にしない。
  - 出力はレース単位の団子度まで。馬ごとの買い目・金額・EV は出さない（人間判断）。

設計:
  - 核 = dango_metrics()：単勝オッズ配列 → 団子度メトリクス＋ティア（純ロジック＝確実にテスト可能）。
  - JRA経路 = fetch_racecard.py の POST連鎖(jra_post/jra_race_tokens)を再利用し、出馬表ビューの
    <div class="odds"> から単勝を抜く（fetch_racecard は strip している部分）。**今週開催のみ**。
    odds div の内部マークアップは VERIFY-pending（次の実取得で要確認）＝best-effort。失敗時は paste へ。
  - paste経路 = stdin に「<馬番> <単勝オッズ>」行 or JSON配列を貼る（スクレイパは fast-path、必須依存でない）。

閾値の出典（B研究・2026-06 / data-backed）:
  - 1人気-2人気の単勝オッズ差（最強指標・単調）: 差<0.5=拮抗(1人気複勝58%) / 差>=2.0で堅さ顕在 / >=3.5-5.0で断然(複勝82%)。
  - 1番人気の単勝オッズ: <=1.9=堅(複勝80%前後) / >=3.0-4.0=割れ(複勝50%割れ)。
  - 単勝30倍以下の頭数: >=10頭=団子(本命不在)。
  - 単勝平均オッズ: <20倍=団子（馬連平均12.3k＝標準の約2.3倍）。
  オッズ断層理論は通説止まり（効果の公開検証なし）＝1人気-2人気差で代替できるので不採用。

CLI:
  python3 tools/fetch_odds.py race  <race_id12桁> [--json] [--out PATH]   # JRA出馬表→単勝→団子度（今週のみ）
  python3 tools/fetch_odds.py paste <race_id>     [--json] [--out PATH]   # stdinに単勝を貼る（確実な経路）
  python3 tools/fetch_odds.py --self-check                                # 団子ロジックの内部整合チェック
"""
import sys
import os
import re
import json
import html

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 兄弟 fetch_racecard を import 可能に

# ── 団子度の閾値（B研究・data-backed。チューニングはここ一箇所） ───────────────
FAV_SPLIT = 3.0      # 1番人気が単勝この倍以上＝割れ（本命不在・複勝50%割れ）
FAV_SPLIT_HI = 4.0   # さらに上＝割れが濃い
FAV_SOLID = 1.9      # 1番人気が単勝この倍以下＝収束（抜けた本命・複勝80%前後）
FAV_SOLID_HI = 1.4   # さらに下＝鉄板（複勝86-89%）
GAP_TIGHT = 0.5      # 2人気-1人気の差がこの倍未満＝拮抗（割れ）
GAP_TIGHT_HI = 0.3   # さらに拮抗
GAP_CLEAR = 2.0      # 差がこの倍以上＝1番人気の堅さ顕在（収束）
GAP_CLEAR_HI = 3.5   # 断然本命級
UNDER_BUNCH = 30.0   # 単勝この倍以下を「圏内候補」とみなす
UNDER_BUNCH_N = 10   # 圏内候補がこの頭数以上＝団子（本命不在・割れ）
MEAN_BUNCH = 20.0    # 単勝平均オッズがこの倍未満＝団子


def _classify(metrics):
    """各メトリクスを 割れ(+) / 中(0) / 収束(-) に符号化し、重み付き合計でティアを決める。
    1人気オッズと1-2人気差を主指標(重み2)、頭数と平均を補助(重み1)。透明性のため発火シグナルも返す。"""
    fav = metrics["fav_odds"]
    gap = metrics["fav_second_gap"]
    n30 = metrics["n_under_30"]
    mean = metrics["mean_odds"]
    score = 0
    sig = []  # (符号, ラベル)
    # 1番人気オッズ（主・重み2）
    if fav is not None:
        if fav >= FAV_SPLIT_HI:
            score += 4; sig.append(("割れ", f"1番人気{fav}倍≥{FAV_SPLIT_HI}(本命不在)"))
        elif fav >= FAV_SPLIT:
            score += 2; sig.append(("割れ", f"1番人気{fav}倍≥{FAV_SPLIT}(割れ)"))
        elif fav <= FAV_SOLID_HI:
            score -= 4; sig.append(("収束", f"1番人気{fav}倍≤{FAV_SOLID_HI}(鉄板)"))
        elif fav <= FAV_SOLID:
            score -= 2; sig.append(("収束", f"1番人気{fav}倍≤{FAV_SOLID}(抜けた本命)"))
    # 1人気-2人気の差（主・重み2・最強指標）
    if gap is not None:
        if gap < GAP_TIGHT_HI:
            score += 4; sig.append(("割れ", f"1-2人気差{gap:.1f}<{GAP_TIGHT_HI}(拮抗)"))
        elif gap < GAP_TIGHT:
            score += 2; sig.append(("割れ", f"1-2人気差{gap:.1f}<{GAP_TIGHT}(拮抗)"))
        elif gap >= GAP_CLEAR_HI:
            score -= 4; sig.append(("収束", f"1-2人気差{gap:.1f}≥{GAP_CLEAR_HI}(断然)"))
        elif gap >= GAP_CLEAR:
            score -= 2; sig.append(("収束", f"1-2人気差{gap:.1f}≥{GAP_CLEAR}(堅さ顕在)"))
    # 単勝30倍以下の頭数（補助・重み1）
    if n30 is not None and n30 >= UNDER_BUNCH_N:
        score += 1; sig.append(("割れ", f"単勝{UNDER_BUNCH:.0f}倍以下が{n30}頭≥{UNDER_BUNCH_N}(団子)"))
    # 単勝平均オッズ（補助・重み1）
    if mean is not None and mean < MEAN_BUNCH:
        score += 1; sig.append(("割れ", f"単勝平均{mean:.1f}倍<{MEAN_BUNCH:.0f}(団子)"))
    tier = "割れ" if score >= 2 else "収束" if score <= -2 else "中"
    star = {"割れ": "荒れ★★★", "中": "中★★", "収束": "収束★"}[tier]
    return tier, star, score, sig


def dango_metrics(odds):
    """odds = [{"no":int, "name":str|None, "tansho":float}] → 団子度メトリクス＋ティア。純ロジック。
    取消等で tansho が None/<1.0 の馬は除外して集計する（1.0 は最低オッズの実馬＝除外しない）。"""
    valid = [o for o in odds if isinstance(o.get("tansho"), (int, float)) and o["tansho"] >= 1.0]
    valid.sort(key=lambda o: o["tansho"])
    vals = [o["tansho"] for o in valid]
    n = len(vals)
    fav = vals[0] if n >= 1 else None
    second = vals[1] if n >= 2 else None
    gap = round(second - fav, 2) if (fav is not None and second is not None) else None
    ratio = round(second / fav, 3) if (fav and second) else None
    metrics = {
        "fav_odds": fav,
        "second_odds": second,
        "fav_second_gap": gap,                       # 最強指標
        "fav_second_ratio": ratio,
        "n_under_30": sum(1 for v in vals if v <= 30.0),
        "n_under_10": sum(1 for v in vals if v < 10.0),   # "赤の数"の素（参考）
        "mean_odds": round(sum(vals) / n, 1) if n else None,
        "n_valid": n,
    }
    tier, star, score, sig = _classify(metrics)
    return {
        "metrics": metrics,
        "dango_tier": tier,
        "dango_label": star,
        "dango_score": score,                        # +で割れ / -で収束（重み付き合計）
        "dango_signals": [f"[{s}] {t}" for s, t in sig],
        "fav_no": valid[0]["no"] if valid else None,
        "fav_name": valid[0].get("name") if valid else None,
    }


# ── 入力経路 ────────────────────────────────────────────────────────────────
def parse_paste(text):
    """stdin テキスト → odds 配列。2形式を受ける:
       (a) JSON配列 [{"no":1,"tansho":3.4,"name":"…"}, …]
       (b) 行テキスト「<馬番> <単勝オッズ> [馬名]」（空白/タブ/カンマ区切り）。'1 3.4 ウマ' 等。"""
    text = text.strip()
    if not text:
        raise ValueError("paste: 入力が空（stdin に単勝オッズを与えてください）")
    if text.lstrip().startswith("["):
        arr = json.loads(text)
        return [{"no": int(o["no"]), "name": o.get("name"),
                 "tansho": float(o["tansho"])} for o in arr if o.get("tansho") not in (None, "")]
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = re.split(r"[\s,]+", ln)
        if len(parts) < 2:
            continue
        try:
            no = int(re.sub(r"\D", "", parts[0]))
            tansho = float(parts[1])
        except ValueError:
            continue
        name = " ".join(parts[2:]) if len(parts) > 2 else None
        out.append({"no": no, "name": name, "tansho": tansho})
    if not out:
        raise ValueError("paste: 単勝オッズを1頭も抽出できず（形式『馬番 オッズ [馬名]』 or JSON配列）")
    return out


# 出馬表ビューの per-horse ブロック内オッズ（VERIFY-pending・best-effort）。
# fetch_racecard は <div class="odds">…</div></div> を strip しているので、ここでは capture して使う。
# ★実測(2026-06-26 函館1R/発売前): 出馬表ビューに単勝は**載らない**（class="odds"無し・単勝0件）。
#   = この経路が効くのは**発売中(当日/前日発売中)のみ**。発売前・薄取得は下の guard で例外→ paste へ誘導。
#   発売前でも確実に欲しいなら paste 経路（JRA/各サイトのオッズ画面を人が貼る）を使う。専用オッズページ直叩きは将来課題。
_ODDS_BLOCK = re.compile(r'<div class="odds">(.*?)</div>\s*</div>', re.S)
_FIRST_FLOAT = re.compile(r'(\d{1,4}\.\d)')   # 単勝は塊内の最初の小数（複勝は範囲『1.5-2.0』なので先頭=単勝）


def fetch_jra_odds(race_id):
    """JRA出馬表ビューから 馬番・馬名・単勝オッズ を抜く（今週開催のみ・best-effort）。
    fetch_racecard の POST連鎖を再利用。失敗・薄取得は例外（→呼び出し側が paste へ誘導）。"""
    import fetch_racecard as fr
    date, place, rno = race_id[:8], race_id[8:10], race_id[10:12]
    toks = fr.jra_race_tokens(date, place)
    if rno not in toks:
        raise ValueError(f"JRA: {date} 場{place} に {int(rno)}R が無い")
    h = fr.jra_post(toks[rno])
    odds = []
    for c in fr.PATTERNS["jra_horse"].findall(h):
        nm = fr.PATTERNS["jra_name"].search(c)
        num = fr.PATTERNS["jra_num"].search(c)
        if not (nm and num):
            continue
        ob = _ODDS_BLOCK.search(c)
        tansho = None
        if ob:
            fm = _FIRST_FLOAT.search(ob.group(1))
            if fm:
                tansho = float(fm.group(1))
        odds.append({"no": int(num.group(1)),
                     "name": html.unescape(nm.group(1)).strip(),
                     "tansho": tansho})
    got = [o for o in odds if o["tansho"] is not None]
    if len(got) < max(3, len(odds) // 2):
        raise ValueError(
            f"JRA: 単勝オッズの抽出が薄い（{len(got)}/{len(odds)}頭）。"
            "発売前か odds マークアップ変化の可能性。paste 経路へフォールバックを。")
    return odds


# ── 出力 ────────────────────────────────────────────────────────────────────
def build(race_id, source, odds):
    d = dango_metrics(odds)
    return {
        "race_id": race_id,
        "source": source,        # "jra" | "paste"
        "odds": odds,
        **d,
    }


def render_human(res):
    m = res["metrics"]
    L = [f"race {res['race_id']}  source={res['source']}  ({m['n_valid']}頭)",
         f"  団子度: {res['dango_label']}  (score {res['dango_score']:+d})  ← Y軸の当日側",
         f"  1番人気: {m['fav_odds']}倍" + (f"（{res['fav_no']} {res['fav_name']}）" if res.get('fav_name') else ""),
         f"  1-2人気差: {m['fav_second_gap']}（比 {m['fav_second_ratio']}）  ← 最強指標",
         f"  単勝30倍以下: {m['n_under_30']}頭 / 10倍未満: {m['n_under_10']}頭 / 平均 {m['mean_odds']}倍"]
    for s in res["dango_signals"]:
        L.append(f"   ・{s}")
    L.append("  ※選別専用(I1-S)：予想本体には渡さない／買い目・金額は出さない。")
    return "\n".join(L)


def write_out(res, path):
    if "data/screening/" not in path.replace("\\", "/"):
        sys.stderr.write(f"[warn] I1-S: --out は data/screening/ 配下のみ可（指定: {path}）。書き込み中止。\n")
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    return True


# ── self-check（団子ロジックの内部整合・スクレイプ非依存） ──────────────────────
def self_check():
    cases = [
        # 抜けた本命 → 収束
        ("収束", [{"no": 1, "tansho": 1.3}, {"no": 2, "tansho": 6.0}, {"no": 3, "tansho": 9.0},
                   {"no": 4, "tansho": 15.0}, {"no": 5, "tansho": 40.0}]),
        # 拮抗＋本命不在＋団子 → 割れ
        ("割れ", [{"no": i, "tansho": v} for i, v in enumerate(
            [4.2, 4.6, 5.1, 6.0, 7.2, 8.5, 9.0, 11.0, 14.0, 18.0, 22.0, 28.0], start=1)]),
        # 中庸 → 中
        ("中", [{"no": 1, "tansho": 2.6}, {"no": 2, "tansho": 4.0}, {"no": 3, "tansho": 6.0},
                 {"no": 4, "tansho": 9.0}, {"no": 5, "tansho": 14.0}, {"no": 6, "tansho": 30.0},
                 {"no": 7, "tansho": 60.0}]),
    ]
    ok = True
    for expect, odds in cases:
        got = dango_metrics(odds)["dango_tier"]
        mark = "OK" if got == expect else "FAIL"
        if got != expect:
            ok = False
        print(f"[{mark}] expect={expect} got={got}")
    # 単調性: 1番人気オッズを上げるほど score は割れ方向（非減少）であるべき
    prev = None
    for fav in (1.3, 1.8, 2.6, 3.2, 4.5):
        s = dango_metrics([{"no": 1, "tansho": fav}, {"no": 2, "tansho": 5.0},
                           {"no": 3, "tansho": 9.0}])["dango_score"]
        if prev is not None and s < prev:
            print(f"[FAIL] 単調性: fav={fav} で score {s} < 前 {prev}")
            ok = False
        prev = s
    print("self-check:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--self-check":
        return self_check()

    as_json = "--json" in args
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        out_path = args[i + 1] if i + 1 < len(args) else None
    args = [a for a in args if a not in ("--json",) and a != out_path and a != "--out"]

    cmd = args[0]
    try:
        if cmd == "race":
            race_id = args[1]
            if not re.fullmatch(r"\d{12}", race_id):
                raise ValueError("race_id は12桁数字（YYYYMMDD+場2桁+R2桁）")
            odds = fetch_jra_odds(race_id)
            res = build(race_id, "jra", odds)
        elif cmd == "paste":
            race_id = args[1] if len(args) > 1 else "unknown"
            odds = parse_paste(sys.stdin.read())
            res = build(race_id, "paste", odds)
        else:
            sys.stderr.write(f"unknown command: {cmd}\n")
            return 2
    except Exception as e:
        json.dump({"error": str(e), "stage": cmd}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 1

    if out_path:
        write_out(res, out_path)
    print(json.dumps(res, ensure_ascii=False, indent=2) if as_json else render_human(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
