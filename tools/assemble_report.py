#!/usr/bin/env python3
"""report.json の骨格ジェネレータ（手書きJSONをやめる＝検証手戻りを構造的に潰す）。

合成結果（pace-model.json）＋ research-*.json（観点スコア/pros/cons）＋ seed.json（出走表スパイン）から、
report.json の**決定論で組める部分を機械生成**する。手書きで起きていた事故（市場語混入・box_reverse の id 違い・
%混入・全頭カバー漏れ・観点 artifact 取りこぼし）が構造的に起きなくなる。

ツールが埋める（決定論）:
  - meta（race_id 分解・used_observations＝実在する research-*.json から・field_size）
  - pace.leg_table（seed のスパイン＝gate/no/horse/jockey/trainer/leg_type）
  - pace.patterns（pace-model.json を report スキーマへ転記＝tier/prob/phase_flow/leg_advantage/formation）
  - pace.box_reverse・rank[].pattern_fit（pace-model の per_horse_fit をパースして同源生成＝I7 で矛盾しない）
  - rank[] の骨格（no/gate/horse/jockey/trainer/leg_type/jockey_change＝前走騎手比較で機械判定）
  - rank[].pros/cons の**素材**（research の各観点 pros/cons を tag 付きで束ねる＝人間が取捨選択）
  - win_prob/place_prob=0.0（後段 inject_probs.py が上書き）

人間（LLM）が後で上書きする（論理ファースト＝I8・散文）:
  - rank[].mark / rank_order（並びは論理が主＝ツールはスコア降順の暫定値を入れる）
  - rank[].intent（F+K+H から導出）・pace_sensitivity（展開感度の1行）
  - pros/cons の最終取捨・推敲、header_notes/pivot/shape_note/transmission など散文

使い方:
  python3 tools/assemble_report.py <race-id> --skeleton            # report.json を骨格生成（既存があれば *.skeleton.json に出す）
  python3 tools/assemble_report.py <race-id> --skeleton --force    # report.json に直接書く（手組み前の初期化）
  python3 tools/assemble_report.py --self-check
設計: 標準ライブラリのみ。%・市場語は一切出さない（research 由来の文字列は通すが、市場語スキャンは validate_report が担当）。
"""
import sys, json, re, argparse, glob, os

RACES = "data/races"


def parse_fit(s):
    """per_horse_fit → {no:score}。正規スキーマ [{no,fit},...]・dict {no:fit}・文字列 '4:+2 6:+1' のいずれでも受ける。"""
    out = {}
    if isinstance(s, list):
        for e in s:
            if isinstance(e, dict) and e.get("no") is not None and e.get("fit") is not None:
                out[int(e["no"])] = int(round(float(e["fit"])))
        return out
    if isinstance(s, dict):
        for k, v in s.items():
            try:
                out[int(k)] = int(round(float(v)))
            except (TypeError, ValueError):
                pass
        return out
    for m in re.finditer(r'(\d+)\s*:\s*([+-]?\d+)', s or ''):
        out[int(m.group(1))] = int(m.group(2))
    return out


def fit_to_mark(score):
    """per_horse_fit スコア → pattern_fit 記号。+2以上=◎中心 / +1=○圏内 / それ未満=記載なし（△は人間が手で）。"""
    return '◎' if score >= 2 else ('○' if score == 1 else None)


def to_int_list(v):
    """formation_head/last_corner を int[] に正規化（LLM出力が '4→11→6' 等の文字列でも数字を順に拾う）。"""
    if isinstance(v, list):
        return [int(x) for x in v if isinstance(x, int) or (isinstance(x, str) and x.strip().isdigit())]
    if isinstance(v, str):
        return [int(m) for m in re.findall(r'\d+', v)]
    return []


def to_leg_adv(v):
    """leg_advantage を dict に正規化（LLM出力が '逃げ+1 先行+2 差し-1 追込-2' の文字列でも拾う）。"""
    if isinstance(v, dict):
        return v
    out = {}
    if isinstance(v, str):
        for k in ("逃げ", "先行", "差し", "追込"):
            m = re.search(re.escape(k) + r'\s*([+-]?\d+)', v)
            if m:
                out[k] = int(m.group(1))
    return out


# research 由来の pros/cons 素材に紛れる NG 語（validate_report が弾く＝骨格段階で落として手戻りを消す）。
_NG_RE = re.compile(r'[%％]|人気|オッズ|配当|払戻')


def clean_note(s):
    """note に %/市場語が混じっていたら骨格から落とす（素材なので捨ててよい＝人間が必要なら書き直す）。"""
    return None if (not isinstance(s, str) or _NG_RE.search(s)) else s


def load_research(race_dir):
    res = {}
    for f in sorted(glob.glob(f"{race_dir}/research-*.json")):
        pt = os.path.basename(f)[len("research-"):-len(".json")]
        try:
            res[pt] = json.load(open(f, encoding="utf-8"))
        except Exception:
            pass
    return res


def horse_scores(research):
    """{no: {観点: score}} と {no: {観点: (pros,cons)}} を作る。E(legs)はスコア無しなので除外。"""
    sc, pc = {}, {}
    for pt, r in research.items():
        if not isinstance(r, dict) or "horses" not in r:
            continue
        for h in r["horses"]:
            no = h.get("no")
            if not isinstance(no, int):
                continue
            sc.setdefault(no, {})[pt] = h.get("score")
            pc.setdefault(no, {})[pt] = (h.get("pros") or [], h.get("cons") or [])
    return sc, pc


def build_pace(pm, seed):
    """pace-model.json → report.pace。patterns 転記＋leg_table＋box_reverse(per_horse_fit同源)。"""
    patterns = []
    for p in pm.get("patterns", []):
        fit = parse_fit(p.get("per_horse_fit", ""))
        patterns.append({
            "id": p.get("id"), "name": p.get("name"),
            "tier": p.get("likelihood_tier") or p.get("tier"),
            "prob": p.get("prob"), "trigger": p.get("trigger"),
            "pace_level": p.get("pace_level"),
            "contesters": p.get("contesters") or [],
            "leg_advantage": to_leg_adv(p.get("leg_advantage")),
            "formation_head": to_int_list(p.get("formation_head")),
            "formation_last_corner": to_int_list(p.get("formation_last_corner")),
            "bias": p.get("bias"),
            "phase_flow": p.get("phase_flow") or {},
            "risers": sorted([n for n, s in fit.items() if s >= 1]),
            "sinkers": sorted([n for n, s in fit.items() if s < 0]),
        })
    # box_reverse: per_horse_fit を同源にして転置（center>=2 / inside==1 / spot==0 / drop<0）
    box = []
    for p in pm.get("patterns", []):
        fit = parse_fit(p.get("per_horse_fit", ""))
        box.append({
            "pattern": p.get("id"),
            "tier": p.get("likelihood_tier") or p.get("tier"),
            "center": sorted([n for n, s in fit.items() if s >= 2]),
            "inside": sorted([n for n, s in fit.items() if s == 1]),
            "spot": sorted([n for n, s in fit.items() if s == 0]),
            "drop": sorted([n for n, s in fit.items() if s < 0]),
        })
    leg_table = [{
        "gate": str(h.get("waku") or ""), "no": h.get("no"), "horse": h.get("name"),
        "jockey": h.get("jockey"), "trainer": h.get("trainer"),
        "leg_type": h.get("style"), "recent_pos": "", "expected_pos": "",
    } for h in seed.get("horses", [])]
    return {
        "verification_contract": "",  # 人間が記述
        "pace_factors": [],           # 人間が記述（5材料）
        "leg_table": leg_table,
        "patterns": patterns,
        "shape_note": "", "formation_note": "", "bias_note": "",
        "counter_conditions": pm.get("falsification") or "",
        "transmission": "",
        "box_reverse": box,
    }


def jockey_change(h):
    """前走騎手(recent[0].jockey)と今走鞍上を比較＝継続/乗替を機械判定（強化/弱化は K が上書き）。"""
    rec = h.get("recent") or []
    prev = rec[0].get("jockey") if rec else None
    if not prev:
        return "乗替"  # 不明＝テン乗り扱いの保留
    return "継続" if prev == h.get("jockey") else "乗替"


def build_rank(pm, seed, sc, pc):
    """rank[] の骨格。mark/rank_order は暫定（スコア降順）＝人間が論理で上書き。"""
    fits = {p.get("id"): parse_fit(p.get("per_horse_fit", "")) for p in pm.get("patterns", [])}
    rows = []
    for h in seed.get("horses", []):
        no = h.get("no")
        pattern_fit = {}
        for pid, fit in fits.items():
            mk = fit_to_mark(fit.get(no, -9))
            if mk:
                pattern_fit[pid] = mk
        # pros/cons の素材: スコア>0観点の pros 全件、スコア<0観点と I の cons 全件を tag 付きで束ねる
        pros, cons = [], []
        for pt, (pp, cc) in (pc.get(no) or {}).items():
            s = (sc.get(no) or {}).get(pt)
            if isinstance(s, (int, float)) and s > 0:
                for note in pp:
                    cleaned = clean_note(note)
                    if cleaned:
                        pros.append({"tag": pt, "note": cleaned})
            if pt == "I" or (isinstance(s, (int, float)) and s < 0):
                for note in cc:
                    cleaned = clean_note(note)
                    if cleaned:
                        cons.append({"tag": pt, "note": cleaned})
        total = sum(v for v in (sc.get(no) or {}).values() if isinstance(v, (int, float)))
        rows.append({
            "no": no, "gate": str(h.get("waku") or ""), "horse": h.get("name"),
            "jockey": h.get("jockey"), "trainer": h.get("trainer"),
            "jockey_change": jockey_change(h),
            "intent": "→",            # 人間が F+K+H から上書き
            "mark": "—",              # 人間が論理で上書き
            "rank_order": 0,          # 下で暫定連番
            "win_prob": 0.0, "place_prob": 0.0,  # inject_probs が上書き
            "leg_type": h.get("style"),
            "pattern_fit": pattern_fit,
            "pace_sensitivity": "",   # 人間が記述
            "pros": pros[:4], "cons": cons[:4],
            "_score_sum": round(total, 1),  # 暫定並び用（最後に消す）
        })
    rows.sort(key=lambda r: -r["_score_sum"])
    for i, r in enumerate(rows, 1):
        r["rank_order"] = i
        del r["_score_sum"]
    return rows


def assemble(race_id):
    rd = f"{RACES}/{race_id}"
    seed = json.load(open(f"{rd}/seed.json", encoding="utf-8"))
    pm = json.load(open(f"{rd}/pace-model.json", encoding="utf-8"))
    research = load_research(rd)
    sc, pc = horse_scores(research)
    date = f"{race_id[:4]}-{race_id[4:6]}-{race_id[6:8]}" if race_id[:8].isdigit() else ""
    rno = race_id.split("-")[-1]
    report = {
        "schema_version": "1.0", "race_id": race_id,
        "race_name": "", "edition": "", "race_no": int(rno) if rno.isdigit() else None, "grade": "",
        "date": date,
        "course": {"track": "", "surface": seed.get("surface", ""), "distance": seed.get("distance"), "direction": ""},
        "conditions": "", "field_size": seed.get("headcount") or len(seed.get("horses", [])),
        "model_version": "5.0",
        "used_observations": sorted(research.keys()),
        "header_notes": [
            "市場ゼロ(I1): 市場情報・他人の予想は不使用。並びは馬の内在情報のみ。",
            "win_prob/place_prob は score_race.py の決定論出力＝較正先(市場)を持たない内在確率で偽の精度。並びは論理(rank_order)が主・率は参考列。",
        ],
        "pivot": "",
        "day_board": {
            "reference_races": [], "reference_note": "",
            "observation_blanks": "ペース層 / 内外バイアス / 決まり手 / 伸び位置",
            "going": [{"item": "馬場状態", "value": "", "read": ""}],
            "paddock_watch": [], "other_unknowns": [],
        },
        "pace": build_pace(pm, seed),
        "rank_verification_contract": "",
        "rank": build_rank(pm, seed, sc, pc),
        "data_confidence": [], "reinforcement_requests": [],
    }
    return report


def self_check():
    # 最小 fixture を組んで pattern_fit と box_reverse が同源・全頭カバー・rank_order連番を確認
    seed = {"surface": "ダ", "distance": 1700, "headcount": 2, "horses": [
        {"no": 1, "waku": 1, "name": "A", "jockey": "x", "trainer": "t", "style": "先", "recent": [{"jockey": "x"}]},
        {"no": 2, "waku": 2, "name": "B", "jockey": "y", "trainer": "t", "style": "差", "recent": [{"jockey": "z"}]},
    ]}
    pm = {"patterns": [{"id": "α", "name": "n", "likelihood_tier": "本線", "prob": 1.0,
                        "phase_flow": {}, "leg_advantage": "逃げ+1 先行+2 差し-1 追込-2",  # str も dict 正規化されるか
                        "formation_head": "1→2", "formation_last_corner": [1, 2],  # str も正規化されるか
                        "per_horse_fit": "1:+2 2:-1"}], "falsification": "f"}
    import tempfile
    d = tempfile.mkdtemp()
    os.makedirs(f"{d}/data/races/t-x-01", exist_ok=True)
    global RACES
    RACES = f"{d}/data/races"
    json.dump(seed, open(f"{RACES}/t-x-01/seed.json", "w"))
    json.dump(pm, open(f"{RACES}/t-x-01/pace-model.json", "w"))
    json.dump({"point": "A", "horses": [{"no": 1, "name": "A", "score": 2, "pros": ["好"], "cons": []},
                                        {"no": 2, "name": "B", "score": -1, "pros": [], "cons": ["難", "単勝圏外の走破時計", "後方0%勝率"]}]},
              open(f"{RACES}/t-x-01/research-A.json", "w"))
    rep = assemble("t-x-01")
    assert len(rep["rank"]) == 2, "全頭カバー"
    assert [r["rank_order"] for r in rep["rank"]] == [1, 2], "rank_order連番"
    assert rep["rank"][0]["no"] == 1 and rep["rank"][0]["pattern_fit"] == {"α": "◎"}, "fit ◎(+2)"
    assert rep["pace"]["box_reverse"][0]["center"] == [1] and rep["pace"]["box_reverse"][0]["drop"] == [2], "box同源"
    assert rep["rank"][0]["jockey_change"] == "継続" and rep["rank"][1]["jockey_change"] == "乗替", "乗替判定"
    assert rep["used_observations"] == ["A"], "観点はartifactから"
    assert rep["pace"]["patterns"][0]["formation_head"] == [1, 2], "formation str→int[] 正規化"
    assert rep["pace"]["patterns"][0]["leg_advantage"] == {"逃げ": 1, "先行": 2, "差し": -1, "追込": -2}, "leg_advantage str→dict 正規化"
    b2 = [r for r in rep["rank"] if r["no"] == 2][0]
    cons_notes = [c["note"] for c in b2["cons"]]
    assert "難" in cons_notes, "正当なcons noteが残る"
    assert "後方0%勝率" not in cons_notes, "%混入noteは骨格から除外"
    # clean_note が「単勝」「複勝」を通すことを直接検証（cc[0]のみ拾う構造のためcons_notesでは検証困難）
    assert clean_note("単勝圏外の走破時計") == "単勝圏外の走破時計", "「単勝」を含む正当noteは通す（validate_reportと同基準）"
    assert clean_note("複勝実績あり") == "複勝実績あり", "「複勝」を含む正当noteは通す"
    assert clean_note("3番人気") is None, "「人気」はNG"
    blob = json.dumps(rep, ensure_ascii=False)
    for w in ["%", "％"]:
        assert w not in blob, f"%混入 {w}"
    print("self-check OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("race_id", nargs="?")
    ap.add_argument("--skeleton", action="store_true", help="report.json 骨格を生成")
    ap.add_argument("--force", action="store_true", help="既存 report.json に直接書く（初期化）")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        self_check(); return
    if not a.race_id:
        ap.error("race_id が必要（または --self-check）")
    rep = assemble(a.race_id)
    rd = f"{RACES}/{a.race_id}"
    out = f"{rd}/report.json" if a.force else f"{rd}/report.skeleton.json"
    if os.path.exists(f"{rd}/report.json") and not a.force:
        out = f"{rd}/report.skeleton.json"
    json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✓ {out} に骨格を生成（mark/rank_order/intent/散文は人間が論理で埋める→ inject_probs → validate → project）")


if __name__ == "__main__":
    main()
