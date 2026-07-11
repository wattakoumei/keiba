#!/usr/bin/env python3
"""data/screening/<date>-<venue>.json スキーマ検証器（依存ゼロ）。

screening JSON は screen-card 選別ハーネスの出力（schema は
.claude/skills/screen-card/references/screening-model.md §6）。keiba-web の
日付ページ（dates/[date].astro）が build 時に直読みするため、型崩れは
**CI ビルドの実行時クラッシュ**になる（例: x_axis が文字列だと
String.prototype.anchor に化けて `.join` で落ちる＝2026-07-11 の CI 障害）。
本検証器は書込直後と CI ビルド前のゲートとして、
  - トップレベル（date/venue/races）と各レースの型
  - x_axis はオブジェクト or null（文字列は禁止）・anchor は配列
  - quadrant に絵文字を埋めない（表示側が付ける）
  - キーの whitelist（x_conf/dango/gap 等のドリフト別名を検知）
を確認する。odds-*.json（fetch_odds.py 出力・別スキーマ）は対象外。

使い方:
  python3 tools/validate_screening.py data/screening/20260711-kokura.json
  python3 tools/validate_screening.py --all       # data/screening/*.json 一括（odds-* 除く）
  python3 tools/validate_screening.py --self-check

終了コード: 0=OK / 1=エラーあり。
"""
import sys, os, json, glob, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREEN_DIR = os.path.join(ROOT, "data", "screening")

# 表示側（quadMeta）が絵文字を付けるので、データ側に埋めるのは二重化＝禁止
EMOJI_RE = re.compile(r"[🟥🟦🎯✖⬜🔺⭐★]")
COND_RAGE = {"強", "中", "弱", None}
DANGO_TIER = {"割れ", "中", "収束", None}
DATE_RE = re.compile(r"^\d{8}$")
FNAME_RE = re.compile(r"^(\d{8})-([a-z]+)\.json$")

# 各レースの許可キー（screening-model.md §6 ＋ screen_conditions.py fill の補完キー）。
# ドリフト別名の対応: x_conf→x_axis.confidence / dango→dango_tier / gap→x_axis.market_divergence
RACE_KEYS = {
    "r", "race_id", "post_time", "condition",
    "surface", "distance", "headcount", "class", "race_type", "race_name",
    "cond_rage", "cond_flags", "dango_tier", "dango_signals",
    "x_axis", "quadrant", "score", "cut_reason", "error",
}
XAXIS_KEYS = {
    "anchor", "confidence", "market_divergence",
    "field_legs", "concern", "style_counts", "reason", "top_scores", "top_group",
}
DRIFT_HINT = {
    "x_conf": "x_axis.confidence へ",
    "dango": "dango_tier へ",
    "gap": "x_axis.market_divergence へ",
}


def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def check_str_or_none(val, path, errors):
    if val is not None and not isinstance(val, str):
        errors.append(f"{path}: str|null 必須（{type(val).__name__}）")


def check_race(r, path, errors):
    if not isinstance(r, dict):
        errors.append(f"{path}: レースは object 必須（{type(r).__name__}）")
        return
    for k in r:
        if k not in RACE_KEYS:
            hint = f"（{DRIFT_HINT[k]}）" if k in DRIFT_HINT else ""
            errors.append(f"{path}.{k}: 未知キー＝スキーマドリフト{hint}。正本は screening-model.md §6")
    if not is_int(r.get("r")):
        errors.append(f"{path}.r: int 必須（{type(r.get('r')).__name__}）")
    for k in ("surface", "class", "race_type", "race_name", "post_time",
              "condition", "cut_reason", "race_id", "error", "cond_rage"):
        if k in r:
            check_str_or_none(r[k], f"{path}.{k}", errors)
    for k in ("distance", "headcount"):
        if r.get(k) is not None and not is_int(r[k]):
            errors.append(f"{path}.{k}: int|null 必須（{type(r[k]).__name__}）")
    if r.get("cond_rage") not in COND_RAGE:
        errors.append(f"{path}.cond_rage: {sorted(x for x in COND_RAGE if x)}|null のみ（{r.get('cond_rage')!r}）")
    if r.get("dango_tier") not in DANGO_TIER:
        errors.append(f"{path}.dango_tier: {sorted(x for x in DANGO_TIER if x)}|null のみ（{r.get('dango_tier')!r}）")
    for k in ("cond_flags", "dango_signals"):
        v = r.get(k)
        if v is not None and (not isinstance(v, list) or any(not isinstance(x, str) for x in v)):
            errors.append(f"{path}.{k}: str[]|null 必須（{v!r}）")
    if r.get("score") is not None and isinstance(r["score"], bool) or not isinstance(r.get("score"), (int, float, type(None))):
        errors.append(f"{path}.score: number|null 必須（{type(r.get('score')).__name__}）")
    q = r.get("quadrant")
    if not isinstance(q, str):
        errors.append(f"{path}.quadrant: str 必須（{type(q).__name__}）")
    elif EMOJI_RE.search(q):
        errors.append(f"{path}.quadrant: 絵文字を埋めない（表示側が付ける）→ {q!r}")
    # x_axis: object|null。文字列は String.prototype.anchor 化で web build が落ちる＝最重要チェック
    xa = r.get("x_axis")
    if xa is not None and not isinstance(xa, dict):
        errors.append(f"{path}.x_axis: object|null 必須（{type(xa).__name__}: {xa!r}）")
    elif isinstance(xa, dict):
        for k in xa:
            if k not in XAXIS_KEYS:
                errors.append(f"{path}.x_axis.{k}: 未知キー＝スキーマドリフト。正本は screening-model.md §6")
        a = xa.get("anchor")
        if a is not None and not isinstance(a, list):
            errors.append(f"{path}.x_axis.anchor: 配列|null 必須（{type(a).__name__}: {a!r}）")
        for k in ("confidence", "market_divergence", "field_legs", "concern", "reason"):
            if k in xa:
                check_str_or_none(xa[k], f"{path}.x_axis.{k}", errors)


def validate_card(data, fname=None):
    """1カード（dict）を検証してエラー文字列のリストを返す。"""
    errors = []
    if not isinstance(data, dict):
        return [f"$: トップレベルは object 必須（{type(data).__name__}）"]
    date = data.get("date")
    if not isinstance(date, str) or not DATE_RE.match(date.replace("-", "")):
        errors.append(f"$.date: YYYYMMDD 文字列必須（{date!r}）")
    if not isinstance(data.get("venue"), str):
        errors.append(f"$.venue: str 必須（{data.get('venue')!r}）")
    if fname:
        m = FNAME_RE.match(fname)
        if m and isinstance(date, str) and (m.group(1) != date.replace("-", "") or m.group(2) != data.get("venue")):
            errors.append(f"$: ファイル名 {fname} と date/venue（{date}/{data.get('venue')}）が不一致（日付ページの突合キー）")
    races = data.get("races")
    if not isinstance(races, list):
        errors.append(f"$.races: 配列必須（{type(races).__name__}）")
    else:
        for i, r in enumerate(races):
            check_race(r, f"$.races[{i}]", errors)
    return errors


def validate_file(path):
    fname = os.path.basename(path)
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return [f"$: JSON パース不能: {e}"]
    return validate_card(data, fname)


def self_check():
    good = {"date": "20260711", "venue": "kokura", "place": "10", "races": [
        {"r": 11, "surface": "ダ", "distance": 1000, "headcount": 11,
         "cond_rage": "中", "cond_flags": ["小倉開催"], "dango_tier": "中", "dango_signals": [],
         "x_axis": {"anchor": ["8", "11"], "confidence": "上位ボックス", "market_divergence": None},
         "quadrant": "鉄板コツコツ", "score": 2, "post_time": "15:30"}]}
    assert validate_card(good, "20260711-kokura.json") == [], validate_card(good, "20260711-kokura.json")
    # 2026-07-11 CI 障害の再現形: 文字列 x_axis・絵文字象限・ドリフト別名
    bad = {"date": "20260711", "venue": "kokura", "races": [
        {"r": 11, "x_axis": "⑧⑪の2枚", "quadrant": "🟦鉄板コツコツ",
         "x_conf": "上位", "dango": "中", "gap": "ズレ小", "cond_rage": "中", "score": 2}]}
    errs = validate_card(bad)
    for frag in ("x_axis: object|null", "絵文字", "x_conf", "dango", "gap"):
        assert any(frag in e for e in errs), (frag, errs)
    assert any("不一致" in e for e in validate_card(good, "20260712-kokura.json"))
    print("self-check OK")


def main(argv):
    if "--self-check" in argv:
        self_check()
        return 0
    if "--all" in argv:
        paths = [p for p in sorted(glob.glob(os.path.join(SCREEN_DIR, "*.json")))
                 if not os.path.basename(p).startswith("odds-")]
    else:
        paths = [a for a in argv if not a.startswith("-")]
        if not paths:
            print(__doc__)
            return 1
    ok = True
    for p in paths:
        errs = validate_file(p)
        rel = os.path.relpath(p, ROOT)
        if errs:
            ok = False
            print(f"✗ {rel}: {len(errs)} エラー")
            for e in errs:
                print(f"    [E] {e}")
        else:
            print(f"✓ {rel}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
