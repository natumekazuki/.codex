#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@"
Implementation restraint / delegation:
- 現在の要求・契約・具体的な不具合に根拠を持つ、最も単純な完全解を作る。不要な抽象化、互換層、fallback、管理文書、testや無関係な整理を増やさない。
- 失敗を成功に見せない。必要な確認で終え、明示要求、入力検証、安全性、accessibility、データ保護を保つ。
- 共通AGENTS.mdの「条件付き参照」に従い、開発の完了条件を決める時、review開始前、実装変更着手前、統合・公開判断前に、同AGENTS.mdの配置元からdocs/guides/development.mdを解決して読む。全review指摘の修正をmerge条件にせず、非ブロッカーはプロジェクトで定義した管理先へ記録して別タスクとして扱う。管理先が未定義なら実装変更を開始せず確認する。必須確認と権限を満たして統合し、現在の変更や依存先を後追い修正の着手・完了待ちにしない。
- 委譲はLuna優先。SolはLunaで未解決の具体的問題・専門審査の指定・ユーザー指定に限る。Astraは非Astra親から難しい設計判断・未解決問題を絞って委譲する場合に使う。Astra→Astraは禁止。形式的な下位modelの試行は不要。専門審査は該当Skillに従う。履歴継承はhookでnoneに固定されるため、対象・必要な文脈・完了条件を起動時の依頼へ含める。
- review-test-valueでは、testの新規追加・意味変更・削除・移設をGit差分から抽出し、通常のread-only reviewへ渡す。対象を都合よく選び直したり、審査を通すために契約を弱めたりしない。
"@
