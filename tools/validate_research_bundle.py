#!/usr/bin/env python3
"""research バンドル検証器（依存ゼロ）。

report.json の `used_observations` と、同ディレクトリの実 `research-<観点>.json`
の**対応・必須充足**を検証する。スキーマ検証器 `validate_report.py` は report 単体しか
見ず、used_observations と研究artifact の対応を**検証しない**ため、観点が欠落したまま
（合成器が workflow 返り値だけで report を書けてしまい）成果物が出る経路を塞ぐ。

検出する穴（実例: 20260617-kawasaki-11=B欠落・E空・I空 / 20260621-tokyo-11=A欠落→復元）:
  - used_observations に挙がっているのに research-<観点>.json が**保存されていない**（ERROR）
  - 研究artifact の馬番集合が **report.rank の全馬と不一致**（ERROR）: 件数でなく集合一致で見るため、
    同数でも**重複・別馬混入で1頭欠ける**ケースを捕捉（非E は `horses[].no`、E は `legs[].no`）。
    rank が全頭そろわない時のみ件数（`< field_size`）に退避。行が list でない壊れた artifact も error。
  - **市場語の混入**（ERROR・I1）: research JSON の文字列に「人気・オッズ・配当・払戻」が残っていないか走査
    （report に出なくても証拠JSONに残れば I1 違反）。

使い方:
  python3 tools/validate_research_bundle.py <race-id>
  python3 tools/validate_research_bundle.py data/races/<id>/report.json
  python3 tools/validate_research_bundle.py --all

終了コード: 0=OK / 1=エラーあり。analyze-race STEP5 で validate_report.py と並べて必須ゲートにする。
"""
import sys, os, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# I1: 市場・他人の予想は research artifact にも残してはいけない（report に出なくても証拠JSONに残れば違反）。
# オッズ/人気/配当＋予想印/専門紙/英語odds,market。URL(http…)は引用先＝サイト構造で誤検出するため走査から除外。
I1_FORBIDDEN_TERMS = ("人気", "オッズ", "配当", "払戻", "払い戻", "予想印", "専門紙", "odds", "market")


def scan_market(obj, obs, errors):
    """research の全文字列を走査して市場・予想語を I1 違反として記録（URL は除外）。"""
    if isinstance(obj, str):
        if obj.startswith("http"):
            return
        hit = [t for t in I1_FORBIDDEN_TERMS if t in obj]
        if hit:
            errors.append(f"観点 {obs}: I1違反 市場・予想語 {hit} を含む → {obj[:80]!r}")
    elif isinstance(obj, list):
        for x in obj:
            scan_market(x, obs, errors)
    elif isinstance(obj, dict):
        for x in obj.values():
            scan_market(x, obs, errors)


def check_bundle(report_path):
    """1つの report.json に対応する research バンドルを検証。返り値 (errors, warnings)。"""
    errors, warnings = [], []
    race_dir = os.path.dirname(os.path.abspath(report_path))
    try:
        d = json.load(open(report_path, encoding="utf-8"))
    except Exception as e:
        return [f"report.json 読込失敗 — {e}"], []

    used = d.get("used_observations")
    if not isinstance(used, list) or not used:
        errors.append("used_observations が無い/空 — 観点の対応を検証できない")
        return errors, warnings
    field_size = d.get("field_size")

    def _is_int(x):
        return isinstance(x, int) and not isinstance(x, bool)

    # 期待する全馬の馬番集合（report の rank が正本＝§3全馬）。全頭そろっていれば「件数」でなく「集合一致」で検証＝
    # 同数でも重複や別馬混入で1頭欠けるケースを捕捉する。rank が全頭でなければ集合照合は諦め件数に退避（report側で別途error）。
    expected = set(row.get("no") for row in d.get("rank", [])
                   if isinstance(row, dict) and _is_int(row.get("no")))
    if not (isinstance(field_size, int) and len(expected) == field_size):
        expected = None

    # 実在する research-<X>.json を収集
    present = {}
    for p in glob.glob(os.path.join(race_dir, "research-*.json")):
        oid = os.path.basename(p).split("-", 1)[1].rsplit(".", 1)[0]
        present[oid] = p

    for obs in used:
        path = present.get(obs)
        if path is None:
            errors.append(
                f"観点 {obs}: used_observations にあるのに research-{obs}.json が無い"
                f"（合成は返り値で通っても artifact 欠落＝欠落無検知の経路）"
            )
            continue
        # 全頭カバー＝必須充足（部分欠損/重複/別馬混入は error）。E は legs、それ以外は horses。
        try:
            r = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            errors.append(f"観点 {obs}: research-{obs}.json 読込失敗 — {e}")
            continue
        scan_market(r, obs, errors)   # I1: 市場語が artifact に残っていないか
        key = "legs" if obs == "E" else "horses"
        rows = r.get(key)
        # 壊れた artifact は validator を落とさず error にして次へ（CI/レビュー向き）
        if not isinstance(rows, list):
            errors.append(f"観点 {obs}: research-{obs}.json の {key} が list でない（{type(rows).__name__}）＝壊れた artifact")
            continue
        # 各行 dict・no int・重複なし
        nos = set()
        for j, x in enumerate(rows):
            if not isinstance(x, dict):
                errors.append(f"観点 {obs}: {key}[{j}] が dict でない（{type(x).__name__}）")
                continue
            no = x.get("no")
            if not _is_int(no):
                errors.append(f"観点 {obs}: {key}[{j}].no が int でない（{no!r}）")
                continue
            if no in nos:
                errors.append(f"観点 {obs}: {key} に馬番 {no} が重複")
            nos.add(no)
        # 行数 = field_size（N+1 行・余計な行も捕捉）
        if isinstance(field_size, int) and len(rows) != field_size:
            errors.append(f"観点 {obs}: {key} {len(rows)}行 が field_size {field_size} と不一致")
        # 馬番集合 = report.rank の全馬（同数でも欠け/別馬を顕在化）
        if expected is not None and nos != expected:
            miss = sorted(n for n in expected if n not in nos)
            extra = sorted(n for n in nos if n not in expected)
            seg = []
            if miss:
                seg.append(f"欠け={miss}")
            if extra:
                seg.append(f"余分/別馬={extra}")
            errors.append(f"観点 {obs}: {key} の馬番集合が全馬と不一致 {' '.join(seg)}")
    return errors, warnings


def run(path):
    errors, warnings = check_bundle(path)
    name = os.path.relpath(path, ROOT)
    if errors:
        print(f"✗ {name}: {len(errors)} エラー")
        for e in errors:
            print(f"    [E] {e}")
    for w in warnings:
        print(f"    [W] {w}")
    if not errors:
        print(f"✓ {name}  (research バンドル充足{f' / 警告 {len(warnings)}' if warnings else ''})")
    return not errors


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
