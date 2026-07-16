#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_probs.py — score_race.py の決定論出力(win_prob/place_prob)を report.json の rank[] に注入する。

I8（v5.1）: 単勝率/複勝率は score_race.py が唯一の源＝毎回これを回して rank[].win_prob/place_prob に入れる。
率の入力(観点スコア・脚質・展開パターン)は既存の research-<観点>.json と report.json から機械的に組む
（エージェントの手組みゼロ＝再現可能・手計算の揺れを排除）。**並び(rank_order/mark)は論理が主＝率順に並べ替えない**。

組み立て:
  scores{no:{X:score}} / conf{no:{X:conf}} ← research-<X>.json（ファイル名の X を観点IDに採用＝中身スキーマの揺れに依存しない）
  style                                     ← report.json pace.leg_table[].leg_type（A_early の素。ten/agari/recent は省略=中立フォールバック）
  patterns[{id,prob,pace_level,contesters}] ← report.json pace.patterns[]
  horses(no,name)                           ← report.json rank[]
→ score_race.compute → win_prob/place_prob を no で対応づけ rank[] に round(4) で書き戻し、report.json を上書き保存。

使い方:
  python3 tools/inject_probs.py <race-id>          # 注入して report.json を更新
  python3 tools/inject_probs.py <race-id> --dry    # 書き戻さず率と食い違いをプレビュー
終了コード: 0=OK / 1=エラー（report/research 欠落・pace.patterns 無し）。
"""
import sys, os, json, glob, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_race

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_research_scores(race_dir):
    """research-<X>.json 群から scores{no:{X:score}} と conf{no:{X:conf}} を機械集約。
    観点ID X は**ファイル名**から採る（中身の point/observation_point の揺れに依存しない）。"""
    scores, conf = {}, {}
    for path in sorted(glob.glob(os.path.join(race_dir, "research-*.json"))):
        base = os.path.basename(path)
        X = base[len("research-"):-len(".json")].upper()  # research-A.json -> A
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for h in d.get("horses", []) or []:
            no = h.get("no")
            if not isinstance(no, int) or isinstance(no, bool):
                continue
            s = h.get("score")
            if isinstance(s, (int, float)) and not isinstance(s, bool):
                scores.setdefault(no, {})[X] = s
                c = h.get("confidence")
                if c:
                    conf.setdefault(no, {})[X] = c
    return scores, conf


def _compute_draw_adj(report, field_size):
    """bias_note から枠バイアス方向を読み、枠番に応じた draw_adj を返す {no: float}。
    内有利 → 内枠にプラス・外枠にマイナス。外有利 → 逆。フラットなら全馬0。
    ±0.05（最内/最外）のレンジ＝A_early の 10% 程度の補正。"""
    bias = (report.get("pace", {}) or {}).get("bias_note", "") or ""
    direction = 0
    if "内有利" in bias or "内側有利" in bias:
        direction = 1
    elif "外有利" in bias or "外側有利" in bias:
        direction = -1
    if direction == 0:
        return {}
    rank = report.get("rank", []) or []
    gates = [r.get("no") for r in rank if isinstance(r.get("no"), int)]
    if not gates:
        return {}
    n = field_size or len(gates)
    if n <= 1:
        return {}
    adj = {}
    leg_table = (report.get("pace", {}) or {}).get("leg_table", []) or []
    no_to_gate = {}
    for row in leg_table:
        no = row.get("no")
        g = row.get("gate")
        if isinstance(no, int) and g:
            try:
                no_to_gate[no] = int(g)
            except (ValueError, TypeError):
                pass
    if not no_to_gate:
        for r in rank:
            no = r.get("no")
            g = r.get("gate")
            if isinstance(no, int) and g:
                try:
                    no_to_gate[no] = int(g)
                except (ValueError, TypeError):
                    pass
    for no, gate in no_to_gate.items():
        pos = (gate - 1) / max(n - 1, 1)
        adj[no] = round(direction * 0.05 * (1 - 2 * pos), 4)
    return adj


def is_debut(report):
    """新馬戦の判定: meta の debut:true 明示、またはレース名/条件に「新馬」「メイクデビュー」。
    新馬はエンジンを debut プロファイル（A_class base=C/M/F・A_finish素=血統C）で回す（score_race v4.6）。"""
    if report.get("debut") is True:
        return True
    blob = (report.get("race_name") or "") + (report.get("conditions") or "")
    return ("新馬" in blob) or ("メイクデビュー" in blob)


# 地方競馬（NAR）の場 romaji（race-id の開催トークン）。帯広=ばんえいは対象外。
NAR_VENUES = {"monbetsu", "morioka", "mizusawa", "urawa", "funabashi", "ooi", "kawasaki",
              "kanazawa", "kasamatsu", "nagoya", "sonoda", "himeji", "kochi", "saga"}

# obs_coverage（観点欠落の構造化表）用: 観点の読者向けラベルと、seed/決定論ツールで縮退代替が効く観点集合。
OBS_LABEL = {"A": "能力指数・時計", "B": "近走内容", "C": "血統", "D": "コース・馬場適性",
             "E": "展開証拠", "F": "調教・仕上げ", "G": "ローテ・馬体", "H": "当日気配・関係者コメント",
             "I": "リスク要因", "K": "騎手・乗替", "L": "条件実績・リピーター",
             "M": "厩舎新馬型・初戦準備", "N": "クラス格・転入換算"}
SEED_BACKED = set("ABDGIK")


def is_nar(report, race_id=""):
    """地方競馬の判定: report の nar:true 明示、または race-id の開催トークンが NAR 場。
    NAR はエンジンを nar プロファイル（A_class base に観点N=クラス格・転入換算を組込）で回す（score_race v4.7）。"""
    if report.get("nar") is True:
        return True
    parts = (race_id or report.get("race_id") or "").split("-")
    return len(parts) >= 2 and parts[1].lower() in NAR_VENUES


def build_input(report, scores, conf, seed=None):
    """report.json + 集約済み scores から score_race の入力 JSON を組む。
    seed（fetch_racecard 出力）があれば各馬の ten_speed/agari_best/recent/style を score_race に渡す＝
    A_early(序盤の速さ)/A_cruise(位置安定)/A_finish(上がり) を中立0.5でなく実データで作る（v4.1 精緻化）。"""
    pace = report.get("pace", {}) or {}
    style_of = {row.get("no"): row.get("leg_type")
                for row in (pace.get("leg_table") or []) if isinstance(row, dict)}
    seed_of = {h.get("no"): h for h in (seed or {}).get("horses", []) if isinstance(h, dict)}
    draw_adj = _compute_draw_adj(report, report.get("field_size"))
    horses = []
    for r in report.get("rank", []) or []:
        no = r.get("no")
        if not isinstance(no, int) or isinstance(no, bool):
            continue
        s = seed_of.get(no, {})
        horses.append({
            "no": no,
            "name": r.get("horse", str(no)),
            # style は seed の素の脚質("差")を優先・無ければ leg_table の leg_type（装飾は score_race が先頭文字で吸収）
            "style": s.get("style") or style_of.get(no),
            "ten_speed": s.get("ten_speed"),     # A_early の素（速/中/遅）。seed 無→score_race が中立0.5
            "agari_best": s.get("agari_best"),   # A_finish の素（上がり最速の field 相対）
            "recent": s.get("recent") or [],     # A_cruise の素（first_corner/field の位置安定）
            "scores": scores.get(no, {}),
            "conf": conf.get(no, {}),
            "draw_adj": draw_adj.get(no, 0.0),   # 枠バイアス補正（bias_note 由来）
        })
    patterns = [{"id": p.get("id"), "prob": p.get("prob", 0.0),
                 "pace_level": p.get("pace_level", 0.5), "contesters": p.get("contesters", []),
                 "leg_advantage": p.get("leg_advantage") or {}}   # v4.1: 展開項(脚質別有利不利)を率に効かせる
                for p in (pace.get("patterns") or [])]
    data = {"race_id": report.get("race_id", ""), "horses": horses, "patterns": patterns}
    has_N = any("N" in (s or {}) for s in scores.values())
    if is_debut(report):
        data["profile"] = "debut"   # NAR の認定新馬戦も debut 優先（過去走ゼロの構造欠損が先）
    elif report.get("nar") is True or (is_nar(report) and has_N):
        # venue 自動判定だけでは適用しない（旧ハーネスで分析した NAR レース＝research-N 無しの再注入で
        # 率がドリフトするのを防ぐ）。明示 nar:true は N 欠落でも適用（欠落警告が別途出る）。
        data["profile"] = "nar"
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("race_id")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    race_dir = os.path.join(ROOT, "data", "races", args.race_id)
    report_path = os.path.join(race_dir, "report.json")
    if not os.path.exists(report_path):
        print(f"✗ report.json が無い: {report_path}", file=sys.stderr)
        return 1
    report = json.load(open(report_path, encoding="utf-8"))

    scores, conf = load_research_scores(race_dir)
    if not scores:
        print(f"✗ research-*.json から観点スコアが1件も取れない（{race_dir}）", file=sys.stderr)
        return 1

    seed_path = os.path.join(race_dir, "seed.json")
    seed = json.load(open(seed_path, encoding="utf-8")) if os.path.exists(seed_path) else None

    data = build_input(report, scores, conf, seed)
    if not data["patterns"]:
        print("✗ pace.patterns が無い＝率を出せない", file=sys.stderr)
        return 1

    result = score_race.compute(data)
    errs = score_race.self_check(data, result)
    if errs:
        print("⚠ self-check: " + "; ".join(errs), file=sys.stderr)

    win = {h["no"]: h["win_prob"] for h in result["horses"]}
    place = {h["no"]: h["place_prob"] for h in result["horses"]}

    rank = report.get("rank", [])
    # 並びとエンジン複勝率順の食い違い（参考＝engine_check の素。論理が主なので並べ替えはしない）
    eng_order = sorted(win, key=lambda n: -place[n])
    logic_order = [r.get("no") for r in sorted(rank, key=lambda r: r.get("rank_order", 999))]
    disagree = sum(1 for i, no in enumerate(logic_order[:len(eng_order)]) if eng_order[i] != no)

    missing = []
    for r in rank:
        no = r.get("no")
        if no in win:
            r["win_prob"] = round(win[no], 4)
            r["place_prob"] = round(place[no], 4)
        else:
            missing.append(no)

    debut = data.get("profile") == "debut"
    nar = data.get("profile") == "nar"
    print(f"# {args.race_id}  率注入（源=score_race v{result['model_version']}・並びは論理が主"
          f"{'・新馬プロファイル=base C/M/F' if debut else ''}"
          f"{'・NARプロファイル=base N/B/A/C' if nar else ''}）")
    for r in sorted(rank, key=lambda r: r.get("rank_order", 999)):
        no = r.get("no")
        w, pl = r.get("win_prob"), r.get("place_prob")
        if w is not None:
            print(f"  {r.get('mark',''):<2} {no:>2} {r.get('horse',''):<14} 単勝 {w*100:5.1f}%  複勝 {pl*100:5.1f}%")
        else:
            print(f"     {no:>2} {r.get('horse','')} ← 率なし")
    if missing:
        print(f"⚠ 率を入れられない馬(rankにいるがscore入力に無い): {missing}", file=sys.stderr)
    print(f"# 論理の並び vs エンジン複勝率順: 食い違い {disagree}頭"
          f"（並びは論理が主＝率順に並べ替えない。engine_check の素）")

    # ◎とエンジン単勝1位の乖離 → 点検シグナルを report に自動記録（I8: 並びは論理が主＝並べ替えない）。
    # 根拠: コーパス48Rで乖離レースの◎勝率12% vs 一致レース22%（2026-07-12）＝乖離は◎の読み直しの合図。
    AUTO_SIG = "エンジン点検: 率の単勝1位は◎でなく"
    notes = report.get("header_notes") or []
    if logic_order and win:
        top_no = logic_order[0]
        eng_top = max(win, key=lambda n: win[n])
        if top_no is not None and eng_top != top_no:
            name = next((str(r.get("horse", "")) for r in rank if r.get("no") == eng_top), "")
            sig = (f"{AUTO_SIG}{eng_top}番{name}。乖離時は◎の勝ち切りが落ちる傾向＝"
                   f"印確定前に◎の好材料/懸念と展開適合を再検算（並びは論理が主・率で並べ替えはしない）。")
            if not report.get("engine_check"):
                report["engine_check"] = sig
            notes = [n for n in notes if AUTO_SIG not in n] + [sig]
            report["header_notes"] = notes
            print(f"⚠ {sig}")
        else:
            # 再実行で乖離が解消したら自動シグナルだけ掃除（人手の engine_check は触らない）
            if isinstance(report.get("engine_check"), str) and report["engine_check"].startswith(AUTO_SIG):
                report["engine_check"] = None
            cleaned = [n for n in notes if AUTO_SIG not in n]
            if cleaned != notes:
                report["header_notes"] = cleaned

    # 欠落観点の検出 → header_notes に警告付記（D4: 速報モード等で観点が落ちると率の精度が劣化）
    # 新馬は観点セット自体が別（A/B/D/G/L は過去走依存＝構造的に無い）＝期待セットを差し替えて誤警告しない。
    # NAR は既定セット A,B,C,D,E,G,I,K,N（F/H/L は情報が薄く任意追加）＝スコア観点は ABCDGIKN を期待。
    FULL_OBS = set("CFHIKM") if debut else (set("ABCDGIKN") if nar else set("ABCDFGHIKL"))
    used = set(report.get("used_observations", []))
    used_upper = {x.upper() for x in used}
    missing_obs = sorted(FULL_OBS - used_upper)
    # 観点欠落の構造化（obs_coverage）: web §4 が表として描画する（欠落ゼロなら空配列＝表示なし）。
    # SEED_BACKED = seed近走・決定論ツール(risk_flags/weight_adjust)で縮退代替が効く観点。それ以外は代替なし。
    report["obs_coverage"] = [
        {"id": x, "label": OBS_LABEL.get(x, x),
         "status": "縮退" if x in SEED_BACKED else "未取得",
         "fallback": "seedの近走・決定論ツールで代替（読みの確度は低下）" if x in SEED_BACKED else "代替なし"}
        for x in missing_obs]
    if missing_obs:
        warn = f"観点欠落({','.join(missing_obs)}): 率(win_prob/place_prob)は欠落観点を中立値で代替＝参考精度が低下。"
        notes = report.get("header_notes") or []
        if not any("観点欠落" in n for n in notes):
            notes.append(warn)
            report["header_notes"] = notes
            print(f"⚠ {warn}")
    if debut:
        warn = "新馬プロファイル(v4.6): 率は C/M/F 組替の理論値で新馬コーパス較正ゼロ＝参考精度は通常より更に低い。"
        notes = report.get("header_notes") or []
        if not any("新馬プロファイル" in n for n in notes):
            notes.append(warn)
            report["header_notes"] = notes
            print(f"⚠ {warn}")
    if nar:
        warn = "NARプロファイル(v4.7): 率は N(クラス格)組込の理論値でNARコーパス較正ゼロ＝参考精度は通常より更に低い。"
        notes = report.get("header_notes") or []
        if not any("NARプロファイル" in n for n in notes):
            notes.append(warn)
            report["header_notes"] = notes
            print(f"⚠ {warn}")

    if args.dry:
        print("（--dry: 書き戻さない）")
        return 0
    json.dump(report, open(report_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✓ {os.path.relpath(report_path, ROOT)} に win_prob/place_prob を注入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
