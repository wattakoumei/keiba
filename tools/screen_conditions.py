#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""screen_conditions.py — 選別レイヤー(/screen-card)の STEP2 決定論実装。

カードの**全レース**に「条件荒れ度(強/中/弱)＋荒れフラグ」を機械的に付ける（場・頭数・距離・芝ダ・クラス・重賞名から）。
web 不要・オッズ不要＝未来日付でも全Rやっても軽い。源は [[upset-conditions]] カタログ（数値根拠はそちら）。
★I1-S: 市場は使わない（条件は番組情報のみ）。出力は data/screening/ のみ。

CLI:
  python3 tools/screen_conditions.py assess <YYYYMMDD> <場2桁> [--json]      # 全Rの条件荒れ度を表示
  python3 tools/screen_conditions.py fill   <YYYYMMDD> <場2桁> <venue-romaji> # data/screening/<day>-<venue>.json に
                                                                              #   未掲載のRを「見送り(条件のみ)」で全R埋める
  python3 tools/screen_conditions.py --self-check
"""
import sys
import os
import re
import json
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 夏ローカル＝荒れ寄り（中央4場 東京05/中山06/京都08/阪神09 は base 0＝堅い）。upset-conditions §1。
VENUE_BASE = {"03": ("福島", 2.0), "10": ("小倉", 1.5), "02": ("函館", 1.0),
              "07": ("中京", 1.0), "04": ("新潟", 1.0), "01": ("札幌", 0.5)}
# ローカルG3ハンデ重賞（荒れ↑↑強・upset-conditions #3）/ 堅い重賞（控え目）
ARE_JUSHO = ["函館記念", "ラジオＮＩＫＫＥＩ賞", "ラジオNIKKEI", "七夕賞", "北九州記念",
             "愛知杯", "関屋記念", "アイビスＳＤ", "アイビスSD", "ターコイズ", "エプソム"]
KATAI_JUSHO = ["中山金杯", "京都金杯", "アルゼンチン共和国杯", "日経新春杯"]
PLACE = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
         "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}


def cond_assess(place, surface, distance, headcount, race_name):
    """番組情報 → {cond_rage 強/中/弱, cond_flags[], class}。スコアの閾値は upset-conditions の序列を反映。"""
    nm = race_name or ""
    d = distance or 0
    hc = headcount or 0
    score = 0.0
    flags = []

    vb = VENUE_BASE.get(place)
    if vb:
        score += vb[1]
        flags.append(f"{vb[0]}開催")

    if hc >= 18:
        score += 2.0; flags.append("フルゲート18頭")
    elif hc >= 16:
        score += 1.5; flags.append("多頭数")
    elif hc == 15:
        score += 1.0; flags.append("多頭数")
    elif 0 < hc <= 6:
        score -= 1.5; flags.append("超少頭数")
    elif 0 < hc <= 8:
        score -= 1.0; flags.append("少頭数")
    elif 0 < hc <= 10:
        score -= 0.3

    if surface == "芝" and 0 < d <= 1200:
        score += 1.0; flags.append("芝短距離")
    if surface == "ダ":
        score -= 0.3
    if surface == "芝" and 1800 <= d <= 2400:
        score -= 0.3
    if surface == "障":
        score += 0.5; flags.append("障害")

    klass = None
    if "新馬" in nm:
        score -= 1.5; klass = "新馬"
    elif "未勝利" in nm:
        score -= 1.0; klass = "未勝利"
    elif "1勝" in nm or "１勝" in nm:
        klass = "1勝クラス"
    elif "2勝" in nm or "２勝" in nm:
        score += 0.3; klass = "2勝クラス"
    elif "3勝" in nm or "３勝" in nm:
        score += 1.0; klass = "3勝クラス"; flags.append("3勝クラス")

    grade = None
    if "ＧⅢ" in nm or "(GⅢ)" in nm or "GⅢ" in nm or "G3" in nm:
        grade = "GⅢ"
    elif "ＧⅡ" in nm or "GⅡ" in nm:
        grade = "GⅡ"; score -= 0.5
    elif "ＧⅠ" in nm or "GⅠ" in nm:
        grade = "GⅠ"

    if any(k in nm for k in ARE_JUSHO):
        score += 2.0
        if "ローカルG3ハンデ重賞" not in flags:
            flags.append("ローカルG3ハンデ重賞")
    elif any(k in nm for k in KATAI_JUSHO):
        score -= 0.5

    is_special = ("ステークス" in nm) or ("特別" in nm) or ("杯" in nm) or ("カップ" in nm)
    if is_special:
        score += 0.3
        if not klass:
            klass = "特別/OP"

    if grade:
        klass = grade

    rage = "強" if score >= 2.5 else "中" if score >= 1.0 else "弱"
    seen = set()
    flags = [f for f in flags if not (f in seen or seen.add(f))]
    return {"cond_rage": rage, "cond_flags": flags, "class": klass or "—",
            "_score": round(score, 2)}


def fetch_day(ymd, place):
    """fetch_racecard.py day をサブプロセスで叩いて全Rの番組情報を得る。"""
    r = subprocess.run([sys.executable, os.path.join(HERE, "fetch_racecard.py"),
                        "day", ymd, place, "--json"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 and not r.stdout.strip():
        raise RuntimeError(f"fetch_racecard day 失敗: {r.stderr[:200]}")
    data = json.loads(r.stdout)
    return data if isinstance(data, list) else data.get("races", [])


def cmd_assess(ymd, place, as_json):
    rows = []
    for rc in fetch_day(ymd, place):
        c = cond_assess(place, rc.get("surface"), rc.get("distance"),
                        rc.get("headcount"), rc.get("race_name"))
        rows.append({"r": rc["r"], "surface": rc.get("surface"), "distance": rc.get("distance"),
                     "headcount": rc.get("headcount"), "race_name": rc.get("race_name"), **c})
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"{PLACE.get(place, place)} {ymd}  条件荒れ度（全R）")
        for x in rows:
            print(f"  {x['r']:>2}R 荒れ:{x['cond_rage']}  {x['surface']}{x['distance']}m {x['headcount']}頭"
                  f"  {x['class']:<8} {x['race_name']}  [{' '.join(x['cond_flags'])}]")


def cmd_fill(ymd, place, venue):
    """既存 screening ファイルに未掲載のRを『見送り(条件のみ・軸未評価)』で足して全Rにする。"""
    path = os.path.join(ROOT, "data", "screening", f"{ymd}-{venue}.json")
    if os.path.exists(path):
        data = json.load(open(path, encoding="utf-8"))
    else:
        data = {"date": ymd, "venue": venue, "place": place,
                "as_of": "(条件のみ)", "odds_available": False, "races": []}
    have = {r["r"] for r in data["races"]}
    day = fetch_day(ymd, place)
    times = {rc["r"]: rc.get("post_time") for rc in day}
    # 既存行（ハーネス作成分を含む）にも発走時刻を充填＝バックフィル兼用
    for r in data["races"]:
        if times.get(r["r"]):
            r["post_time"] = times[r["r"]]
    added = 0
    for rc in day:
        if rc["r"] in have:
            continue
        c = cond_assess(place, rc.get("surface"), rc.get("distance"),
                        rc.get("headcount"), rc.get("race_name"))
        data["races"].append({
            "r": rc["r"], "post_time": rc.get("post_time"),
            "surface": rc.get("surface"), "distance": rc.get("distance"),
            "headcount": rc.get("headcount"), "class": c["class"], "race_type": "—",
            "race_name": rc.get("race_name"),
            "cond_rage": c["cond_rage"], "cond_flags": c["cond_flags"],
            "dango_tier": None, "dango_signals": [],
            "x_axis": None, "quadrant": "見送り", "score": -3,
        })
        added += 1
    data["races"].sort(key=lambda r: (-(r.get("score") if r.get("score") is not None else -99), r["r"]))
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{path}: +{added}R（全{len(data['races'])}R）", [f'{r["r"]}:{r["quadrant"]}' for r in data["races"]])


def self_check():
    ok = True
    cases = [
        # 福島フルゲート芝短ハンデ重賞っぽい → 強
        ("03", "芝", 1200, 16, "3歳上1勝クラス", "強"),
        # 函館記念GⅢ → 強
        ("02", "芝", 2000, 15, "函館記念(ＧⅢ)", "強"),
        # 超少頭数未勝利 → 弱
        ("03", "芝", 1200, 5, "サラ系2歳未勝利", "弱"),
        # 東京（中央場）芝中距離定量 → 弱
        ("05", "芝", 2000, 12, "3歳上2勝クラス", "弱"),
    ]
    for place, surf, dist, hc, nm, expect in cases:
        got = cond_assess(place, surf, dist, hc, nm)["cond_rage"]
        mark = "OK" if got == expect else "FAIL"
        if got != expect:
            ok = False
        print(f"[{mark}] {place} {nm} → {got} (expect {expect})")
    print("self-check:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 0
    if a[0] == "--self-check":
        return self_check()
    cmd = a[0]
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    try:
        if cmd == "assess":
            cmd_assess(a[1], a[2], as_json)
        elif cmd == "fill":
            cmd_fill(a[1], a[2], a[3])
        else:
            sys.stderr.write(f"unknown command: {cmd}\n"); return 2
    except Exception as e:
        sys.stderr.write(f"[error] {e}\n"); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
