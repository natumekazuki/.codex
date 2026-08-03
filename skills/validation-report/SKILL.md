---
name: validation-report
description: 実装後に、変更したsourceと実行可能な契約、実行・未実行の検証、ADR / architecture gate、残リスクを短く揃えて報告する。
---

# Validation Report

## 目的

- 実行したcheckだけでなく、変更した現在状態と期待状態の整合を確認する。
- 未実行項目やknowledge placementの未解決を隠さず、完了判断に必要な情報を揃える。

## 出力

- 報告を作る前に `references/template.md` を全文読み、その構造を使う。
- `references/template.md` を出力形式の正本とする。
- Candidate Definitionを使わない作業では通常作業用テンプレートだけを使い、Candidate、Evidence Ledger、origin、lens、matrix cellの欄や空表を出力しない。
- Candidate-boundな作業でCandidate verification resultが`verified`の場合は、通常作業用テンプレートにverified Candidate拡張を追加する。task-localなEvidence Ledgerは省略せず維持し、user-facingな報告では現行Candidateの完了判断に使うevidenceとgapを要約する。
- Candidate verification resultが`mismatch`または`validation-gap`の場合は、通常作業用テンプレートやverified Candidate拡張を使わず、validation-onlyテンプレートだけを使う。substantive finding、approval、completion evidence、structural gate、Matrix coverage、review coverage、accepted risk、residual riskを表示しない。

## ルール

- behaviorまたはcontractを変更した場合は、対応する実行可能な契約を示す。追加・更新しない場合は理由を明記する。
- 対象behaviorまたは防ぐfailure modeを先に示し、各checkがどの期待を証明するか対応づける。
- 主要な回帰シナリオと、それを覆うtest / type / schema / static checkを示す。coverage gapは残リスクへ送る。
- 実装を通すために既存のtestやcontractを弱めていないことを確認し、意図したcontract変更は理由を明示する。
- pure refactorや機械変更では、新規testを一律に要求せず、既存の実行可能な契約が維持されることを確認する。
- docs / policy-only変更では、構文、参照、残存語彙、責務整合などの代替checkを示す。
- reviewを実施した場合はreview kind、scope、complete diffの確認有無、full-diff review回数、`blocking` status、accepted risk、validation gapを示す。full-diff review回数の正常値は一つの論理変更につき0回または1回とする。
- Candidate固有のfield、source identity、Candidate preflight、失効判定、evidence status、Review Briefの意味は`contract-closure` Skillを参照し、このSkillで再定義または再計算しない。
- reviewを実施または開始した場合は、Review Briefのdeadline、deadline内の完了または超過、review再試行の有無と理由を区別して示す。Candidate-bound reviewではCandidate preflightも示す。timeoutをtoolまたはtransport failureとして扱わない。
- verified Candidate拡張では、現行Candidateを識別するsource identityとraw diff digest、review contract、Candidate preflight、Candidate verification result、structural convergence gate / result、完了根拠となるcheck / review Entry ID、実行Candidate、origin、ledger status、definition delta、non-impact rationale、Matrix cellごとのcoverage status、lens、review済み・未確認cell、complete-diff reviewの有無を表示する。holistic findingでCandidateが変わった場合は、旧Candidateのholistic discovery Entry IDとimmutable resultをreview-cycle recordとして示し、現行Candidateのdirect check、targeted closure、影響するspecialist cellのcurrent Entry IDをFinal Candidate closure chainとして分ける。旧holistic entryを現行Candidateのcompletion evidenceとして表示しない。その他の非現行entryは、gapまたはcurrent evidenceの由来を説明するために必要なものだけ要約する。
- validation-only出力では、overall judgment、review scope、complete-diff確認、blocking finding status、Candidate ID、Candidate preflight、Candidate verification result、Review Briefで割り当てられたReview Entry ID、verification evidence、validation gap、reviewed cells `none`だけを表示する。Review Entry IDを新規作成したり、Evidence Ledger entryとして扱ったりしない。
- Candidateを使わない通常reviewでは、reviewの要否、scope、結果、`blocking` status、accepted risk、validation gapだけを示す。reviewを実施不要と判断した場合は理由を示す。
- sourceと実行可能な契約が食い違う場合はalignedとせず、意図確認と残作業を報告する。
- ADRとarchitecture文書の判定規則は`AGENTS.md`を正本とし、このSkillへ条件を複製しない。
- 実行していないcheckを成功扱いせず、生log、大きなdiff、repo外pathを出力しない。
