---
name: present-review-results
description: reviewer、targeted_reviewer、slice_reviewer、fast_reviewer、または別sessionの通常のcode review、PR review、実装差分reviewで、Critical、High、Medium、Lowのseverityとclassificationを持つfindingをユーザーへ新たに提示するとき、探索範囲、判定、修正要否を変えずに表記と並びを統一する。audit-codex-work-quality、review-test-valueなど固有の出力契約を持つ専門Skillには適用しない。既存結果のseverity語彙の変換や再整形、レビュー方法、findingの採否、risk acceptanceを決める用途には使わない。
---

# Review Result Presentation

## 境界

- active review contractとreview resultがseverityに`Critical`、`High`、`Medium`、`Low`のいずれかを採用している場合に、結果をユーザーへ初めて提示する段階だけで適用する。reviewのscope、観点、探索、finding、severity、classification、judgmentを追加、削除、変更しない。
- `audit-codex-work-quality`、`review-test-value`など、固有の出力契約を持つ専門Skillの結果には適用せず、そのSkillの出力契約を維持する。
- 別のseverity語彙で既に提示された結果は適用対象外とし、`P0`〜`P3`と`Critical`〜`Low`を相互変換しない。
- 根拠が不足するfieldを推測で埋めず、validation gapへ分離する。
- reviewerが提案した分類は`Proposed classification`、root sessionなどのownerが確定した分類は`Classification`と表示し、確定度を変えない。
- repository固有またはrole固有の追加sectionは維持し、共通sectionの後へ置く。

## 語彙

- このSkillを適用するreviewは、severityを`Critical`、`High`、`Medium`、`Low`のいずれかで提示し、この順で並べる。`P0`、`P1`、`P2`、`P3`や独自の同義語をseverityとして出力せず、既存labelから変換もしない。
- severityはsupported scopeで到達した場合のimpactを表し、完了を止めるかどうかや修正順序の代用にしない。
- classificationは現在のreview contractの語彙をそのまま使う。このrepositoryでは`blocking`、`risk-candidate`、`non-material`、`invalid`を使い、severityと混同しない。
- classificationが未確定または証拠不足なら、現在のreview contractに従って未確定であることを明示する。

## 出力

次の順序を使う。

```markdown
## Overall Judgment

- <judgment required by the active review contract>

## Findings

### [<Critical | High | Medium | Low>] <title>

- <Proposed classification | Classification>: `<classification>`
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
- reviewer roleは`Proposed classification`、root sessionなど分類を確定するownerは`Classification`を使う。
- 複数findingはseverity順に並べる。同じseverityではreview contractが定めるblocking状態と提示順を維持する。
- locationは利用中の出力surfaceに適した形式で示し、参照可能な位置情報を落とさない。
- finding本文とvalidation gap、residual risk、hardening candidateを混在させない。
- 冗長なreview経緯や生logを加えず、判断に必要な根拠と影響を残す。
