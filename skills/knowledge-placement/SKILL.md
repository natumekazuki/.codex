---
name: knowledge-placement
description: 設計情報を source、test、type、schema、static check、code comment、ADR、全体設計文書のどこへ置くか判定する。ADR該当性、複数subsystem / process / repo / 外部serviceへ波及する非局所設計、コードから復元できない情報、既存設計書の縮小・廃止を検討するときに使う。
---

# Knowledge Placement

## 原則

配置規則とADR / architecture documentの条件は`AGENTS.md`の「Source of Truth and Knowledge Placement」を正本とする。このSkillは候補情報を分類し、適用先と不要なartifactを判定する手順だけを担当する。

## 手順

1. 残す情報を、current implementation、executable expectation、local rationale、decision rationale、cross-cutting context に分ける
2. source、test、type、schema、static check で表現できる情報を文書候補から除く
3. 一つの code location の近くで理解できる理由は comment に置く
4. `AGENTS.md`のADR gateを適用する
5. `AGENTS.md`のarchitecture document gateを適用し、全条件を満たす情報だけ恒久文書へ残す
6. 既存文書を更新する場合は、実装の写経を削り、非実行情報と実行可能な正本への pointer だけに縮める
7. 文書不要なら、作成しないという結論を会話または task result に短く残す。判定専用の repo 文書は作らない

## 出力

```text
Placement:
- source:
- test / type / schema / static check:
- comment:
- ADR: required | not required — <reason>
- architecture document: required | not required — <reason>
- task-local note: keep temporarily | discard

Updated artifacts:
- <path or none>

Residual non-executable context:
- <context or none>
```

## 制約

- 実装コードは、この Skill 自体の担当として変更しない
- ADR に現行仕様を書かない
- task-local note を恒久文書として扱わない
- コード変更を理由に設計文書を機械的に同期しない
- 成果物の path は repo root 相対で書く
