# ADR-0006: external review前の構造収束をmain sessionが所有する

- Status: accepted
- Date: 2026-07-25
- Amends: ADR-0005
- Related: ADR-0004

## Context

実装とread-only reviewを別sessionへ分けるworkflowでは、review findingをmain sessionが修正し、更新差分を新しいreview sessionへ渡す。このcycleはcorrectnessと回帰リスクを独立して確認できる一方、局所的なfinding対応が既存unitへ責務、分岐、adapter、重複したsemantic decisionを積み重ねても、個々の修正が正しければ検出しにくい。

review回数、finding数、clean review、PR作成依頼を構造整理のtriggerにすると、review cycleが整理を自己増殖させる。file数やdiff量だけでは、大きくても凝集した変更と、小さくても責務を漏らす変更を区別できない。外部reviewerに整理を任せると、read-onlyな反証探索と実装責任が混ざる。

構造整理をどのsessionが、どの状態で、何を根拠に行い、整理後にどこへ戻るかをtask lifecycleへ追加する必要がある。

## Decision

- 構造収束gateは、変更を所有するmain implementation sessionが実行する。review-only sessionとread-only childは実行しない
- source、適用可能なexecutable contractまたは理由付きの代替確認、targeted checkが揃った状態をimplementation-complete candidateと呼ぶ。構造収束gateと必要なpost-edit validationを終えるまではsliceの完了状態としない
- 次に外部read-only review cycleへ渡すcandidateについて、今回変更したscope / dependency topologyにsemantic ownerの分散、独立責務の混在、canonical boundaryの迂回、slice間のdecision重複、または新しいtest couplingを示す具体的なevidenceがある場合だけ`consolidate-structure` Skillを使う
- file数、変更行数、diff量、review回数、finding数、clean review、PR作成依頼は単独のtriggerにしない。量的情報はsemantic signalを調べる範囲の補助にだけ使う
- Skillは今回変更したinternal structureと直接consumerに対し、accepted behaviorとexecutable contractの意味を保つ一回のbounded edit batchだけを許可する
- public contract、永続化、authorization、external side effect、error semantics、failure timing、concurrency、resource limit、resource ownership / authorization scope、第三者dependency、またはexecutable contractの意味を変える必要がある場合は整理を止め、通常workflowの調査と設計へ戻す。該当する場合は`contract-closure`を使う
- 整理で差分を変更した場合、整理前のgreen結果は最終検証として扱わない。sliceをimplementation中へ戻し、元のtargeted check、影響に応じたbuild / typecheck / lint / smoke、必要なSibling Sweepを再実行する
- Skillは外部reviewを開始せず、reviewの回数、scope、fresh-context条件を変更しない。後続のfinding対応が新しいqualifying topology evidenceを生じた場合だけ、新しいcandidateとして再判定する
- lifecycle上の適用順序と戻り先は`AGENTS.md`、再利用可能なinventory、分類、bounded edit、停止規則は`skills/consolidate-structure/SKILL.md`を正本とする

## Alternatives

- PR作成依頼の直前に常時実行する: userがreview cycleを終える判断をした後に新しい変更とreviewを増やすため採用しない
- reviewのたびに実行する: review findingが構造整理を再帰的に発火させ、有限なreview収束を崩すため採用しない
- review回数またはfinding数にthresholdを置く: findingの性質と責務topologyを表さず、別session間の回数管理も正本化しにくいため採用しない
- file数、変更行数、diff量だけで発火する: 大きく凝集した変更へ過剰発火し、小さい責務漏れを見逃すため採用しない
- 外部reviewerが構造整理する: read-only reviewと実装責任を混ぜ、reviewerの独立性を失うため採用しない
- `contract-closure`へ統合する: `contract-closure`は不変条件とcorrectnessのclosureを所有し、本判断はaccepted behaviorを変えない責務配置の収束を所有するため採用しない
- gateを`AGENTS.md`だけへ直接記述する: lifecycle orderingと具体的な再利用手順が混ざり、手順を他repositoryで再利用しにくくなるため採用しない

## Consequences

- Positive: correctness reviewへ渡す前に、今回の変更で生じた責務分散とsemantic duplicationをmain sessionが処理できる
- Positive: review回数やdiff量に依存せず、小さい責務漏れと大きく凝集した変更を区別できる
- Positive: 構造整理後の差分だけを再検証し、外部reviewerへ渡せる
- Positive: review cycleの回数制限とread-only reviewerの独立性を維持できる
- Negative: semantic ownerとdependency topologyの判定には自然言語上のばらつきが残る
- Negative: qualifying signalがあるcandidateでは、外部review前にinventoryとpost-edit validationのコストが増える
- Negative: fail-closedな境界により、構造上望ましい変更でも別の設計判断または論理変更へ切り出す場合がある
- Follow-up: 同型の過剰発火または見逃しが反復した場合だけ、実例に基づくsemantic signalをSkillへ追加する

## Policy Anchors

- Lifecycle and return paths: `AGENTS.md`
- Reusable procedure: `skills/consolidate-structure/SKILL.md`
- Review convergence: `docs/adr/0004-bounded-review-and-risk-acceptance.md`
- Integrated lifecycle: `docs/adr/0005-integrated-task-lifecycle.md`
- Executable contract: なし。自然言語のworkflow契約としてscenario-based forward testで確認する
