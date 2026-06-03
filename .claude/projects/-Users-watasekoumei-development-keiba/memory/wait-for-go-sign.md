---
name: wait-for-go-sign
description: Wait for the user's explicit OK before editing harness/project files
metadata:
  type: feedback
---

ハーネスやプロジェクトのファイルを編集する前に、ユーザーの明示的なgoサインを待つ。提案を出して「進めますね」と書いただけで実装に進むのは先走り。

**Why:** 2026-06-03、keiba ハーネスの v2.0 再設計（着順予想エンジン化）で、合意を取らずに6ファイルを書き換えたところ「goサインを出さずに変更を行ったようだが」と指摘された。しかもその後ユーザーは設計自体に疑問を呈した＝走り出す前に止まるべきだった。

**How to apply:** 設計や方針の変更は、案を提示して明示的な承認（「やって」「OK」等）を得てからファイルを触る。読み取り・調査は先行してよい。確認なしに進めてよいのは些末で可逆な変更のみ。
