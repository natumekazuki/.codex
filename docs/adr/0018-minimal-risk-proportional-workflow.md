# ADR-0018: 標準workflowを最小化し、独立reviewをriskに比例させる

- Status: accepted, partially superseded by ADR-0019
- Date: 2026-08-13
- Partially supersedes: ADR-0005, ADR-0007, ADR-0008, ADR-0011, ADR-0012, ADR-0013
- Amends: ADR-0016
- Partially superseded by: ADR-0019 (2026-08-16)

## Amendment

ADR-0019はCandidate snapshot、Review Brief builder、`consolidate-structure` Skillを廃止し、Git commitをsource identityとするreviewへ置き換える。本ADRの最小workflow、risk比例review、runtime gapをvalidation gapとして扱う決定は維持する。

## Context

高リスクな永続化、migration、外部副作用、並行処理の変更では、accepted contractの確認、failure modeを直接観測するcheck、独立reviewが実際の不具合を検出していた。一方、Candidate Definition、Evidence Ledger、Review Brief、session handoffを複数のinstruction、Skill、roleへ展開した結果、同じ規範が重複し、実装よりreview-cycleの手動管理が重くなった。

2026-08-12から2026-08-13昼までの作業監査では、low-risk変更はdirect checkだけで閉じられた一方、高リスク変更の独立reviewには有効なfindingがあった。Candidateのfield不足、再生成、session間搬送は品質保証ではなく運用負担を生み、ユーザーがpromptとartifactのtransportを代行していた。

## Decision

- `AGENTS.md`は、要求とauthorityの確認、正本の探索、accepted contractとfailure modeに沿った実装、direct check、riskに比例したreview、短い完了報告という標準workflowを所有する。
- goal、scope、done、riskの整理と、変更、実行済み検証、未実行、残リスクの報告は標準workflowへ含め、`task-brief`と`validation-report`を削除する。
- 情報配置の原則は`AGENTS.md`へ集約し、重複していた`knowledge-placement`を削除する。
- sessionの再開は現在のgit、source、test、ADR、必要なplanから組み立てる。`session-handoff`と`session-resume`を削除し、未完了状態を別名のSkill、Memory、Candidate、常設artifactへ移植しない。
- `contract-closure`はaccepted contract、Invariant、Sibling Sweep、failure timing、Finding Promotionを所有する。標準workflow、role routing、reportingを再定義しない。
- Candidate snapshotとReview Brief builderは、high-riskまたはnon-localなreviewでexact source stateが必要な場合に限る実行helperとして残す。Candidateはsource stateだけを識別し、review cycle、session expiry、review contract freshnessは証明しない。schemaとread-only verification recipeはscriptsとtestsを正本とし、`AGENTS.md`やrole contractへfieldを複製しない。
- Evidence Ledgerを標準artifactにしない。Review Brief schema version 2ではLedgerの入力、検証、出力fieldを除去し、旧fieldを拒否する。checkとreview結果はtask-localな実行記録として扱い、sourceまたはreview contractが変わった場合はcurrent stateから必要な証拠を作り直す。
- reviewer roleは担当scope、禁止事項、出力だけを所有する。Candidate schema、失効規則、review convergenceを再定義しない。
- agent間transport、deadline enforcement、partial result回収、cycle binding、session終了時のartifact失効はruntimeの責務とする。runtimeが提供しない機能を自然言語のfallbackやユーザーの手動搬送で補わず、validation gapとして扱う。cycle bindingを確認できないCandidateを別sessionまたは別review contractのcurrent evidenceとして扱わない。
- `consolidate-structure`は次の3から5論理変更で固有のfindingと構造改善を観測してから削除可否を判断する。監査Skillのruntime責務の簡素化も別の論理変更とする。

ADR-0012の「Review Brief」という歴史的な命名説明と、一つの論理変更につきholistic complete-diff reviewを一度以下にする決定は維持する。

## Alternatives

- 既存Skillを残してtriggerだけ狭める: 誤発火は減るが、規範の重複とmaintenance costが残るため採用しない。
- CandidateとReview Briefを一律に撤去する: low-riskの負担は減るが、高リスクreviewでexact source stateを検証する既存の実行契約まで失うため採用しない。
- review-cycle管理を別名のSkillへ移す: ownerの名称だけが変わり、artifact transportとruntime gapを解決しないため採用しない。
- 独立reviewを一律に減らす: 高リスク変更で実際に検出できたfailure familyを失うため採用しない。

## Consequences

- Positive: low-risk変更は実装とdirect checkを中心に閉じ、Skill発火、gate表示、artifact作成を標準コストにしない。
- Positive: high-risk変更ではaccepted contract、Invariant、failure timing、direct check、独立reviewを維持する。
- Positive: task lifecycle、専門手順、role contract、runtime transportのownerが分離される。
- Negative: goalや完了報告の形式をSkill schemaで強制しないため、標準workflowの遵守は`AGENTS.md`と直接検証に依存する。
- Negative: runtime transportがない環境では、高リスクreviewを完了できずvalidation gapとして止まる場合がある。
- Follow-up: 次の3から5論理変更で、要求誤認、validation漏れ、ユーザーによるartifact搬送、Candidate再生成、独立reviewのvalid findingを観測する。

## Policy Anchors

- Standard workflow and authority: `AGENTS.md`
- Contract reasoning and finding promotion: `skills/contract-closure/SKILL.md`
- Exact source and review input schemas: `skills/contract-closure/scripts/candidate_snapshot.py`、`skills/contract-closure/scripts/review_brief.py`
- Historical executable contracts: Candidate snapshotとReview Briefのscriptsおよびpolicy文言検査はADR-0019で削除した。
- Review role boundaries: `agents/slice_reviewer.toml`、`agents/targeted_reviewer.toml`、`agents/reviewer.toml`
