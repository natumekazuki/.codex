---
name: commit-note
description: conventional commits 形式の commit message と、commit 前後の短い記録を作る。
---

# Commit Note

## 使う場面

- ユーザーが commit を依頼した
- 変更が 1 つの論理単位としてまとまっている

## 手順

1. `git status --short` で対象変更を確認する
2. 無関係変更を commit 対象から除外する
3. conventional commits 形式の message を作る
4. commit 後に hash、summary、validation を報告する

## message

```text
<type>(<scope>): <summary>

<body if needed>
```

## ルール

- `git push` は明示依頼がある場合だけ行う
- 履歴改変は明示依頼がある場合だけ行う
- ユーザー由来の変更を混ぜない
