# 通常作業用テンプレート

Candidate Definitionを使わない作業では、このテンプレートだけを使う。Candidate専用の見出し、表、`not applicable`列を追加しない。

# Validation

## Changed

- Source: <path and summary, or none>
- Executable contract: <test / type / schema / static check path and summary, or none with reason>

## Target

- Behavior / failure mode: <expected behavior or failure prevented>

## Checks Run

| Check | Result and expectation proved |
| --- | --- |
| `<command or check>` | <result and the expectation it proves> |

## Regression Coverage

- <principal regression scenario and covering contract, or gap>

## Contract Integrity

- preserved | changed intentionally — <reason> | discrepancy — <detail>

## Review

- Required: yes | no — <reason>
- Result: <review kind, scope, result, or not run>
- Complete diff reviewed: yes | no
- Full-diff review count: <number or 0>
- Blocking status: none | remaining — <detail>
- Accepted risk: <risk and rationale, or none>
- Validation gap: <gap or none>

## Completion Gates

- Source / executable contract: aligned | discrepancy — <detail>
- ADR: required — <path> | not required — <reason> | unresolved — <detail>
- Architecture document: required — <path> | not required — <reason> | unresolved — <detail>

## Not Run

- <check and reason, or none>

## Residual Risk

- <risk or none>

# Verified Candidate拡張

Candidate verification resultが`verified`の作業では、通常作業用テンプレートの後へ次の節を追加する。task-localなEvidence Ledger全体の代わりにはせず、現行Candidateの完了判断に使うevidenceとgapだけを要約する。

## Candidate Evidence

- Candidate ID: <ID>
- Source identity: <mode, value, resolved base OIDs, read-only verification recipe, raw diff command / digest, and creator tree OID when applicable>
- Review contract: <revision / recipe, accepted anchors and contract meaning, Invariant IDs, supported scope, cell definitions, and lens scope>
- Candidate verification result: verified
- Structural convergence gate / result: <canonical gate result from the task-local Ledger>

| Entry ID | Evidence kind | Executed-on Candidate | Origin entry / Candidate | Ledger status | Result / current-evidence basis | Reviewed definition delta / non-impact rationale |
| --- | --- | --- | --- | --- | --- | --- |
| <check or review Entry ID> | <check, review, or definition-delta non-impact confirmation> | <Candidate ID> | <origin IDs only for a confirmation, otherwise none> | <check / review entry status defined by contract-closure> | <immutable result and why this entry is or is not completion evidence> | <required for a confirmation, otherwise none> |

## Candidate Matrix Coverage

| Invariant / cell | Coverage status | Current evidence Entry IDs | Gap / rationale |
| --- | --- | --- | --- |
| <Invariant ID / cell> | <covered / anchored-exception / residual-risk / unresolved> | <current check / review Entry IDs, or none> | <reason for exception, risk, unresolved status, or none> |

## Candidate Review Coverage

| Entry ID | Review kind / lens | Cells reviewed | Cells unreviewed | Complete diff reviewed |
| --- | --- | --- | --- | --- |
| <review Entry ID from Candidate Evidence> | <review kind and lens> | <cells> | <cells or none> | yes / no |

- Current evidence summary: <evidence that satisfies the current Candidate>
- Candidate validation gap: <missing or non-current evidence, or none>

# Candidate verification-onlyテンプレート

Candidate verification resultが`mismatch`または`validation-gap`の場合は、このテンプレートだけを使う。通常作業用テンプレート、Verified Candidate拡張、substantive finding、approval、completion evidence、coverage表は出力しない。

# Candidate Verification

- Overall judgment: not assessed — mismatch | not assessed — validation-gap
- Review kind: <kind echoed from the handoff>
- Review scope: Candidate verification only
- Complete updated diff reviewed: no
- Blocking finding status: not assessed
- Candidate ID: <ID>
- Candidate verification result: mismatch | validation-gap
- Review Entry ID: <ID echoed from the handoff, or unassigned; not a Ledger entry>
- Verification evidence: <mismatch evidence or completed verification steps>
- Validation gap: <missing field, object, query, or sandbox capability, or none for a confirmed mismatch>
- Reviewed cells: none
