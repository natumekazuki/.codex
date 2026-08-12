# ユーザー向け完了報告

すべてのchange / build / fixで、まずこの要約をユーザー向けメッセージとして出す。見出しや箇条書きは必須ではないが、次の意味と順序を短時間で読み取れるようにする。
通常は4から6行程度に収め、完了判断に影響しない内部追跡項目を追加しない。

```text
結果: <完了、一部完了、または未完了と、何が変わったか>
要判断・操作: なし | <ユーザーが決めることまたは行うこと>
主な検証: <実行した主要checkと結果。何を証明したかを含める>
未検証・blocking・残リスク: なし | <完了判断への影響を含めた要約>
レビュー: Full-review gate=run | skip — <root sessionの判定理由と、実施したreviewの要点>
詳細: <repo root相対のMarkdown path。詳細成果物を作った場合だけ追加>
```

- ユーザーの判断事項、blocking、未検証リスクは詳細Markdownのみに置かない。
- 詳細成果物を作らない場合は`詳細`行を出さない。
- Candidate ID、Entry ID、digest、origin、lens、matrix cellは、その値自体がユーザーの判断に必要な場合を除き要約へ展開しない。
- review deadline、retry、full-diff review count、ADR / architecture gateは追跡証拠へ保持し、要判断、blocking、gap、残リスクに影響する場合だけ要約に含める。

# 詳細Markdownを作る条件

次のいずれかを満たす場合だけ、task-localなMarkdownを作る。

- 根拠が多く、ユーザー向けメッセージだけでは正確さを維持できない。
- 後から参照する価値がある。
- Candidateまたは複数reviewの追跡情報を保存する必要がある。

小規模で、上の要約だけで正確に完了判断できる作業には作らない。HTMLは図表または操作性が必要な場合だけ使う。

# 詳細Markdownの構成例

条件を満たした場合だけ使う。空の見出しや`not applicable`用の表を作らない。

```text
# Validation Evidence

## Changed behavior and contract
- Source: <path and summary>
- Executable contract: <test / type / schema / static check path and summary, or none with reason>
- Behavior / failure mode: <expected behavior or failure prevented>
- Contract integrity: preserved | changed intentionally — <reason> | discrepancy — <detail>

## Checks and regression coverage
- <command or check>: <result and expectation proved>
- <principal regression scenario and covering contract, or gap>
- Not run: <check and reason, or none>

## Review and completion gates
- Targeted / specialist review: <required / not required and reason; kind, scope, result, or not run>
- Full-review gate: run | skip — <root sessionの判定理由>
- Holistic complete-diff review: <scope and completed / unavailable / deadline exceeded / not applicable>
- Complete diff reviewed / full-diff review count: <yes|no> / <0|1>
- Review deadline / retry: <status>
- Blocking / accepted risk / validation gap: <summary>
- Source / executable contract: aligned | discrepancy — <detail>
- ADR / architecture document: <required, not required, or unresolved with reason>
- Residual risk: <risk or none>
```

## Verified Candidateの追跡情報

Candidate verification resultが`verified`で、詳細Markdownの作成条件を満たす場合は、task-localなEvidence Ledgerを正本とし、次の情報を詳細Markdownへ投影する。

- Candidate ID、source identity、resolved base OID、raw diff digest、review contract、Candidate preflight、Candidate verification result
- structural convergence gate / result
- currentなcheck / review Entry ID、実行Candidate、origin、ledger status、definition delta、non-impact rationale
- Matrix cellごとのcoverage statusとcurrent evidence
- review kind、lens、review済み・未確認cell、complete diff確認の有無
- holistic discoveryのimmutableな出自とFinal Candidate closure chain
- current evidence summaryとCandidate validation gap

旧holistic entryを現行Candidateのcompletion evidenceとして表示しない。非現行entryは、gapまたはcurrent evidenceの由来に必要なものだけ投影する。

# Candidate verification-onlyの出力

Candidate verification resultが`mismatch`または`validation-gap`の場合は、次の意味だけを出力する。通常作業の完了報告、substantive finding、approval、completion evidence、coverage表を混ぜない。

```text
結果: substantive reviewは未評価 — Candidate verification resultがmismatch | validation-gap
要判断・操作: なし | <mismatchまたはvalidation gapを解消するためにユーザーが決めることまたは行うこと>
検証範囲: Candidate verification only。complete updated diffは未確認
Blocking finding: not assessed
Candidate / preflight / verification: <Candidate ID> / verified / mismatch | validation-gap
Review Entry ID: <Review Briefの値またはunassigned。Ledger entryとして扱わない>
検証証拠: <mismatch evidenceまたは完了したverification step>
Validation gap: <missing field, object, query, or sandbox capability, or none for a confirmed mismatch>
Reviewed cells: none
```
