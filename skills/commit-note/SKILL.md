---
name: commit-note
description: task / feature branchへの通常の追加commit、またはユーザーが明示したcommitについて、conventional commits形式のmessageとcommit前後の短い記録を作る。
---

# Commit Note

## 使う場面

- `AGENTS.md`のauthority内でtask / feature branchへ通常の追加commitを行う
- ユーザーがcommitを明示的に依頼した
- 変更が 1 つの論理単位としてまとまっている

## 手順

1. `git status --short` で対象変更を確認する
2. 現在branchと`AGENTS.md`のauthority境界を確認する
3. 対象pathまたはhunkだけをstageし、既存のstaged変更と無関係変更を除外する
4. conventional commits 形式の message を作る
5. commit後にhash、summary、validationをread-backして報告する

## message

```text
<type>(<scope>): <summary>

<body if needed>
```

## ルール

- `git push` は明示依頼がある場合だけ行う
- default / main / protected branchへのcommitは明示依頼がある場合だけ行う
- 履歴改変は明示依頼がある場合だけ行う
- ユーザー由来の変更を混ぜない
