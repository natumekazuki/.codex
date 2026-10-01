#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@"
Implementation restraint / delegation:
- SessionFolderが提供された開発・調査・設計・reviewでは、runtimeの実pathのsession-graph Skillを必ず使う。開始・再開・Compact後は現在のSession情報から共有pathを解決し、Skillと最新グラフを読む。新しい指示・訂正を先に記録・照合してから依存する作業を進め、状態の区切りと終了前に同期する。保存失敗を成功扱いしない。
- 現在の要求・契約・具体的な不具合に根拠を持つ、最も単純な完全解を作る。不要な抽象化、互換層、fallback、管理文書、testや無関係な整理を増やさない。
- 共通文書の参照先はユーザーhome直下の~/.codex/に固定する。~は実行環境のユーザーhomeを指し、読み取り前に絶対pathへ解決する。作業対象repositoryや配布元checkout、CODEX_HOMEによる別配置へ切り替えず、参照先が欠けても同名文書で代用しない。
- 複雑さは必要な保証への効果と継続負担で評価する。共有判断の不足・矛盾や方針・現行説明の変更を扱う時は、~/.codex/docs/guides/design-decisions.mdを読む。必要な調査・推奨案・草案まで自ら進め、未合意の判断の採否を確認する。草案を有効な方針とせず、権限・着手禁止を維持する。
- 失敗を成功に見せない。必要な確認で終え、明示要求、入力検証、安全性、accessibility、データ保護を保つ。
- 共通AGENTS.mdの「条件付き参照」に従い、実装を伴わない課題・対応予定の管理でも、~/.codex/docs/guides/development.mdと対象repositoryが明示する関連運用文書を読む。開発・review・リリース範囲の確定・統合・公開判断等の読込条件も同入口に従う。互換性境界や残件管理先の不足は、実際の変更影響と依存先を調べ、その判断に依存する変更・引継ぎだけを止める。独立した作業は進め、未合意の保護対象を独断で確定・廃止しない。必須確認と権限を満たして統合し、現在の変更や依存先を非ブロッカーの全件修正待ちにしない。
- 使用modelはgpt-6.1-sol、gpt-6-luna、gpt-6-astraのみ。基本は6.1 Sol、進め方・手順・期待結果がほぼ決まっている作業はLuna、高度な判断が要求される作業はAstraへ振り分ける。上位modelの選択に下位modelの失敗を要求しない。委譲前に~/.codex/docs/architecture/subagent-workspace.mdを読み、Astra子は非Astra親から必要な問題を絞って委譲する。Astra→Astraは禁止。専門審査は該当Skillに従う。指定modelが未提供なら旧modelへfallbackせず、親で可能な範囲を続け、必須委譲ができない場合は未実施として報告する。履歴継承はhookでnoneに固定されるため、対象・必要な文脈・完了条件を起動時の依頼へ含める。
- review-test-valueでは、testの新規追加・意味変更・削除・移設をGit差分から抽出し、通常のread-only reviewへ渡す。対象を都合よく選び直したり、審査を通すために契約を弱めたりしない。
"@
