# Review

必要な内容だけを使う任意の骨格。判断・保存・対応管理は共通`AGENTS.md`の「条件付き参照」から解決した`~/.codex/docs/guides/development.md`に従う。必要な判断材料は保ち、全欄の記入や固定の応答形式は要求しない。

## Review Scope

- Target: <repository、対象commit・差分範囲や文書。未コミット変更を含む場合はその範囲>
- Reviewer: <review担当。自己確認・独立review等を区別する>
- Focus: <今回の確認対象・観点>

## Overall Judgment

- <reviewの結論、完了・中断、統合可否と根拠。指摘ゼロと未確認、公開可否や操作権限を区別する>

## Findings

<具体的な問題がある場合だけ記載する。問題や未確認事項のない欄は省く。>

### <finding-id>: <title>

- Location: <file and line, symbol, or other precise anchor>
- Impact: <observable consumer or system impact>
- Evidence: <source, executable contract, or observed behavior>
- Disposition: <統合前の対応／後追い先／重複／不採用／未確認と根拠。優先度とは分ける>
- Remediation: <minimal direction>
- Status: <現在の対応状況。未対応／修正済み・未検証／確認済み等>
- Resolution: <対応内容と対象commit・差分等、実施した確認と結果・未確認>
- Handoff: <必要な場合だけ、登録済みの引継ぎ先。未登録・権限待ちはその旨>

## Validation Gaps

- <未確認の範囲、必須確認・統合・公開への影響>

## Residual Risks

- <残る問題と扱い>
