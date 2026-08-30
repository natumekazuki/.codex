---
name: present-review-results
description: レビュー、code review、PR review、差分review、監査で得たfindingをユーザーへ提示または再整形するとき、探索範囲、判定、修正要否を変えずに、severity、classification、location、impact、evidence、remediation、validation gap、residual riskの表記と並びを統一する。レビュー方法、findingの採否、risk acceptanceを決める用途には使わない。
---

# Review Result Presentation

## 境界

- 完了したreviewの結果だけを整形する。reviewのscope、観点、探索、finding、severity、classification、judgmentを追加、削除、変更しない。
- 根拠が不足するfieldを推測で埋めず、validation gapへ分離する。
- reviewerが提案した分類は`Proposed classification`、root sessionなどのownerが確定した分類は`Classification`と表示し、確定度を変えない。
- repository固有またはrole固有の追加sectionは維持し、共通sectionの後へ置く。

## 語彙

- severityは`Critical`、`High`、`Medium`、`Low`だけを使い、この順で並べる。`P0`、`P1`、`P2`、`P3`や独自の同義語へ置き換えない。
- severityはsupported scopeで到達した場合のimpactを表し、完了を止めるかどうかや修正順序の代用にしない。
- classificationは現在のreview contractの語彙をそのまま使う。このrepositoryでは`blocking`、`risk-candidate`、`non-material`、`invalid`を使い、severityと混同しない。
- classificationが未確定または証拠不足なら、現在のreview contractに従って未確定であることを明示する。

## 出力

次の順序を使う。

```markdown
## Overall Judgment

- <judgment required by the active review contract>

## Findings

### [<Critical | High | Medium | Low>][<classification>] <title>

- Location: <file and line, symbol, or other precise anchor>
- Impact: <observable consumer or system impact>
- Evidence: <source, executable contract, or observed behavior>
- Remediation: <minimal direction, not an expanded implementation plan>

## Validation Gaps

- <gap or "none">

## Residual Risks

- <risk or "none">
```

- findingがない場合も`Findings`を省略せず、`none`と明記する。
- 複数findingはseverity順に並べる。同じseverityではreview contractが定めるblocking状態と提示順を維持する。
- locationは利用中の出力surfaceに適した形式で示し、参照可能な位置情報を落とさない。
- finding本文とvalidation gap、residual risk、hardening candidateを混在させない。
- 冗長なreview経緯や生logを加えず、判断に必要な根拠と影響を残す。
