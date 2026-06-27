#!/usr/bin/env python3
"""report.json スキーマ検証器（依存ゼロ）。

report.json は analyze-race が出力する構造化正本（§0-§4）。本検証器は
  - スキーマ（必須キー・型・参照整合）
  - 不変則 I2（% / ％ をレポートに出さない）= 文字列フィールドに百分率記号が無いこと
を確認する。analyze-race の書込直後・Astro ビルド前のゲートに使う。

使い方:
  python3 tools/validate_report.py data/races/<race-id>/report.json
  python3 tools/validate_report.py <race-id>          # data/races/<id>/report.json を解決
  python3 tools/validate_report.py --all              # data/races/*/report.json を一括

終了コード: 0=OK / 1=エラーあり。
"""
import sys, os, json, glob, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKS = {"◎", "◯", "○", "▲", "△", "×", "注", "—"}     # rank.mark（無印は全角—に統一。円は◯/○両許容）
FIT_SYMBOLS = {"◎", "○", "△"}                              # pattern_fit の符号
LEG_KEYS = {"逃げ", "先行", "差し", "追込"}                  # leg_advantage キー
FLOW_KEYS = {"early", "mid", "late", "result"}
RACE_ID_RE = re.compile(r"^\d{8}-[a-z]+-\d{2}$")
# I2: 文字列に出てはいけない百分率記号。prob/pace_level/win_prob/place_prob は数値Fなので対象外
# （率は数値で持ち web が ×100 して%付与＝I2 の率2カラム限定例外。文字列への%埋め込みは引き続き禁止）。
PCT_RE = re.compile(r"[%％]")
# I1: 市場・他人の予想は証拠にもログにも一切出さない（オッズ/人気/配当＋予想印/専門紙/英語odds,market）。
# 単勝/複勝は的中率の意味で使うため対象外。URL(http…)は引用先＝サイト構造に odds/market を含みうるので走査から除外。
I1_FORBIDDEN_TERMS = ("人気", "オッズ", "配当", "払戻", "払い戻", "予想印", "専門紙", "odds", "market")


class V:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, path, msg):
        self.errors.append(f"{path}: {msg}")

    def warn(self, path, msg):
        self.warnings.append(f"{path}: {msg}")

    def req(self, obj, key, path, typ=None):
        if not isinstance(obj, dict) or key not in obj:
            self.err(path, f"必須キー '{key}' が無い")
            return None
        val = obj[key]
        if typ is not None and not isinstance(val, typ):
            self.err(f"{path}.{key}", f"型が {typ.__name__} でない（{type(val).__name__}）")
        return val


def is_int(x):
    """bool を除く int。馬番・rank_order など整数フィールドの型ガード（"1" 文字列混入を弾く）。"""
    return isinstance(x, int) and not isinstance(x, bool)


def check_int_list(arr, path, v: V):
    """馬番配列が list かつ各要素 int であることを検証（非list/非int要素をエラー）。"""
    if not isinstance(arr, list):
        v.err(path, f"int[] 必須（list でない: {type(arr).__name__}）")
        return
    bad = [x for x in arr if not is_int(x)]
    if bad:
        v.err(path, f"馬番配列は int 要素必須。非int: {bad!r}")


def scan_pct(obj, path, v: V):
    """全文字列を走査して % / ％（I2）と市場語（I1）を違反として記録。"""
    if isinstance(obj, str):
        if PCT_RE.search(obj):
            v.err(path, f"I2違反: 百分率記号を含む → {obj!r}")
        if not obj.startswith("http"):   # URL(引用先)は走査しない＝odds/market を含むサイト構造の誤検出回避
            hit = [t for t in I1_FORBIDDEN_TERMS if t in obj]
            if hit:
                v.err(path, f"I1違反: 市場・予想語 {hit} を含む（オッズ・人気・他人の予想は証拠にもログにも使わない）→ {obj!r}")
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            scan_pct(x, f"{path}[{i}]", v)
    elif isinstance(obj, dict):
        for k, val in obj.items():
            scan_pct(val, f"{path}.{k}", v)


def validate(d, v: V):
    # --- meta ---
    rid = v.req(d, "race_id", "$", str)
    if rid and not RACE_ID_RE.match(rid):
        v.err("$.race_id", f"形式は YYYYMMDD-開催-RR（2桁0埋め）。実際: {rid!r}")
    v.req(d, "race_name", "$", str)
    v.req(d, "date", "$", str)
    v.req(d, "field_size", "$", int)
    course = v.req(d, "course", "$", dict)
    if isinstance(course, dict):
        for k in ("track", "surface", "distance"):
            v.req(course, k, "$.course")
    for k in ("model_version", "pivot"):
        v.req(d, k, "$", str)
    v.req(d, "used_observations", "$", list)
    v.req(d, "header_notes", "$", list)

    # --- §0 day_board ---
    db = v.req(d, "day_board", "$", dict)
    if isinstance(db, dict):
        v.req(db, "reference_races", "$.day_board", list)
        v.req(db, "paddock_watch", "$.day_board", list)
        v.req(db, "other_unknowns", "$.day_board", list)

    # --- §2 pace ---
    pace = v.req(d, "pace", "$", dict)
    pat_ids = set()
    leg_nos = set()
    if isinstance(pace, dict):
        leg_table = v.req(pace, "leg_table", "$.pace", list)
        if isinstance(leg_table, list):
            for i, row in enumerate(leg_table):
                p = f"$.pace.leg_table[{i}]"
                for k in ("no", "horse", "leg_type"):
                    v.req(row, k, p)
                if isinstance(row, dict) and "no" in row:
                    if not is_int(row["no"]):
                        v.err(f"{p}.no", f"馬番は int 必須。実際: {row['no']!r}")
                    if row["no"] in leg_nos:
                        v.err(p, f"馬番 {row['no']} が脚質表に重複")
                    leg_nos.add(row.get("no"))
            if isinstance(d.get("field_size"), int) and len(leg_nos) != d["field_size"]:
                v.err("$.pace.leg_table", f"全頭カバー必須: 脚質表 {len(leg_nos)}頭 が field_size {d['field_size']} と不一致（§2-1も全馬=output-template）")
        patterns = v.req(pace, "patterns", "$.pace", list)
        if isinstance(patterns, list):
            if len(patterns) < 2:
                v.err("$.pace.patterns", f"複数パターン必須=I5（単一に潰さない）。実際: {len(patterns)}個")
            for i, pat in enumerate(patterns):
                p = f"$.pace.patterns[{i}]"
                pid = v.req(pat, "id", p)
                if pid:
                    pat_ids.add(pid)
                for k in ("name", "tier", "trigger", "bias"):
                    v.req(pat, k, p, str)
                pl = v.req(pat, "pace_level", p)
                if isinstance(pl, (int, float)) and not (0.0 <= pl <= 1.0):
                    v.err(f"{p}.pace_level", f"0..1 の範囲外: {pl}")
                la = v.req(pat, "leg_advantage", p, dict)
                if isinstance(la, dict):
                    bad = set(la) - LEG_KEYS
                    if bad:
                        v.warn(f"{p}.leg_advantage", f"想定外キー: {bad}（{LEG_KEYS} を推奨）")
                flow = v.req(pat, "phase_flow", p, dict)
                if isinstance(flow, dict):
                    miss = FLOW_KEYS - set(flow)
                    if miss:
                        v.err(f"{p}.phase_flow", f"段階フローのキー不足: {miss}")
                for k in ("formation_head", "formation_last_corner", "risers", "sinkers"):
                    v.req(pat, k, p, list)
                # 馬番配列の要素型（"1" 文字列混入が後段の集合一致/投影を壊すのを防ぐ）
                for k in ("formation_head", "formation_last_corner", "risers", "sinkers", "contesters"):
                    if k in pat:
                        check_int_list(pat[k], f"{p}.{k}", v)
        # box_reverse の pattern 参照整合＋馬番配列の要素型
        box = pace.get("box_reverse")
        if isinstance(box, list):
            for i, b in enumerate(box):
                bp = b.get("pattern") if isinstance(b, dict) else None
                if bp and pat_ids and bp not in pat_ids:
                    v.err(f"$.pace.box_reverse[{i}]", f"未知のパターン id: {bp!r}（定義: {sorted(pat_ids)}）")
                if isinstance(b, dict):
                    for k in ("center", "inside", "spot", "drop"):
                        if k in b:
                            check_int_list(b[k], f"$.pace.box_reverse[{i}].{k}", v)
        # pace_factors（展開トリガー早見・任意）= 来そうな展開の判断材料。あれば形を検証
        pf = pace.get("pace_factors")
        if pf is not None:
            if not isinstance(pf, list):
                v.err("$.pace.pace_factors", f"型が list でない（{type(pf).__name__}）")
            else:
                for i, f in enumerate(pf):
                    fp = f"$.pace.pace_factors[{i}]"
                    for k in ("factor", "reads", "day_check"):
                        v.req(f, k, fp, str)

    # --- §3 rank ---
    rank = v.req(d, "rank", "$", list)
    if isinstance(rank, list):
        if isinstance(d.get("field_size"), int) and len(rank) != d["field_size"]:
            v.err("$.rank", f"全頭カバー必須: rank {len(rank)}頭 が field_size {d['field_size']} と不一致（無印馬も省かない=output-template）")
        # win_prob/place_prob = 率2カラムの源(score_race.py 注入・I8)。過去レース(v5.0以前)には無い＝
        # 「1頭でも持てば全頭必須」で部分欠損(注入漏れ)だけ弾き、全頭無しは旧形式としてスルー（--all 回帰を壊さない）。
        has_prob = any(isinstance(r, dict) and ("win_prob" in r or "place_prob" in r) for r in rank)
        orders, nos = [], set()
        for i, r in enumerate(rank):
            p = f"$.rank[{i}]"
            for k in ("no", "horse", "mark", "rank_order", "leg_type", "pace_sensitivity"):
                v.req(r, k, p)
            if isinstance(r, dict):
                if has_prob:
                    for pk in ("win_prob", "place_prob"):
                        if pk not in r:
                            v.err(p, f"率2カラム必須(I8): '{pk}' が無い（1頭でも持つなら全頭必須＝score_race.py 注入漏れ）")
                        elif not isinstance(r[pk], (int, float)) or isinstance(r[pk], bool):
                            v.err(f"{p}.{pk}", f"率は数値(0..1)必須。実際: {r[pk]!r}")
                        elif not (0.0 <= r[pk] <= 1.0):
                            v.err(f"{p}.{pk}", f"率が 0..1 の範囲外: {r[pk]}")
                if r.get("mark") not in MARKS:
                    v.err(f"{p}.mark", f"印が許可集合外: {r.get('mark')!r}（{MARKS}）")
                if "rank_order" in r:
                    # int 必須（bool 除外）。型不正を sorted() のクラッシュでなく明示エラーに寄せる
                    if isinstance(r["rank_order"], int) and not isinstance(r["rank_order"], bool):
                        orders.append(r["rank_order"])
                    else:
                        v.err(f"{p}.rank_order", f"int 必須（順位相関の採点正本）。実際: {r['rank_order']!r}")
                if not is_int(r.get("no")):
                    v.err(f"{p}.no", f"馬番は int 必須。実際: {r.get('no')!r}")
                if r.get("no") in nos:
                    v.err(p, f"馬番 {r.get('no')} が重複")
                nos.add(r.get("no"))
                fit = r.get("pattern_fit", {})
                if isinstance(fit, dict):
                    for fid, sym in fit.items():
                        if pat_ids and fid not in pat_ids:
                            v.err(f"{p}.pattern_fit", f"未知パターン id: {fid!r}")
                        if sym not in FIT_SYMBOLS:
                            v.err(f"{p}.pattern_fit.{fid}", f"符号が ◎/○/△ 以外: {sym!r}")
                for kk in ("pros", "cons"):
                    arr = r.get(kk, [])
                    if isinstance(arr, list):
                        for j, it in enumerate(arr):
                            if not (isinstance(it, dict) and "tag" in it and "note" in it):
                                v.err(f"{p}.{kk}[{j}]", "要素は {tag, note} であること")
        if orders and sorted(orders) != list(range(1, len(orders) + 1)):
            v.err("$.rank", f"rank_order が 1..N の連番でない（重複/欠番＝順位相関の採点正本が破損）: {sorted(orders)}")
        # §2-1 脚質表と §3 着順表は同じ全馬集合であること（どちらかに欠落馬が混ざらない）
        if leg_nos and nos and leg_nos != nos:
            v.err("$.rank", f"脚質表(§2-1)と着順表(§3)の馬番集合が不一致: 脚質表のみ={sorted(leg_nos - nos)} / 着順表のみ={sorted(nos - leg_nos)}")

    # --- §4 ---
    v.req(d, "data_confidence", "$", list)

    # --- I2: % 全面禁止 ---
    scan_pct(d, "$", v)


def run(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(f"✗ {path}: JSON 読込失敗 — {e}")
        return False
    v = V()
    validate(d, v)
    name = os.path.relpath(path, ROOT)
    if v.errors:
        print(f"✗ {name}: {len(v.errors)} エラー")
        for e in v.errors:
            print(f"    [E] {e}")
    if v.warnings:
        for w in v.warnings:
            print(f"    [W] {w}")
    if not v.errors:
        rid = d.get("race_id", "?")
        n = len(d.get("rank", []))
        pats = [p.get("id") for p in d.get("pace", {}).get("patterns", [])]
        print(f"✓ {name}  ({rid} / rank {n}頭 / patterns {pats})"
              + (f"  [警告 {len(v.warnings)}]" if v.warnings else ""))
    return not v.errors


def resolve(arg):
    if arg.endswith(".json") and os.path.exists(arg):
        return [arg]
    cand = os.path.join(ROOT, "data", "races", arg, "report.json")
    if os.path.exists(cand):
        return [cand]
    print(f"見つからない: {arg}")
    return []


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--all":
        paths = sorted(glob.glob(os.path.join(ROOT, "data", "races", "*", "report.json")))
        if not paths:
            print("report.json が1件も無い")
            return 1
    else:
        paths = []
        for a in argv:
            paths += resolve(a)
        if not paths:
            return 1
    oks = [run(p) for p in paths]   # 短絡させず全件検査
    return 0 if all(oks) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
