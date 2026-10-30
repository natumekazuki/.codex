#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@"
Implementation restraint / delegation:
- 共通ルールの入口は~/.codex/AGENTS.md。~は実行環境のユーザーhomeへ解決し、作業対象repositoryや別配置で代用しない。入口の操作境界と条件付き参照に従い、作業に必要なguide・runtimeのSkillを読む。
- 追加前の削減・統合と、保守者が修正できる構造を優先する。設計の選択基準は~/.codex/docs/guides/design-decisions.md、開発・review・統合の判断は~/.codex/docs/guides/development.mdを正本とする。
- WithMate Session Graphの利用条件は共通入口に従い、runtimeのsession-graph Skillで必要な指示を依存作業前に保存する。記録を権限拡大や未実施の確認の代わりにしない。
- 委譲前に~/.codex/docs/architecture/subagent-workspace.mdを読む。使用modelはgpt-6.1-sol、gpt-6-luna、gpt-6.1-terra、gpt-6-astraのみ。選択・実効権限・履歴を継承しない依頼の条件は同guideに従う。
"@
