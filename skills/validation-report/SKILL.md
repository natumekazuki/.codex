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
- `references/template.md` を出力形式の正本とし、該当事項がない欄も省略しない。

## ルール

- behaviorまたはcontractを変更した場合は、対応する実行可能な契約を示す。追加・更新しない場合は理由を明記する。
- 対象behaviorまたは防ぐfailure modeを先に示し、各checkがどの期待を証明するか対応づける。
- 主要な回帰シナリオと、それを覆うtest / type / schema / static checkを示す。coverage gapは残リスクへ送る。
- 実装を通すために既存のtestやcontractを弱めていないことを確認し、意図したcontract変更は理由を明示する。
- pure refactorや機械変更では、新規testを一律に要求せず、既存の実行可能な契約が維持されることを確認する。
- docs / policy-only変更では、構文、参照、残存語彙、責務整合などの代替checkを示す。
- reviewを実施した場合はreview kind、scope、complete diffの確認有無、full-diff review回数、`blocking` status、accepted risk、validation gapを示す。
- Candidate-boundなcheckとreview stepでは、Candidate DefinitionとEvidence Ledgerを分けて記録する。Entry ID、kind、実行Candidate ID、immutable result、source identity modeとvalue、Candidate作成時に固定したbase commit / tree OID、read-only verification recipe、creator tree OIDの有無、review contract、specialist lens、review済み・未確認matrix cell、ledger statusを各stepへ対応付ける。`definition-delta non-impact confirmation`では元entryのEntry IDとCandidate ID、reviewed definition delta、non-impact rationaleも独立fieldとして示す。説明用のbase ref labelを再解決して完了証拠を生成しない。
- checkやreview結果の追加、既存cellのcoverage status更新、構造収束gateの結果更新だけではCandidate IDを変更しない。source identityを先に判定し、source identity変更ではreview contractも同時に変わった場合を含め、旧Candidateのreviewとsource依存checkを`superseded`として示し、`unconfirmed`への移行や再関連付けをしない。source identityが変わらないreview contractだけの変更では、旧entryを元Candidateに保持し、影響するcellを新Candidate上で`unconfirmed`として示す。holistic review対象にはexact source stateとcomplete raw diffに加え、accepted anchor、その契約上の意味、Invariant、supported scopeを含め、この対象が変わる場合は新Candidate上でholistic reviewを再実行した証拠を示す。影響しないreview-contract-only evidenceも自動継承せず、元entryのEntry IDとCandidate ID、確認した定義差分、非影響の根拠を持つ独立した確認entryを新Candidate上の行として示す。source identity変更後のdelta非影響確認も、新Candidate上で新しく得たreview evidenceとして示す。完了根拠には現行Candidateへ紐付く`current`の行だけを使う。
- Candidateを使わない通常reviewでは、Candidate、Candidate Definition、Evidence Ledger、matrix cellの欄を`not applicable — review not Candidate-bound`とする。reviewを実施不要と判断した場合は理由を示す。
- sourceと実行可能な契約が食い違う場合はalignedとせず、意図確認と残作業を報告する。
- ADRとarchitecture文書の判定規則は`AGENTS.md`を正本とし、このSkillへ条件を複製しない。
- 実行していないcheckを成功扱いせず、生log、大きなdiff、repo外pathを出力しない。
