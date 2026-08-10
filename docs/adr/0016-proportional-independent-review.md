# ADR-0016: 独立reviewを高リスク境界と直接検証不能なinteractionへ限定する

- Status: accepted
- Date: 2026-08-10
- Amends: ADR-0013, ADR-0014
- Related: ADR-0011, ADR-0012

## Context

ADR-0013とADR-0014はreview kindとroleを分離したが、通常のcompleted sliceを`slice_reviewer`へ渡す運用を残していた。このため、局所的・単一責務でtargeted checkがaccepted contractを直接検証できる変更にも、独立reviewを追加できた。direct checkと独立reviewが同じfailure modeを確認する場合、追加のtoken、待ち時間、finding対応が完了条件へ寄与しない。

## Decision

- 局所的・単一責務で、targeted checkがaccepted contractを直接検証できるsliceには独立reviewを起動しない。
- `slice_reviewer`は、targeted checkでは直接検証できない具体的なnon-high-risk interactionがあり、対象scopeとtriggerを明示できる場合だけ使う。
- 高リスク境界、`contract-closure`が要求するtargeted / specialist review、`Full-review gate=run`のholistic complete-diff reviewは従来どおり維持する。
- review findingの`current-scope repair`はdirect checkと同じfinding family / resulting deltaのtargeted closureで閉じ、同じscopeの探索reviewまたはcomplete-diff reviewを再開しない。
- `fast_reviewer`はユーザーがexact roleを明示した場合だけ使い、通常workflowでは自動選択しない。
- routing modeはfast roleの実行可否とfallback contextだけを定め、独立reviewの必要性やtriggerを追加しない。

## Alternatives

- 通常のcompleted sliceを一律に`slice_reviewer`へ渡す: 実装から独立した視点は得られるが、direct checkが同じ契約を直接検証できる場合にもreviewコストが発生するため採用しない。
- 局所変更を`fast_reviewer`へ自動的に渡す: reviewer単価は下がるが、重複reviewの起動回数は減らないため採用しない。
- 高リスクreviewもdirect checkで代替する: public contract、永続化、認可、並行処理などの反例探索を失うため採用しない。

## Consequences

- Positive: direct checkで閉じる変更はreview agentを起動せず完了できる。
- Positive: reviewを起動する場合、対象interactionまたは高リスクtriggerを説明できる。
- Positive: finding修正後のclosureが同じfamilyへ限定され、探索reviewの反復を防げる。
- Negative: targeted checkが契約を直接検証できるかをroot sessionが明示的に判定する必要がある。
- Negative: direct checkで観測できないinteractionを見落とすとreview不足になるため、plannerとroot sessionはinteractionと高リスクtriggerを先に列挙する必要がある。

## Policy Anchors

- Review lifecycle and completion gates: `AGENTS.md`
- Static review role contracts: `agents/slice_reviewer.toml`、`agents/targeted_reviewer.toml`、`agents/reviewer.toml`、`agents/fast_reviewer.toml`
- Planning contracts: `agents/planner.toml`、`agents/fast_planner.toml`
- Executable routing contract: `hooks/test-subagent-routing.ps1`
