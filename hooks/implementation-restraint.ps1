#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@"
Implementation restraint（正本: AGENTS.md）:
- 現在の要求・契約・具体的な不具合に根拠を持つ、最も単純な完全解を作る。不要な抽象化、互換層、fallback、管理文書、testや無関係な整理を増やさない。
- 失敗を成功に見せない。必要な確認で終え、明示要求、入力検証、安全性、accessibility、データ保護を保つ。
- 委譲はLunaを優先する（調査・データ取得・範囲が明確な実装・検証）。SolはLunaで未解決の具体的な問題、専門審査の指定、ユーザーの明示指定に限る。Astraは非Astra親から、難しい設計判断や未解決の問題を範囲を絞って委譲する場合に使える。Astra親からAstra子は起動しない。Luna・Solの形式的な試行を前提にしない。親が設計・統合を担い、子へ必要な文脈だけ渡す。専門審査は該当Skillに従い、形式的なLuna試行や不要な分業を増やさない。
- review-test-valueでは、testの新規追加・意味変更・削除・移設をGit差分から抽出し、通常のread-only reviewへ渡す。対象を都合よく選び直したり、審査を通すために契約を弱めたりしない。
"@
