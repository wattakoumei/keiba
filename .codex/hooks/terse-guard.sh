#!/usr/bin/env bash
# Stop hook: 散文が冗長(本文12行以上)なら exit 2 で差し戻す。表・箇条書きは許可(表中心方針と整合)＝計上しない。
# 無限ループ防止: stop_hook_active のとき(=既に1度差し戻し済み)はブロックしない=1ターン1回まで。
set -u
command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
active=$(printf '%s' "$input" | jq -r '.stop_hook_active // false')
[ "$active" = "true" ] && exit 0

tp=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
[ -n "$tp" ] && [ -f "$tp" ] || exit 0

text=$(jq -rs '[.[] | select(.type=="assistant")] | last
  | (.message.content // []) | map(select(.type=="text") | .text) | join("\n")' "$tp" 2>/dev/null)
[ -n "$text" ] || exit 0

# 表(|始まり)・箇条書き(-/*/数字.)・見出し・引用の行は除き、散文の実行数だけ数える。
lines=$(printf '%s\n' "$text" | grep -vE '^\s*([|>#*+-]|[0-9]+[.)])' | grep -cE '\S')

if [ "$lines" -ge 12 ]; then
  echo "簡潔スタイル違反: 散文が冗長。結論を1行目に・表/箇条書きで圧縮しろ。" >&2
  exit 2
fi
exit 0
