# Validation

## Changed

- Source: <path and summary, or none>
- Executable contract: <test / type / schema / static check path and summary, or none with reason>

## Target

- Behavior / failure mode: <expected behavior or failure prevented>

## Checks Run

| Entry ID | Check / evidence kind | Executed-on Candidate ID | Origin entry / Candidate | Reviewed definition delta | Non-impact rationale | Ledger status | Current-evidence basis | Result and expectation proved |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| <entry ID or not applicable> | `<command or check>` / definition-delta non-impact confirmation | <ID or "not applicable — check not Candidate-bound"> | <entry ID and Candidate ID, or not applicable> | <delta or not applicable> | <rationale or not applicable> | current / superseded / unconfirmed / not applicable | executed on this Candidate / new confirmation entry on this Candidate / not applicable | <immutable result and the expectation it proves> |

## Regression Coverage

- <principal regression scenario and covering contract, or gap>

## Contract Integrity

- preserved | changed intentionally — <reason> | discrepancy — <detail>

## Review

- Required: yes | no — <reason>

| Entry ID | Step / evidence kind | Executed-on Candidate ID | Origin entry / Candidate | Reviewed definition delta | Non-impact rationale | Source identity | Review contract | Ledger status | Current-evidence basis | Result | Lens / scope | Cells reviewed / unreviewed | Complete diff reviewed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| <entry ID or not applicable> | <initial / specialist / targeted re-review / holistic complete-diff / fresh-context closure / definition-delta non-impact confirmation> | <ID or "not applicable — review not Candidate-bound"> | <entry ID and Candidate ID, or not applicable> | <delta or not applicable> | <rationale or not applicable> | <identity mode, value, resolved base OIDs, read-only verification recipe, and creator tree OID if applicable; or not applicable> | <revision / recipe, accepted anchors and contract meaning, Invariant IDs and definitions, supported scope, cell definitions, lens scope, or not applicable> | current / superseded / unconfirmed / not applicable | reviewed on this Candidate / new confirmation entry on this Candidate / not applicable | <immutable review result> | <lens or scope> | <cells or "not applicable — review not Candidate-bound"> | yes / no |

- Full-diff review count: <number or 0>
- Blocking status: none | remaining — <detail> | not applicable
- Accepted risk: <risk and rationale, or none>
- Validation gap: <gap or none>

## Completion Gates

- Source / executable contract: aligned | discrepancy — <detail>
- ADR: required — <path> | not required — <reason> | unresolved — <detail>
- Architecture document: required — <path> | not required — <reason> | unresolved — <detail>

## Not Run

- <check and reason, or "none">

## Residual Risk

- <risk or "none">
