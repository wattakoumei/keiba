#!/usr/bin/env bash
# Stop hook: 最終assistantメッセージが 6行以上 or markdown表(| を含む行 >=2) なら exit 2 で差し戻す。
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

lines=$(printf '%s\n' "$text" | wc -l | tr -d ' ')
pipes=$(printf '%s\n' "$text" | grep -c '|')

if [ "$lines" -ge 6 ] || [ "$pipes" -ge 2 ]; then
  echo "簡潔スタイル違反: 5行以内・表禁止。結論を1行目に書き直せ。" >&2
  exit 2
fi
exit 0
