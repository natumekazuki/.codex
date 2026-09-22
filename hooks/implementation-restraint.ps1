#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@"
Implementation restraint / delegation:
- 現在の要求・契約・具体的な不具合に根拠を持つ、最も単純な完全解を作る。不要な抽象化、互換層、fallback、管理文書、testや無関係な整理を増やさない。
- 共通文書の参照先はユーザーhome直下の~/.codex/に固定する。~は実行環境のユーザーhomeを指し、読み取り前に絶対pathへ解決する。作業対象repositoryや配布元checkout、CODEX_HOMEによる別配置へ切り替えず、参照先が欠けても同名文書で代用しない。
- 複雑さは必要な保証への効果と継続負担で評価する。共有判断の不足・矛盾や方針・現行説明の変更を扱う時は、~/.codex/docs/guides/design-decisions.mdを読む。必要な調査・推奨案・草案まで自ら進め、未合意の判断の採否を確認する。草案を有効な方針とせず、権限・着手禁止を維持する。
- 失敗を成功に見せない。必要な確認で終え、明示要求、入力検証、安全性、accessibility、データ保護を保つ。
- 共通AGENTS.mdの「条件付き参照」に従い、開発の完了条件を決める時、review開始前、実装変更着手前、統合・公開判断前に、~/.codex/docs/guides/development.mdを読む。全review指摘の修正をmerge条件にせず、非ブロッカーはプロジェクトで定義した管理先へ記録して別タスクとして扱う。管理先が未定義なら実装変更を開始せず確認する。必須確認と権限を満たして統合し、現在の変更や依存先を後追い修正の着手・完了待ちにしない。
- 使用modelはgpt-6-astra、gpt-6-sol、gpt-6-lunaのみ。明確な範囲・判定基準を持つ調査、抽出、小実装、reviewはLuna、複雑な実装・debug・調査・判断を伴うreviewはSol、最難関の横断的推論・設計判断はAstraへ振り分ける。Solの選択にLunaの失敗を要求しない。Astra子は非Astra親から必要な問題を絞って委譲し、Astra→Astraは禁止。専門審査は該当Skillに従う。新modelが未提供なら旧modelへfallbackせず、親で可能な範囲を続け、必須委譲ができない場合は未実施として報告する。履歴継承はhookでnoneに固定されるため、対象・必要な文脈・完了条件を起動時の依頼へ含める。
- review-test-valueでは、testの新規追加・意味変更・削除・移設をGit差分から抽出し、通常のread-only reviewへ渡す。対象を都合よく選び直したり、審査を通すために契約を弱めたりしない。
"@
