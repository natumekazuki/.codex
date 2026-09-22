# 変更testの審査と保持

Codex自身が作業途中に選んだ変更も含め、Python／TypeScript／C#のtestを新規追加・意味変更・削除・移設する前に読む。専門手順はruntimeが通知する実pathの`review-test-value` Skillを使用し、ここへ複製しない。

- Python／TypeScript／C#のtestを新規追加・意味変更・削除・移設する場合は、task開始時のbaseからGit差分で対象recordを抽出し、`review-test-value`の観点を通常のread-only `general_luna` reviewへ渡して完了を確認する。審査やcheckを通すためだけに契約を弱めない。
- 今回の変更で削除・非表示にした処理や表示内容の不在だけを確認するために追加したtestは、変更完了を確認する一時検証として扱い、確認後に削除する。恒久保持する場合は、現在も有効な要求・契約、違反時の具体的な影響、既存checkで代替できない理由、CI・保守負担を継続して負う価値をtest付近のmetadata、レビュー記録、またはPR説明に明記する。「回帰対策」だけを理由にtestを残さない。
