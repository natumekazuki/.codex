#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@"
Implementation restraint / delegation:
- 現在の要求・契約・具体的な不具合に根拠を持つ、最も単純な完全解を作る。不要な抽象化、互換層、fallback、管理文書、testや無関係な整理を増やさない。
- 失敗を成功に見せない。必要な確認で終え、明示要求、入力検証、安全性、accessibility、データ保護を保つ。
- 委譲はLuna優先。SolはLunaで未解決の具体的問題・専門審査の指定・ユーザー指定に限る。Astraは非Astra親から難しい設計判断・未解決問題を絞って委譲する場合に使う。Astra→Astraは禁止。形式的な下位modelの試行は不要。専門審査は該当Skillに従う。履歴継承はhookでnoneに固定されるため、対象・必要な文脈・完了条件を起動時の依頼へ含める。
- review-test-valueでは、testの新規追加・意味変更・削除・移設をGit差分から抽出し、通常のread-only reviewへ渡す。対象を都合よく選び直したり、審査を通すために契約を弱めたりしない。
"@
