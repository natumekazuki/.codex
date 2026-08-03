# ADR-0007: frozen Candidateと不変条件lensでhigh-risk reviewを収束させる

- Status: accepted, amended by ADR-0008, ADR-0012, and ADR-0013
- Date: 2026-07-26
- Amends: ADR-0004, ADR-0005
- Related: ADR-0006
- Amended by: ADR-0008 (2026-07-27), ADR-0012 (2026-08-03), ADR-0013 (2026-08-03)

## Amendment

ADR-0012は、specialist review後のholistic complete-diff reviewを`Full-review gate=run`の場合の一度に限定し、そのfinding修正後のfresh-context full-diff closure reviewを廃止する。specialist lens、Candidate、Evidence Ledger、同一Candidateへ証拠を揃える決定は維持する。ADR-0013は、実運用で確認された観点混在を受け、初期導入の単一`reviewer` roleをholistic専用`reviewer`とtargeted / specialist / closure専用`targeted_reviewer`へ分割する。lensごとの専用roleは追加しない。

## Context

Codex App Server AdapterとRuntime Hostの実装では、外部reviewを重ねるたびに異なるblocking findingが見つかった。findingの多くは独立した欠陥ではなく、mutationの相関と副作用確度、resource ownerの解放、failure timing、response projectionなど、同じ不変条件familyの兄弟経路で反復していた。

genericなcomplete-diff reviewを直列に追加すると新しい反例は見つかるが、観測されたcall pathごとの局所修正になりやすい。targeted re-reviewと実行済みcheckが、更新後のexact diffに対するholistic closureとして扱われる余地もあった。また、external schemaのrequirednessを一次根拠で固定しないままreview findingを採用し、修正を後から反転した事例があった。

通常quotaの節約より成果物品質を優先しつつ、review回数そのものを品質の代理にせず、追加するreviewの観点と対象差分を固定する必要がある。

## Decision

- `contract-closure`対象のhigh-riskまたはnon-localな変更では、accepted contractの根拠、supported scope、観測可能なfailure、canonical owner、兄弟入口、executable anchorを実装前に確定する。required / optional、default、failure semanticsなど結論を反転させる根拠が未確定なら、reviewへ進まず契約を確認する
- source、適用可能なexecutable contract、targeted check、該当する構造収束gateが揃ったexact source stateをtask-localなCandidateとして凍結する。Candidate DefinitionとEvidence Ledgerの境界、identity mode、失効、evidence entryの出自、sandbox別の作成・read-only検証recipeはADR-0008と`contract-closure`を正本とし、本ADRではreview方式を所有する
- `contract-closure`はInvariant Matrixから独立してtriggerされたreview lensを選ぶ。1 lensにつき1 reviewer、同じCandidateにつき1から3 lensを原則として並列にreviewし、同じlensへreviewerを重ねない
- specialist reviewerは割り当てられたlensとmatrix cellを反証し、review済みcell、未確認cell、finding、hardening候補、validation gapを分ける。root sessionがfindingをaccepted contractへ照合し、不変条件familyへ統合して最終分類する
- 全specialist reviewを終え、`blocking`がある場合だけSibling Sweepとcheckを再実行する。新Candidateではfindingを出したlensがfamilyとdeltaをtargeted re-reviewし、他のtrigger済みlensも担当cellへのdeltaの非影響を再確認する。全lensの証拠が同じ現行Candidateへ揃った後、`blocking`の有無にかかわらず、過去finding、specialist reviewの結論、claimed resolution、実装者の結論、既存Closure Mapを知らないreviewerが更新後complete diffをholisticにreviewする
- specialist reviewはADR-0004のfull-diff review回数へ数えない。holistic complete-diff reviewと、その`blocking`修正後のfresh-context closure reviewにはADR-0004の上限と停止条件を適用する
- 初期導入では既存の`reviewer` roleへreview kindとlensを渡す。専用roleの追加、routing hookによる機械制御、恒久的なCandidate保存は、実案件pilotで観点混在や証拠誤帰属が確認された場合だけ検討する

## Alternatives

- generic reviewerによるcomplete-diff reviewをfindingが減るまで反復する: 新しい反例は探索できるが、同じ不変条件familyの局所修正とreviewの非収束を防げないため採用しない
- 最初からlensごとの専用agent roleを作る: 静的な責務は明確になるが、triggerと有効性を確認する前にrole、config、routing testを増やすため採用しない
- Candidate IDを使わず、branchまたは最新diffだけでreview証拠を管理する: review後のeditでcheckとreviewの対象がずれるため採用しない
- review cycleをhookで機械制御する: evidence identityを強制できるが、現在は自然言語workflowのpilot前で状態機械の保守コストが先行するため採用しない
- `consolidate-structure`へ統合する: 同Skillはaccepted behaviorを変えない責務配置の収束を所有し、本決定はcorrectnessとreview evidenceを所有するため採用しない

## Consequences

- Positive: 同じ不変条件を持つ兄弟operationとfailure timingを、一つのfamilyとしてreviewと修正へ載せられる
- Positive: schema根拠とreview scopeをexact Candidateへ、checkとreview結果をそのEvidence Ledgerへ結び付け、moving diffへの誤ったclosure claimを減らせる
- Positive: reviewコストをgenericな反復ではなく、変更がtriggerした専門観点へ配分できる
- Positive: hardening候補とaccepted contract違反を分離し、root sessionが根拠付きで停止判断できる
- Negative: high-riskな変更ではCandidate作成、matrix、複数reviewer、holistic closureの実行コストが増える
- Negative: Candidate IDとmatrixはtask-localな自然言語artifactであり、初期導入では機械的な同一性強制を持たない
- Negative: review lensの選択とfinding familyの統合にはroot sessionの判断が残る
- Follow-up: 次のeligibleな実変更と、Adapter / Runtime Hostの履歴を使ったread-only replayで、同family findingの初回検出、review重複、未確認cell、holistic review回数を確認する。lens指定だけで観点が混ざる場合は専用roleを追加し、追加作業がfinding familyのclosureへ寄与しない場合はlens数またはCandidate項目を縮小する

## Policy Anchors

- Lifecycle and holistic join: `AGENTS.md`
- Candidate Definition, Evidence Ledger, identity, invalidation, Invariant Matrix, lens selection, and Review Brief: `skills/contract-closure/SKILL.md`
- Reusable counterexample axes: `skills/contract-closure/references/trigger-matrices.md`
- Holistic reviewer responsibility and output: `agents/reviewer.toml`
- Targeted, specialist, and closure reviewer responsibility and output: `agents/targeted_reviewer.toml`
- Structural convergence boundary: `skills/consolidate-structure/SKILL.md`
- Runtime executable contract: なし。review cycleを機械制御するruntimeを導入する場合だけ、その状態遷移を別のexecutable contractとして追加する
