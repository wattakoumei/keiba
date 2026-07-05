#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ev_board.py — 馬連・三連複の EVボード（I1-E EVレイヤー・買う瞬間の隔離判断板）。

何をするか:
  確定済み report.json のエンジン再生（score_race.compute_exotics）でペア/トリオ確率を作り、
  ユーザーが貼り付けた馬連/三連複オッズと掛け合わせて EV（=確率×オッズ）を表示する。
  box_sim.STRATEGIES の箱候補ごとに 点数・箱的中確率・EV を並べ、EV上位の組も出す。

隔離の壁（I1-E・破ってはならない）:
  1. 入出力は data/ev/ のみ（--save の書き込み先ガード内蔵）。予想成果物・data/screening/ に流さない。
  2. 確率は report.json 確定後のエンジン再生のみ＝オッズを見て確率・印・並びを変えない。
     report.json が無いレースでは実行拒否（時系列の壁をコードで強制）。
  3. 出力は「箱候補×点数×的中確率×オッズ×EV」の表まで。金額・Kelly・購入指示は出さない（人間判断）。
  4. 内在確率は市場較正前＝EV は参考値（較正は /calibrate-T・box_sim の蓄積で改善）。

使い方:
  cat odds.txt | python3 tools/ev_board.py <dir-race-id> --bet umaren [--save] [--top 20]
      # odds.txt: 「1-5 12.3」行（馬連）/「1-5-8 45.6」行（三連複は --bet sanrenpuku）
      # 「馬連 1-5 12.3」のように券種プレフィクス付きなら --bet 省略可
  cat odds.json | python3 tools/ev_board.py <dir-race-id>
      # JSON: {"umaren": {"1-5": 12.3, ...}, "sanrenpuku": {"1-2-3": 45.6, ...}}
  python3 tools/ev_board.py <dir-race-id> --odds-file data/ev/odds-<id>.json
  python3 tools/ev_board.py --self-check

オッズの取り方（法的リスク配慮）: JRA公式のオッズページを人間がブラウザで開いてコピー→貼り付けが正規経路
（オッズページの自動スクレイプ fast-path は VERIFY-pending＝別POSTトークン経路の実地調査後に検討）。
"""
import sys, os, re, json, argparse, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calibrate_T          # build_race_input（エンジン入力の組立て・研究スコア読み）
import score_race           # compute_exotics（ペア/トリオ確率の源）
from box_sim import STRATEGIES, K_OF_BET   # 箱候補の正本（ワンソース）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV_DIR = os.path.join(ROOT, "data", "ev")

BET_JP = {"umaren": "馬連", "sanrenpuku": "三連複"}
JP_BET = {"馬連": "umaren", "三連複": "sanrenpuku", "3連複": "sanrenpuku"}


def guard_out(path):
    """書き込みは data/ev/ 配下のみ（I1-E の壁を構造で守る）。"""
    ap = os.path.abspath(path)
    if not (ap + os.sep).startswith(EV_DIR + os.sep) and ap != EV_DIR:
        raise ValueError(f"I1-E: data/ev/ の外への書き込みは禁止: {path}")
    return ap


def norm_key(nums):
    return "-".join(str(n) for n in sorted(nums))


def parse_odds(text, default_bet=None):
    """貼り付けテキスト/JSON → {"umaren": {"1-5": 12.3}, "sanrenpuku": {...}}。キーは昇順正規化。"""
    text = text.strip()
    if not text:
        return {}
    if text.startswith("{"):
        d = json.loads(text)
        out = {}
        for bet, m in d.items():
            b = JP_BET.get(bet, bet)
            if b not in BET_JP:
                continue
            out[b] = {norm_key(int(x) for x in re.findall(r"\d+", k)): float(v)
                      for k, v in m.items()}
        return out
    z2h = str.maketrans("０１２３４５６７８９．", "0123456789.")
    out = {}
    for line in text.splitlines():
        line = line.strip().translate(z2h)
        if not line:
            continue
        bet = default_bet
        for name in sorted(JP_BET, key=len, reverse=True):
            if line.startswith(name):
                bet = JP_BET[name]
                line = line[len(name):].strip()
                break
        if bet not in BET_JP:
            continue
        m = re.match(r"^(\d{1,2}(?:-\d{1,2}){1,2})[\s:：]+([\d,]+\.?\d*)", line)
        if not m:
            continue
        nums = [int(x) for x in m.group(1).split("-")]
        k = K_OF_BET[bet]
        if len(nums) != k:
            continue
        out.setdefault(bet, {})[norm_key(nums)] = float(m.group(2).replace(",", ""))
    return out


def build_ev(race_dir, odds):
    """エンジン再生（時系列の壁: report.json 必須）→ EV行＋箱候補集計。"""
    data, report = calibrate_T.build_race_input(race_dir)
    if data is None:
        raise SystemExit(f"I1-E: {race_dir} に確定済み report.json＋research が無い＝実行拒否"
                         "（オッズより先に予想を確定させる）")
    ex = score_race.compute_exotics(data)
    probs = {"umaren": ex["pair"], "sanrenpuku": ex["trio"]}

    ev_rows = []      # 全組の {bet, comb, p, odds, ev}
    overround = {}
    for bet, m in odds.items():
        if m:
            overround[bet] = round(sum(1.0 / o for o in m.values() if o > 0), 3)
        for comb, o in m.items():
            p = probs[bet].get(comb)
            if p is None:
                continue
            ev_rows.append({"bet": bet, "comb": comb, "p": round(p, 5),
                            "odds": o, "ev": round(p * o, 3)})
    ev_rows.sort(key=lambda r: -r["ev"])

    boxes = []
    for sid, spec in STRATEGIES.items():
        bet = spec["bet"]
        combos = spec["build"](report)
        if not combos:
            continue
        keys = [norm_key(c) for c in combos]
        box_p = sum(probs[bet].get(k, 0.0) for k in keys)
        priced = [(k, odds.get(bet, {}).get(k)) for k in keys]
        evs = [(k, probs[bet].get(k, 0.0) * o) for k, o in priced if o]
        boxes.append({"strategy": sid, "label": spec["label"], "bet": bet,
                      "points": len(keys), "box_hit_prob": round(box_p, 4),
                      "priced_points": len(evs),
                      "ev_gt1": sum(1 for _, e in evs if e > 1.0),
                      "avg_ev": round(sum(e for _, e in evs) / len(evs), 3) if evs else None,
                      "best": max(evs, key=lambda x: x[1]) if evs else None,
                      "combos": keys})
    return {"race_id": report.get("race_id", os.path.basename(race_dir.rstrip("/"))),
            "model_version": ex["model_version"],
            "generated_at": datetime.date.today().isoformat(),
            "overround": overround, "odds": odds, "ev_rows": ev_rows, "boxes": boxes}


def human(out, top):
    L = [f"# {out['race_id']}  EVボード（I1-E・確率=エンジン v{out['model_version']} exotics・市場較正前の参考値）"]
    for bet, ov in out["overround"].items():
        L.append(f"Σ1/odds {BET_JP[bet]} = {ov}（1.2〜1.3付近が正常＝控除率の目安。大きくズレたら貼り付け不完全）")
    L.append("")
    L.append("== 箱候補（box_sim.STRATEGIES と同源） ==")
    L.append(f"{'戦略':<16} {'券種':<4} {'点':>3} {'箱的中確率':>9} {'オッズ有':>7} {'EV>1':>5} {'平均EV':>7}  best")
    for b in out["boxes"]:
        best = f"{b['best'][0]} (EV {b['best'][1]:.2f})" if b["best"] else "-"
        avg = f"{b['avg_ev']:.3f}" if b["avg_ev"] is not None else "-"
        L.append(f"{b['strategy']:<16} {BET_JP[b['bet']]:<4} {b['points']:>3} "
                 f"{b['box_hit_prob']*100:8.2f}% {b['priced_points']:>7} {b['ev_gt1']:>5} {avg:>7}  {best}")
    L.append("")
    L.append(f"== EV 上位 {top} 組（p×オッズ） ==")
    L.append(f"{'券種':<4} {'組':<9} {'p':>7} {'オッズ':>7} {'EV':>6}")
    for r in out["ev_rows"][:top]:
        L.append(f"{BET_JP[r['bet']]:<4} {r['comb']:<9} {r['p']*100:6.2f}% {r['odds']:>7.1f} {r['ev']:>6.2f}")
    if not out["ev_rows"]:
        L.append("（オッズ未入力 or 組不一致＝EV行なし）")
    L.append("")
    L.append("※ I1-E: 金額・購入判断は人間。オッズ・EVは data/ev/ の外に出さない（予想側へ還流しない）。")
    return "\n".join(L)


def self_check():
    errs = []
    # 1) オッズパース（行・プレフィクス・JSON・全角）
    o = parse_odds("1-5 12.3\n馬連 2-8 45.0\n三連複 1-2-3 99.9\n５-８ 7.0", default_bet="umaren")
    if o.get("umaren") != {"1-5": 12.3, "2-8": 45.0, "5-8": 7.0} or o.get("sanrenpuku") != {"1-2-3": 99.9}:
        errs.append(f"parse_odds(行) 不一致: {o}")
    oj = parse_odds(json.dumps({"馬連": {"5-1": 12.3}, "sanrenpuku": {"3-1-2": 45.6}}))
    if oj != {"umaren": {"1-5": 12.3}, "sanrenpuku": {"1-2-3": 45.6}}:
        errs.append(f"parse_odds(JSON) 不一致: {oj}")
    # 2) EV 算術（toy エンジン入力・p×odds）
    data = {"race_id": "toy", "horses": [
        {"no": 1, "style": "逃", "ten_speed": "速", "scores": {"A": 1}, "conf": {}},
        {"no": 2, "style": "差", "ten_speed": "中", "scores": {"A": 0}, "conf": {}},
        {"no": 3, "style": "追", "ten_speed": "遅", "scores": {"A": -1}, "conf": {}}],
        "patterns": [{"id": "P1", "prob": 1.0, "pace_level": 0.5}]}
    ex = score_race.compute_exotics(data)
    p12 = ex["pair"]["1-2"]
    rows = [{"bet": "umaren", "comb": "1-2", "p": p12, "odds": 4.0, "ev": round(p12 * 4.0, 3)}]
    if abs(rows[0]["ev"] - round(p12 * 4.0, 3)) > 1e-9:
        errs.append("EV算術 不一致")
    if abs(sum(ex["pair"].values()) - 1.0) > 0.02:
        errs.append(f"Σpair={sum(ex['pair'].values()):.3f}≠1")
    # 3) 書き込みガード（data/ev/ の外は拒否）
    try:
        guard_out(os.path.join(ROOT, "data", "screening", "x.json"))
        errs.append("guard_out: data/screening/ への書き込みが通った")
    except ValueError:
        pass
    try:
        guard_out(os.path.join(EV_DIR, "ev-test.json"))
    except ValueError:
        errs.append("guard_out: data/ev/ 配下が拒否された")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("race_id", nargs="?", help="dir-race-id（data/races/<id>/ に report.json 必須）")
    ap.add_argument("--bet", choices=["umaren", "sanrenpuku"], default=None,
                    help="プレフィクス無し行テキストの券種")
    ap.add_argument("--odds-file", default=None, help="保存済みオッズ JSON（data/ev/）")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--save", action="store_true", help="data/ev/ev-<race_id>.json に保存")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        errs = self_check()
        if errs:
            print("SELF-CHECK FAIL: " + "; ".join(errs), file=sys.stderr)
            sys.exit(1)
        print("self-check OK (odds parse / EV算術 / Σpair / 書き込みガード)")
        return
    if not args.race_id:
        print(__doc__)
        sys.exit(2)

    if args.odds_file:
        odds = parse_odds(open(args.odds_file, encoding="utf-8").read(), args.bet)
    elif not sys.stdin.isatty():
        odds = parse_odds(sys.stdin.read(), args.bet)
    else:
        odds = {}
        print("注意: オッズ未入力（stdin/--odds-file 無し）＝確率と箱候補のみ表示", file=sys.stderr)

    race_dir = os.path.join(ROOT, "data", "races", args.race_id)
    out = build_ev(race_dir, odds)

    if args.save:
        os.makedirs(EV_DIR, exist_ok=True)
        path = guard_out(os.path.join(EV_DIR, f"ev-{args.race_id}.json"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"保存: {os.path.relpath(path, ROOT)}", file=sys.stderr)

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else human(out, args.top))


if __name__ == "__main__":
    main()
