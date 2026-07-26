---
name: task-brief
description: 要求が曖昧または少し大きいとき、実装前に goal、target behavior / failure mode、scope、canonical anchors、done、risksを短く整理する。
---

# Task Brief

## 使う場面

- 要求が複数の変更を含む
- どこまでやるかを短く確認したい
- plan ファイルを作るほどではないが、作業の輪郭を固定したい

## 出力

```text
Goal:
Target behavior / failure mode:
Scope:
Out of scope:
Canonical anchors: <source / executable contract / accepted ADR, or none>
Done when:
Risks:
```

## ルール

- 7から10行に収める
- source、実行可能な契約、accepted ADRが既に分かる場合だけcanonical anchorを示し、briefへ内容を複製しない
- ADRまたはarchitecture文書の要否が未確定でも、briefのためだけに文書を作らない。実装中のknowledge placement gateで判定する
- 実装を止める質問がない限り、brief 後にそのまま作業へ進む
- brief は原則として会話内に置き、複数 session で参照する必要がない限り repo 文書にしない
- repo 外パスや絶対パスを書かない
