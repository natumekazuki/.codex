# ADR-0001: 設計情報は実行可能な正本を優先する

- Status: accepted
- Date: 2026-07-13
- Supersedes: none

## Context

- 設計書を先に作り、実装後も現行仕様として同期する運用では、実際に最も参照される source と test に加えて別の正本が生まれる
- 設計書を常に読まない運用では、文書の陳腐化と実装との不一致を検出しにくい
- 一方、判断理由、外部制約、複数 subsystem をまたぐ責務など、source、test、type、schema、static check、comment だけでは復元できない情報は残す必要がある

## Decision

- 現在の実装と構造は source を正本にする
- 実行可能な期待動作、不変条件、契約は test、type、schema、static check を正本にする
- 局所的な理由や制約は code comment に置く
- 局所的な実装詳細を超え、複数の妥当な選択肢、高い後戻りコスト、外部制約または長期的 trade-off、理由喪失リスクのいずれかに該当する決定は ADR に必ず残す
- ADR 以外の恒久設計文書は、複数 subsystem / process / repo / 外部 service に波及し、単一の code location や test 群から全体像を復元できず、誤解が全体不整合を生み、実行可能な契約や comment だけでは背景・制約を表せない非局所情報に限定する
- task-local な design note を repo 設計書へ同期することは既定にしない

## Alternatives

- 設計書を現行仕様の正本として維持する: source と test に加えて同期対象が増え、実際の参照順と一致しないため採用しない
- 恒久設計文書をすべて廃止する: 判断理由や非局所的な外部制約が失われるため採用しない
- 重要度だけで文書化を判断する: 局所的で実行可能な情報まで文書へ複製されるため採用しない

## Consequences

- Positive: 実装と期待動作の正本が、日常的に読まれ検証される artifact に集約される
- Positive: 恒久文書は理由、外部制約、全体責務に集中できる
- Negative: 不変条件を test、type、schema、static check へ落とす規律が必要になる
- Negative: 非局所情報が architecture 文書の全条件を満たすか、変更時に確認する必要がある
- Follow-up: 配置判断は`AGENTS.md`の「Sources of Truth and Knowledge Placement」で支援する

## Executable Anchors

- Source: `AGENTS.md`
- Tests / types / schemas / static checks: policy-only のためなし
