#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@"
Implementation restraint（正本: AGENTS.md）:
- 現在の要求・契約・具体的な不具合に根拠を持つ、最も単純な完全解を作る。不要な抽象化、互換層、fallback、管理文書、testや無関係な整理を増やさない。
- 失敗を成功に見せない。必要な確認で終え、明示要求、入力検証、安全性、accessibility、データ保護を保つ。
- testの新規追加・意味変更にはreview-test-valueの必須審査を適用し、削除・移設の解消確認も省かない。
"@
