# ADR-0008: Candidate DefinitionとEvidence Ledgerを分離する

- Status: accepted
- Partially superseded by: ADR-0018
- Date: 2026-07-27
- Amends: ADR-0007
- Related: ADR-0004, ADR-0006

## Context

ADR-0007は、high-riskまたはnon-localな変更について、exact source stateをfrozen Candidateとして固定し、Invariant Matrixから選んだ専門lensとholistic reviewを同じCandidateへ結び付けた。

初期のCandidate Evidenceは、source stateとreview scopeだけでなく、実行済みcheckの集合・結果、matrixのcoverage status、構造収束gateの結果までCandidateの失効条件に含めていた。このため、sourceを変更せずにreviewerが求めたcheckを追加しただけでもCandidateと既存reviewが失効し、証拠を増やす操作がreviewを自己失効させる。

また、Candidate treeを通常のGit indexで構築すると、reviewのためだけのstageがユーザーの既存staged変更と混在し得る。`HEAD`やbranch名などの可変refをbaseとして保存し、再現時に解決し直すと、Candidate作成後のcommit、rebase、checkoutによって同じ表記から異なるraw diffが生成される。さらに、`read-tree`はindexを書き換え、`write-tree`はGit objectを生成するため、read-only reviewerや`.git`が保護された通常のworkspace-write環境ではtree生成recipeを再実行できない。Candidate identityと可変な完了証拠の境界、sandboxに依存しないidentity生成・検証規則、およびbaseをimmutableに固定する規則を明確にする必要がある。

review contractだけを変更した後に旧evidenceを新Candidateへ再関連付けすると、そのentryがどのCandidate上で実行されたか分からなくなる。元Candidateでの実行結果と、新Candidate上で行った定義差分の非影響確認は、別々の証拠として追跡する必要がある。

## Decision

- Candidateを不変の`Candidate Definition`と可変の`Evidence Ledger`へ分ける
- Candidate Definitionは、immutableなbase OIDを含むSource Identityと、accepted anchor、その契約上の意味、Invariant、supported scopeを含むReview Contractで構成する。ref labelはprovenanceの説明にだけ使う
- Source Identityの標準方式は、Git metadataへ書き込まず作成側とread-only reviewerが同じ状態を再現できる方式とする。treeを使う方式は作成側に必要なauthorityがある場合だけ選び、reviewerには生成を要求しない
- Evidence LedgerにはCandidateの定義を変えずに追加できる完了証拠と、その出自を記録する。field、status、Candidate間の扱いは`skills/contract-closure/SKILL.md`だけで定義する
- source identityまたはreview contractが変わった場合のCandidate失効とevidenceの扱いは`skills/contract-closure/SKILL.md`、specialist reviewからholistic reviewへの合流順序は`AGENTS.md`だけで定義する
- Candidate Definition、Evidence Ledger、失効条件、生成・検証手順、Review Briefの詳細は`skills/contract-closure/SKILL.md`を正本とする

## Alternatives

- checkとreview結果をCandidate Definitionへ含め続ける: 証拠追加が既存証拠を自己失効させ、review cycleが収束しないため採用しない
- Candidateをsource identityだけで定義する: accepted anchor、Invariant ID、cell定義、lens scopeの変更を検出できず、異なるreview contractの証拠を混在させるため採用しない
- review contract変更時に全lensを無条件で全面再reviewする: 安全側ではあるが、影響しないcellまで再探索し、専門lensを選ぶ効果を失うため採用しない
- review contract変更後に旧entryのCandidate IDを書き換える: 実行時の出自と新Candidate上の非影響確認を区別できなくなるため採用しない
- baseを可変refだけで記録し、再現時に解決する: Candidate作成後のref移動で同じCandidate表記から異なるsource identityとraw diffが生成されるため採用しない
- Candidate treeを常に必須にする: `.git`がread-onlyまたは保護された実行環境で作成・再検証できず、通常のreview lifecycleが停止するため採用しない
- 通常のGit indexへstageしてtree OIDを作る: ユーザーのstaged stateを変更または混在させるため採用しない
- CandidateとEvidence Ledgerを恒久保存する: 初期運用ではtask-localな自然言語artifactで足り、状態機械と保存形式の保守コストが先行するため採用しない

## Consequences

- Positive: sourceを変えずにcheckやreview evidenceを追加でき、review cycleを自己失効させない
- Positive: source変更とreview scope変更で必要な再確認範囲を区別できる
- Positive: specialist reviewとholistic reviewが同じCandidate Definitionへ収束しているか追跡できる
- Positive: base refが移動しても、Candidateのsource stateとraw diffを同じOIDから再現できる
- Positive: Candidate作成が通常のGit indexと既存staged変更を汚さない
- Positive: read-only reviewerとGit metadataが保護されたworkspace-write環境の両方で標準identityを検証できる
- Positive: evidenceの実行Candidateと定義差分の非影響確認を監査時に区別できる
- Negative: Candidate DefinitionとEvidence Ledgerを別々に記録する手間が増える
- Negative: review contractだけを変更した場合、影響しないlensにも定義差分の非影響確認が必要になる
- Negative: `manifest-digest` recipeではrecord framing、path、mode、object type、content digestの取り扱いを明示する必要がある
- Negative: task-localな自然言語artifactであるため、identityとevidence statusの機械的な強制は限定的である
- Follow-up: 実案件で誤失効または誤継承が反復した場合だけ機械的な状態管理を導入し、その実装の観測可能な状態遷移をexecutable contractとして検証する

## Policy Anchors

- Lifecycle and holistic join: `AGENTS.md`
- Candidate Definition, Evidence Ledger, invalidation, and Review Brief: `skills/contract-closure/SKILL.md`
- Reusable counterexamples: `skills/contract-closure/references/trigger-matrices.md`
- Reviewer read-only boundary, accepted input, and output: `agents/reviewer.toml`, `agents/targeted_reviewer.toml`
- Current reporting policy: `AGENTS.md`
- Runtime executable contract: なし。状態管理を実装する場合だけ、その実装の観測可能な振る舞いを検証する
