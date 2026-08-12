---
name: validation-report
description: 実装後に、変更したsourceと実行可能な契約、実行・未実行の検証、ADR / architecture gate、残リスクを短く揃えて報告する。
---

# Validation Report

## 目的

- 実行したcheckだけでなく、変更した現在状態と期待状態の整合を確認する。
- 未実行項目やknowledge placementの未解決を隠さず、完了判断に必要な情報を揃える。
- ユーザー向けメッセージと追跡用の詳細証拠を分け、結論と判断事項を先に読めるようにする。

## 出力

- 報告を作る前に `references/template.md` を全文読み、その構造を使う。見出し名、項目名、順序、箇条書き、表などの表現は固定せず、同じ意味を読み取れる表現を使ってよい。
- `references/template.md` をユーザー向け要約と詳細Markdownの必要情報・構成例の正本とする。固定文字列やMarkdown構造への一致を正しさの条件にしない。
- ユーザー向けメッセージでは、結果、ユーザーの判断・操作の要否、主要な検証、未検証事項・blocking・残リスク、ある場合は詳細成果物の参照先をこの順で短く示す。
- 通常のユーザー向けメッセージは4から6行程度を目安とする。review deadline、retry、full-diff review count、ADR / architecture gateなどの詳細は、要判断、blocking、gap、残リスクの意味を変える場合だけメッセージに展開し、それ以外は必要な追跡証拠へ保持する。
- Candidate ID、Evidence Ledger、review Entry ID、digest、origin、lens、matrix cellなどの追跡情報はtask-localに維持するが、通常のユーザー向けメッセージへ全項目を展開しない。完了判断に影響するgapやblockingの意味だけを要約する。
- 詳細成果物は、根拠が多く短いメッセージで正確さを保てない、後から参照する価値がある、またはCandidateや複数reviewの追跡情報を保存する必要がある場合だけtask-localなMarkdownとして作る。小規模でメッセージだけで正確に報告できる作業には作らない。
- HTMLは図表または操作性が必要な場合だけ使い、既定はMarkdownとする。
- ユーザーの判断事項、blocking、未検証リスクは詳細成果物だけに置かず、必ずユーザー向けメッセージにも残す。
- Candidate verification resultが`mismatch`または`validation-gap`の場合はvalidation-onlyの意味境界を守り、substantive finding、approval、completion evidence、structural gate、Matrix coverage、review coverage、accepted risk、residual riskを表示しない。

## ルール

- behaviorまたはcontractを変更した場合は、対応する実行可能な契約を示す。追加・更新しない場合は理由を明記する。
- 対象behaviorまたは防ぐfailure modeを先に示し、各checkがどの期待を証明するか対応づける。
- 主要な回帰シナリオと、それを覆うtest / type / schema / static checkを示す。coverage gapは残リスクへ送る。
- 実装を通すために既存のtestやcontractを弱めていないことを確認し、意図したcontract変更は理由を明示する。
- pure refactorや機械変更では、新規testを一律に要求せず、既存の実行可能な契約が維持されることを確認する。
- docs / policy-only変更では、構文、参照、残存語彙、責務整合などの代替checkを示す。
- change、build、fixのすべての完了報告で、root sessionが判定した`Full-review gate`の`run`または`skip`と、その判定理由を明示する。このSkillは判定結果を報告するだけとし、gateを再判定しない。
- `Full-review gate=run`では、holistic complete-diff reviewの対象scopeと、`completed`、`unavailable`、`deadline exceeded`のいずれかの実施状況を示す。完了していない場合は、完了判断に残るvalidation gapを明示し、`skip`またはclean reviewとして扱わない。
- targeted reviewまたはspecialist reviewの要否と結果は、`Full-review gate`およびholistic complete-diff reviewの実施状況と区別して示す。前者の実施有無から後者の判定を推測させない。
- reviewを実施した場合はreview kind、scope、complete diffの確認有無、full-diff review回数、`blocking` status、accepted risk、validation gapを示す。full-diff review回数の正常値は一つの論理変更につき0回または1回とする。
- `Full-diff review count: 0`、reviewの要否、またはtargeted / specialist reviewの結果だけで`Full-review gate=skip`を表したことにしない。gate判定と理由を別に読み取れるようにする。
- Candidate固有のfield、source identity、Candidate preflight、失効判定、evidence status、Review Briefの意味は`contract-closure` Skillを参照し、このSkillで再定義または再計算しない。
- reviewを実施または開始した場合は、Review Briefのdeadline、deadline内の完了または超過、review再試行の有無と理由を区別して示す。Candidate-bound reviewではCandidate preflightも示す。timeoutをtoolまたはtransport failureとして扱わない。
- verified Candidateの追跡では、現行Candidateを識別するsource identityとraw diff digest、review contract、Candidate preflight、Candidate verification result、structural convergence gate / result、完了根拠となるcheck / review Entry ID、実行Candidate、origin、ledger status、definition delta、non-impact rationale、Matrix cellごとのcoverage status、lens、review済み・未確認cell、complete-diff reviewの有無をtask-localなEvidence Ledgerまたは条件を満たした詳細Markdownへ保持する。holistic findingでCandidateが変わった場合は、旧Candidateのholistic discovery Entry IDとimmutable resultをreview-cycle recordとして示し、現行Candidateのdirect check、targeted closure、影響するspecialist cellのcurrent Entry IDをFinal Candidate closure chainとして分ける。旧holistic entryを現行Candidateのcompletion evidenceとして表示しない。その他の非現行entryは、gapまたはcurrent evidenceの由来を説明するために必要なものだけ要約する。
- validation-only出力では、overall judgment、ユーザーの判断・操作の要否、review scope、complete-diff確認、blocking finding status、Candidate ID、Candidate preflight、Candidate verification result、Review Briefで割り当てられたReview Entry ID、verification evidence、validation gap、reviewed cells `none`だけを表示する。overall judgmentはsubstantive reviewが未評価であることを示し、Candidate verification自体の結果と混同しない。Review Entry IDを新規作成したり、Evidence Ledger entryとして扱ったりしない。Candidate verification-onlyを担当するreviewerは`Full-review gate`を再判定せず、root sessionが後続の完了報告で判定結果と必要情報を揃える。
- Candidateを使わない通常reviewでは、reviewの要否、scope、結果、`blocking` status、accepted risk、validation gapだけを示す。reviewを実施不要と判断した場合は理由を示す。
- sourceと実行可能な契約が食い違う場合はalignedとせず、意図確認と残作業を報告する。
- ADRとarchitecture文書の判定規則は`AGENTS.md`を正本とし、このSkillへ条件を複製しない。
- 実行していないcheckを成功扱いせず、生log、大きなdiff、repo外pathを出力しない。
