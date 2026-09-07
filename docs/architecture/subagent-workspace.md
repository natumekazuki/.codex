# Subagent Execution Boundary

汎用`general_sol`と`general_luna`には、対象、必要な結果、権限を依頼ごとに渡す。調査だけの依頼では編集しない。編集・検証に必要な権限はruntimeから継承し、role文章をsandboxの代わりにしない。

同じworking treeで作業する場合は編集範囲と生成物の競合を避け、ユーザーと他の担当の変更を保護する。子は結果・根拠・実行した確認・未解決事項を親へ返し、親が統合と最終確認を行う。通常の成果返却に専用文書は不要である。

worktreeやcommit固定は具体的な隔離・再現の必要に応じて使う。全reviewへ一律に別worktreeを要求しない。

`test_value_luna`は単一意味reviewの専門境界を持つ。通常の子をforkして入力隔離の代わりにせず、[review-test-value](../../skills/review-test-value/SKILL.md)の実行経路へ渡す。metadata・test本文・必要なbounded contextをhostが一つのinputへまとめる。親履歴や一般hookを自動注入せず、modelにはtoolやrepository探索を公開しない。旧metadata/alignment/deepの分業は使用しない。
