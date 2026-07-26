# ADR-0005: task lifecycleを一つの番号付きworkflowへ統合する

- Status: accepted
- Date: 2026-07-18

## Context

- authority、調査、planning、knowledge placement、delegation、validation、review、Memory、Gitの規則は個別には定義されていたが、適用順序と戻り先が複数の節へ分散していた
- 番号付きworkflowは変更作業を中心にしており、read-onlyな依頼の分岐、dirty worktreeの確認、実装前のADR判定、session handoff、commitとpushの権限分離を十分に表していなかった
- すべてのtaskでplan、Memory検索、delegation、reviewを一律に行うと、低リスクな作業へ手続きコストが増える。一方、複雑なtaskで適用時点が曖昧だと、未完成状態のreview、後戻りの大きい設計変更、未検証の統合が起きる
- Memoryにはrepositoryの正本を補助する文脈だけでなく、repository artifactとして維持する価値が低いproject固有情報、projectをまたぐユーザー選好、Characterとの関係性や会話エピソードを自然に再利用する役割がある。durableな設計判断だけへ限定すると、この会話継続の用途を失う

## Decision

- `AGENTS.md`の番号付きworkflowを、依頼の分類、baseline確認、正本調査、実行構造の決定、slice実装、統合、最終検証、引き渡し、報告までを統合するtask lifecycleの正本とする
- root sessionは調査前の原因を仮説として扱い、sourceとexecutable contractを読んだ後に根本原因、影響範囲、意図したcontractを確定する
- planning、knowledge placement、ADR、contract-closure、delegation、reviewable sliceの要否は実装前に判断し、scope、contract、責務境界、依存関係が変わった場合だけ見直す
- 小さく低リスクで責務が一つのtaskは一つのsliceへ縮約し、不要なplan、Memory検索、delegation、reviewを省略する。複数の別々に検証可能な責務は、観測可能な成果とtargeted checkを持つsliceへ分ける
- slice内のvalidation failureまたは`blocking` findingはそのsliceへ戻す。統合後にscopeまたはcross-cutting contractが変わった場合は調査と実行構造の判断へ戻す。追加authorityまたは結果を変えるユーザー判断が必要な場合は停止する
- workflowは適用順序と戻り先だけを所有し、共通の完了条件は`AGENTS.md`の各節、role固有の責務は`agents/*.toml`、再利用手順は`skills/*/SKILL.md`を正本とする。共通規則をSkillへ複製しない
- repository-ownedな現在状態、期待状態、決定理由を正本へ置いた後で、必要なMemory、handoff、commit、pushを行う。Memoryには正本へのpointer、非正本のproject文脈、cross-projectのユーザー選好、Characterとの関係性、好み、会話エピソードを置ける。会話内でユーザーが明示した内容は`AGENTS.md`の保存候補、除外条件、authority境界を満たす場合に追加確認なしでappendできる。Character Memoryは観察記録として扱い、現在のユーザー発言とCharacter Definitionを優先する。未完了状態はMemoryではなくhandoffへ置き、commitとpushは別々に権限を判定する

## Alternatives

- 各節を独立したchecklistとして維持する: 局所規則は読みやすいが、適用順序、戻り先、省略条件が曖昧なままになるため採用しない
- すべてのtaskへ同じplan、Memory、delegation、reviewを要求する: 判断は単純になるが、低リスクな作業を儀式化し、完了までの時間とreview findingの探索機会を不要に増やすため採用しない
- workflow全体をhookで機械制御する: 実行順序を強制できるが、task種別、risk、authority、正本の性質による分岐をruntime文字列へ重複させるため採用しない
- file数またはdiff量でtaskの複雑さを判定する: 実装しやすいが、public contract、外部副作用、session継続、責務数を適切に表さないため採用しない

## Consequences

- Positive: 調査、設計判断、slice実装、統合検証、deliveryの順序と戻り先が明確になる
- Positive: 低リスクなtaskでは不要な手順を省き、高リスクまたは複数責務のtaskでは必要なgateを実装前に配置できる
- Positive: AGENTS、role、Skill、hookの正本境界を維持しながら、end-to-endの進行を一つのworkflowから追跡できる
- Positive: repositoryの正本を汚さず、project固有の非正本文脈、cross-projectの選好、Characterとの会話継続をMemoryから再利用できる
- Negative: root sessionはtask種別、risk、slice依存関係、省略可能な手順を初期段階で判断する必要がある
- Negative: Character Memoryのappendとrecallは自然言語上の判断を含み、過剰保存、誤推測、不自然な想起を避ける運用が必要になる
- Negative: lifecycleは自然言語の運用契約であり、runtimeによる完全な状態遷移の強制はない
- Follow-up: 同じ工程の手戻り、不要なartifact、未完了状態の誤保存が繰り返される場合は、該当する戻り先または省略条件を本ADRと`AGENTS.md`で見直す

## Policy Anchors

- Workflow: `AGENTS.md`
- Role contracts: `agents/*.toml`
- Reusable procedures: `skills/task-brief/SKILL.md`、`skills/validation-report/SKILL.md`、`skills/session-handoff/SKILL.md`、`skills/session-resume/SKILL.md`、`skills/withmate-memory/SKILL.md`
- Instruction ownership: `docs/architecture/instruction-governance.md`
- Executable contract: なし。task lifecycleは自然言語の運用契約であり、runtime routing testの責務には含めない
