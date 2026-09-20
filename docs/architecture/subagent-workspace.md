# Subagent Review Boundary

汎用`general_sol`と`general_luna`には、対象、必要な結果、権限を依頼ごとに渡す。調査だけの依頼では編集しない。履歴継承に頼らず、review依頼には主要動作、後続の依存、共通`AGENTS.md`の統合基準と、非ブロッカーを全件修正待ちにしないことを含める。

test価値reviewの抽出、`general_luna`への委譲、review観点、完了判断は[review-test-value](../../skills/review-test-value/SKILL.md)を正本とする。専用roleや独自のworker、scheduler、artifact storeは使わない。

同じworking treeで作業する場合は編集範囲と生成物の競合を避け、ユーザーと他の担当の変更を保護する。子は結果、根拠、実行した確認、未解決事項を親へ返し、親が統合と最終確認を行う。通常の成果返却に専用文書は不要である。

worktreeやcommit固定は具体的な隔離・再現の必要に応じて使う。全reviewへ一律に別worktreeを要求しない。

非ブロッカーは共通`AGENTS.md`に従って別の修正タスクとして扱い、その着手・完了を現在の変更の完了・統合条件にしない。
