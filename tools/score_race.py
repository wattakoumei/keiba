#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
score_race.py — 着順エンジン v4.0（相変位再帰モデル）の決定論リファレンス実装。

仕様の正本は .claude/skills/analyze-race/references/scoring-model.md（v4.0）。
本コードの PARAMS は同書の「パラメータ早見表」6値と一致させること（review は markdown を編集→ここへミラー）。

何をするか:
  エージェントが調査して組み立てた「観点スコア(A〜K)＋著作した展開パターン(prob, pace_level, contesters)」を入力に、
  相別能力(early/cruise/finish/class)を作り、3相再帰({pos,energy}を持ち越し)で各パターンの終端スコア S を出し、
  softmax→Harville でパターン別条件付き着順、パターン確率で加重した最終着順分布を返す。
  併せて展開検証用の派生 leg_advantage / formation を逆生成する（合成器の著作値があれば、本派生は整合チェック用）。

なぜコード化するか:
  3相再帰(シグモイド・エネルギー減衰・Harville)は手計算では揺れる(v3.0の「85%過信」はこの揺れが一因)。
  標準ライブラリのみ(math/json、pip不要＝fetch_racecard.py と同方針)。

使い方:
  python3 tools/score_race.py --in race.json            # 人間可読
  python3 tools/score_race.py --in race.json --json      # 構造化出力(レポート/jsonl転記用)
  python3 tools/score_race.py --in race.json --self-check # 健全性検査(Σprob≈1・正規化)
  cat race.json | python3 tools/score_race.py --json      # stdin も可

入力スキーマ(抜粋):
  {"race_id":"...",
   "horses":[{"no":4,"name":"...","ten_speed":"速","style":"逃","agari_best":36.4,
              "recent":[{"first_corner":1,"field":12}],
              "scores":{"A":0,"B":0,"C":0.5,"D":2,"F":0,"G":0,"H":0,"I":0,"K":0},
              "conf":{"A":"低"}, "draw_adj":0.05}],
   "patterns":[{"id":"P1","prob":0.46,"pace_level":0.22,"contesters":[4]}],
   "params":{...任意上書き...}}
"""
import sys, json, math, argparse, statistics

MODEL_VERSION = "4.1"

# === パラメータ早見表（6ノブ・scoring-model.md と一致させる） ===
PARAMS = {
    "k_pos":   1.6,   # 序盤の位置取り広がり
    "c_drain": 0.45,  # 中盤の基本消耗
    "g_fwd":   0.35,  # 前を取りに行く消耗結合
    "w_pos0":  0.8,   # 終端の位置重み(ハイ時 L=1)
    "w_pos1":  2.6,   # スロー化で増える位置重み(=前残りレバー, L=0で計3.4)
    "T":       0.35,  # softmax 温度(S スケール 0..~1.5 上)
    "LEG_ADV_GAIN": 0.20,  # 合成器著作 leg_advantage の終端S変調ゲイン(v4.1)。pace_level では出ないコース固有の脚質有利不利(残差)を率に反映。0=従来(無効)
}
# 構造定数（非tunable・ノブ数を6に固定するため）
MID_DRAIN_BASE, MID_DRAIN_PACE = 0.6, 0.8   # 中盤消耗 (0.6 + 0.8*L)
POS_DECAY = 0.15                            # 中盤の位置減衰
INTENT_PACE_DAMP = 0.5                      # 序盤 intent をペースで抑制
ENERGY_FLOOR = 0.05
# A_class を [CLASS_FLOOR,1] の変調帯へ圧縮（地力を支配項でなく乗数に留め、位置が競えるように）。
# これが無いと A_class(0..1) が全体に掛かり v3.0 と同じ「地力支配」へ戻る（加古川⑥の再現）。
CLASS_FLOOR = 0.60

TEN_MAP = {"速": 1.0, "中": 0.5, "遅": 0.1}
STY_MAP = {"逃": 1.0, "先": 0.75, "差": 0.3, "追": 0.1}
# 脚質ラベルの別名（先頭文字で吸収）
STY_ALIAS = {"逃げ": "逃", "先行": "先", "差し": "差", "追込": "追", "自在": "先"}
# _sty_key の返すキー → leg_advantage(report.json) のキー（合成器はフル名で著作）
STY_TO_ADV = {"逃": "逃げ", "先": "先行", "差": "差し", "追": "追込"}


def norm(score, conf):
    """観点スコア e∈[-2,+2] を 0..1 に正規化。低確信は中央へ収縮。"""
    if score is None:
        score = 0.0
    n = (score + 2) / 4.0
    n = max(0.0, min(1.0, n))
    f = {"低": 0.70, "低〜中": 0.85, "中〜低": 0.85}.get(conf, 1.0)
    return 0.5 + (n - 0.5) * f


def clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def sigmoid(x):
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def _sty_key(style):
    if not style:
        return None
    s = style.strip()
    if s in STY_MAP:
        return s
    if s in STY_ALIAS:
        return STY_ALIAS[s]
    # "先/差" のような複合は最初の有効トークン
    for ch in s:
        if ch in STY_MAP:
            return ch
    return None


def phase_abilities(h):
    """1頭の観点スコア＋スクレイパ値から相別能力(early/cruise/finish/class)を算出。"""
    sc = h.get("scores", {}) or {}
    cf = h.get("conf", {}) or {}

    def g(k):  # 正規化済み n_X（欠損=中立0.5）
        if k not in sc:
            return 0.5
        return norm(sc.get(k, 0.0), cf.get(k, "中"))

    nA, nB, nC, nD = g("A"), g("B"), g("C"), g("D")
    nF, nG, nH, nK = g("F"), g("G"), g("H"), g("K")
    eI = sc.get("I", 0.0) or 0.0

    # --- A_class: 旧 ability0 を 0..1 に圧縮し、乗数へ降格 ---
    base = 0.40 * nA + 0.40 * nB + 0.20 * nC
    apt = 1.0 + 0.15 * (2 * nD - 1)
    cond = (1.0 + 0.07 * (2 * nF - 1) + 0.05 * (2 * nG - 1)
            + 0.05 * (2 * nH - 1) + 0.06 * (2 * nK - 1))
    disc = 0.10 * (-eI)
    A_class_raw = clip(base * apt * cond - base * disc)
    A_class = CLASS_FLOOR + (1 - CLASS_FLOOR) * A_class_raw  # 変調帯 [CLASS_FLOOR,1]

    # --- A_early: テン速・脚質・騎手の出方・枠 ---
    ten = TEN_MAP.get(h.get("ten_speed"), 0.5)
    sty = STY_MAP.get(_sty_key(h.get("style")), 0.4)
    draw_adj = h.get("draw_adj", 0.0) or 0.0
    A_early = clip(0.55 * ten + 0.35 * sty + 0.10 * nK + draw_adj)

    # --- A_cruise: 近走位置の安定 ＋ スタミナ血統(C) ＋ 近走内容(B) ---
    # I(リスク全般)は A_class の disc で効かせる。A_cruise に混ぜると脚部不安等が巡航力を不当に下げる
    recent = h.get("recent") or []
    ratios = []
    for r in recent:
        fc, fld = r.get("first_corner"), r.get("field")
        if fc and fld:
            ratios.append(fc / fld)
    if len(ratios) >= 2:
        stab = 1.0 - clip(statistics.pstdev(ratios) / 0.30)
    else:
        stab = 0.5
    A_cruise = clip(0.50 * stab + 0.35 * nC + 0.15 * nB)

    # --- A_finish: 上がり最速(相対) ＋ 決め手(B近走) ---
    A_finish_af = h.get("_af", 0.5)  # field 相対は集計後に注入(下の compute で設定)
    A_finish = clip(0.6 * A_finish_af + 0.4 * nB)

    return dict(A_early=A_early, A_cruise=A_cruise, A_finish=A_finish,
                A_class=A_class, _nB=nB)


def inject_af(horses, ab):
    """agari_best の field 相対(速いほど高=1)を A_finish に反映。"""
    vals = [h.get("agari_best") for h in horses if h.get("agari_best") is not None]
    if len(vals) >= 2 and max(vals) > min(vals):
        amax, amin = max(vals), min(vals)
        for h in horses:
            no = h["no"]
            a = h.get("agari_best")
            af = 0.5 if a is None else clip((amax - a) / (amax - amin))
            ab[no]["A_finish"] = clip(0.6 * af + 0.4 * ab[no]["_nB"])
    # 値が無ければ phase_abilities の af=0.5 のまま


def run_pattern(horses, ab, L, P, leg_adv=None):
    """1パターン(pace_level L)について3相再帰を回し、終端S・pos履歴・energyを返す。
    leg_adv（合成器著作の脚質別有利不利 {逃げ,先行,差し,追込} -2..+2）があれば終端Sを脚質ぶん変調＝
    pace_level では出ないコース固有の前残り/差し台頭の残差を率に反映（v4.1）。"""
    nos = [h["no"] for h in horses]
    sty_of = {h["no"]: _sty_key(h.get("style")) for h in horses}
    intent = {no: ab[no]["A_early"] * (1 - INTENT_PACE_DAMP * L) for no in nos}
    mean_intent = sum(intent.values()) / len(intent)

    pos1, energy, pos2, S = {}, {}, {}, {}
    for no in nos:
        Ae = ab[no]["A_early"]; Acr = ab[no]["A_cruise"]
        Af = ab[no]["A_finish"]; Acl = ab[no]["A_class"]
        # 序盤
        p = sigmoid(P["k_pos"] * (intent[no] - mean_intent))
        e = 1 - P["g_fwd"] * L * max(0.0, p - Acr)
        pos1[no] = p
        # 中盤
        work = L * p + (1 - Acr) * 0.5
        e = clip(e - P["c_drain"] * work * (MID_DRAIN_BASE + MID_DRAIN_PACE * L),
                 ENERGY_FLOOR, 1.0)
        p = p - POS_DECAY * (p - 0.5) * (1 - Acr)
        energy[no] = e; pos2[no] = p
        # 終盤
        w_pos = P["w_pos0"] + P["w_pos1"] * (1 - L)
        kick = Af * e
        S[no] = Acl * (w_pos * p + kick)
        # 展開項(v4.1): 合成器のleg_advantageを脚質ぶん乗算変調（la -2..+2 を /2 で -1..1、gainで控えめに）
        if leg_adv:
            ak = STY_TO_ADV.get(sty_of.get(no))
            la = leg_adv.get(ak) if ak else None
            if isinstance(la, (int, float)):
                S[no] *= clip(1 + P["LEG_ADV_GAIN"] * la / 2, 0.2, 2.0)
    return pos1, pos2, energy, S


def softmax(scores, T):
    mx = max(scores.values())
    ex = {k: math.exp((v - mx) / T) for k, v in scores.items()}
    Z = sum(ex.values())
    return {k: v / Z for k, v in ex.items()}


def harville_place3(p):
    """条件付き勝率 p(dict no->prob) から複勝率(top3)を Harville 近似。"""
    out = {}
    for i in p:
        pi = p[i]
        s = pi
        for k in p:
            if k == i:
                continue
            denom = 1 - p[k]
            if denom <= 1e-9:
                continue
            s += p[k] * pi / denom
        for k in p:
            if k == i:
                continue
            for l in p:
                if l == i or l == k:
                    continue
                d1 = 1 - p[k]
                d2 = 1 - p[k] - p[l]
                if d1 <= 1e-9 or d2 <= 1e-9:
                    continue
                s += p[k] * p[l] / d1 * pi / d2
        out[i] = s
    return out


def derive_leg_advantage(horses, ab, S):
    """脚質群の平均S − 全体平均S を符号(-2..+2)に。展開検証の整合チェック用。"""
    groups = {"逃": [], "先": [], "差": [], "追": []}
    for h in horses:
        k = _sty_key(h.get("style"))
        if k in groups:
            groups[k].append(S[h["no"]])
    allS = list(S.values())
    om = sum(allS) / len(allS)
    sd = statistics.pstdev(allS) or 1e-6
    out = {}
    for g, vs in groups.items():
        if not vs:
            out[g] = 0
            continue
        z = (sum(vs) / len(vs) - om) / sd
        if z > 0.8:
            out[g] = 2
        elif z > 0.25:
            out[g] = 1
        elif z < -0.8:
            out[g] = -2
        elif z < -0.25:
            out[g] = -1
        else:
            out[g] = 0
    return out


def compute(data):
    P = dict(PARAMS)
    P.update(data.get("params", {}) or {})
    horses = data["horses"]
    nos = [h["no"] for h in horses]
    names = {h["no"]: h.get("name", str(h["no"])) for h in horses}

    # 相別能力
    ab = {h["no"]: phase_abilities(h) for h in horses}
    inject_af(horses, ab)

    patterns = data.get("patterns") or [{"id": "P0", "prob": 1.0, "pace_level": 0.5}]

    # パターンごとに再帰→条件付き勝率・複勝率
    per_pat = {}
    for pat in patterns:
        L = pat.get("pace_level", 0.5)
        pos1, pos2, energy, S = run_pattern(horses, ab, L, P, pat.get("leg_advantage"))
        cw = softmax(S, P["T"])           # 条件付き勝率
        cp3 = harville_place3(cw)          # 条件付き複勝率
        per_pat[pat["id"]] = dict(L=L, prob=pat.get("prob", 0.0),
                                  pos1=pos1, pos2=pos2, energy=energy,
                                  S=S, cw=cw, cp3=cp3,
                                  leg=derive_leg_advantage(horses, ab, S),
                                  formation_head=[n for n in sorted(pos1, key=lambda n: -pos1[n])][:3],
                                  formation_last_corner=[n for n in sorted(pos2, key=lambda n: -pos2[n])][:6])

    # パターン確率で加重
    win = {no: sum(pp["prob"] * pp["cw"][no] for pp in per_pat.values()) for no in nos}
    place = {no: sum(pp["prob"] * pp["cp3"][no] for pp in per_pat.values()) for no in nos}

    # 偶然レンジ(σ): パターン間ばらつき ＋ 確信度
    def low_frac(h):
        cf = h.get("conf", {}) or {}
        sc = h.get("scores", {}) or {}
        if not sc:
            return 0.5
        lows = sum(1 for k in sc if cf.get(k, "中") in ("低", "低〜中", "中〜低"))
        return lows / len(sc)

    sigma = {}
    for h in horses:
        no = h["no"]
        vals = [pp["cw"][no] for pp in per_pat.values()]
        sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        sigma[no] = sd + win[no] * (0.10 + 0.10 * low_frac(h))

    # 期待着順(Bradley-Terry pairwise の近似)
    erank = {}
    for i in nos:
        r = 1.0
        for j in nos:
            if j == i:
                continue
            denom = win[i] + win[j]
            r += (win[j] / denom) if denom > 1e-12 else 0.5
        erank[i] = r

    # 出力組み立て
    horses_out = []
    for h in sorted(horses, key=lambda h: -place[h["no"]]):
        no = h["no"]
        cond = []
        for pid, pp in per_pat.items():
            cond.append({"pattern_id": pid, "win_prob": round(pp["cw"][no], 4),
                         "place_prob": round(pp["cp3"][no], 4),
                         "pos": round(pp["pos2"][no], 3),
                         "energy": round(pp["energy"][no], 3),
                         "S": round(pp["S"][no], 4)})
        horses_out.append({
            "no": no, "name": names[no],
            "phase_abilities": {k: round(ab[no][k], 3)
                                for k in ("A_early", "A_cruise", "A_finish", "A_class")},
            "win_prob": round(win[no], 4),
            "place_prob": round(place[no], 4),
            "predicted_rank": round(erank[no], 2),
            "win_range": [round(max(0.0, win[no] - sigma[no]), 4),
                          round(win[no] + sigma[no], 4)],
            "conditional": cond,
        })

    pat_out = []
    for pat in patterns:
        pp = per_pat[pat["id"]]
        pat_out.append({"id": pat["id"], "prob": pp["prob"], "pace_level": pp["L"],
                        "leg_advantage_derived": pp["leg"],
                        "formation_head_derived": pp["formation_head"],
                        "formation_last_corner_derived": pp["formation_last_corner"]})

    return {"race_id": data.get("race_id", ""), "model_version": MODEL_VERSION,
            "params": P, "horses": horses_out, "patterns_derived": pat_out}


def self_check(data, result):
    errs = []
    if not data.get("horses"):
        errs.append("頭数0")
    psum = sum(p.get("prob", 0) for p in (data.get("patterns") or []))
    if data.get("patterns") and abs(psum - 1.0) > 0.02:
        errs.append(f"Σpattern_prob={psum:.3f}≠1")
    # 各パターンの条件付き勝率は1に正規化されているはず(softmax)→加重winは≈1
    wsum = sum(h["win_prob"] for h in result["horses"])
    if abs(wsum - 1.0) > 0.02:
        errs.append(f"Σwin_prob={wsum:.3f}≠1")
    for p in (data.get("patterns") or []):
        L = p.get("pace_level")
        if L is None or not (0.0 <= L <= 1.0):
            errs.append(f"pattern {p.get('id')} pace_level 不正: {L}")
    return errs


def human(result):
    lines = []
    lines.append(f"# {result['race_id']}  model v{result['model_version']}")
    P = result["params"]
    lines.append("params: " + " ".join(f"{k}={P[k]}" for k in ("k_pos", "c_drain", "g_fwd", "w_pos0", "w_pos1", "T")))
    lines.append(f"{'No':>3} {'馬名':<12} {'early':>5} {'cruis':>5} {'finsh':>5} {'class':>5} "
                 f"{'win%':>6} {'plc%':>6} {'E[rank]':>7} {'range':>13}")
    for h in result["horses"]:
        pa = h["phase_abilities"]
        lo, hi = h["win_range"]
        lines.append(f"{h['no']:>3} {h['name']:<12} {pa['A_early']:5.2f} {pa['A_cruise']:5.2f} "
                     f"{pa['A_finish']:5.2f} {pa['A_class']:5.2f} {h['win_prob']*100:5.1f}% "
                     f"{h['place_prob']*100:5.1f}% {h['predicted_rank']:7.2f} "
                     f"{lo*100:5.1f}-{hi*100:4.1f}%")
    lines.append("")
    for p in result["patterns_derived"]:
        lines.append(f"[{p['id']}] prob={p['prob']} L={p['pace_level']} "
                     f"leg(派生)={p['leg_advantage_derived']} head={p['formation_head_derived']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    raw = open(args.infile, encoding="utf-8").read() if args.infile else sys.stdin.read()
    data = json.loads(raw)
    result = compute(data)

    if args.self_check:
        errs = self_check(data, result)
        if errs:
            print("SELF-CHECK FAIL: " + "; ".join(errs), file=sys.stderr)
            sys.exit(1)
        print("SELF-CHECK OK  Σwin=%.3f  patterns=%d  horses=%d"
              % (sum(h["win_prob"] for h in result["horses"]),
                 len(result["patterns_derived"]), len(result["horses"])))
        return

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(human(result))


if __name__ == "__main__":
    main()
