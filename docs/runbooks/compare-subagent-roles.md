# 指示構成の小さな比較と導入

同じ開始commit、親model、effort、利用toolで、代表作業を別の新規sessionから実行する。model変更と指示変更の効果を混同せず、productionへの外部副作用を発生させない。

小さな通常修正、testの新規・意味変更、独立した調査と小実装から代表例を選ぶ。成果の正しさ、重要な見落とし、人の手直し、不要なcode・test・document、経過時間、観測できる実使用量を見る。文字数やtool call数だけで優劣を決めない。

結果は開始commit、比較対象、OS／CLI／model、実施内容、集計と未確認範囲を短く記録する。少数例から普遍的な優位や週枠の保証を断定せず、secret、private path、生transcriptを公開しない。新たなbenchmark frameworkや常設DBは作らない。

通常のtest変更では、`review-test-value`の決定論的な抽出結果と、親から`general_luna`へ渡したread-only reviewの結果を確認する。抽出、review、修正の結果を同じtaskの変更状態へ結び付け、モデル実行の成功だけで完了扱いにしない。

これは導入確認であり、全taskに毎回要求する一覧ではない。offline checkとreview結果を区別し、既知の差分だけをレビュー可能な形で戻す。ユーザーworktreeをresetしない。
