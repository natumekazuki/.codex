# 指示構成の小さな比較と導入

同じ開始commit、親model、effort、利用toolで、代表作業を別の新規sessionから実行する。model変更と指示変更の効果を混同せず、productionへの外部副作用を発生させない。

小さな通常修正、testの新規・意味変更、独立した調査と小実装から代表例を選ぶ。成果の正しさ、重要な見落とし、人の手直し、不要なcode・test・document、経過時間、観測できる実使用量を見る。文字数やtool call数だけで優劣を決めない。

結果は開始commit、比較対象、OS／CLI／model、実施内容、集計と未確認範囲を短く記録する。少数例から普遍的な優位や週枠の保証を断定せず、secret、private path、生transcriptを公開しない。新たなbenchmark frameworkや常設DBは作らない。

通常のtest変更では、`review-test-value`の決定論的な抽出結果と、親から`general_luna`へ渡したread-only reviewの結果を確認する。抽出、review、修正の結果を同じtaskの変更状態へ結び付け、モデル実行の成功だけで完了扱いにしない。

これは導入確認であり、全taskに毎回要求する一覧ではない。offline checkとreview結果を区別し、既知の差分だけをレビュー可能な形で戻す。ユーザーworktreeをresetしない。

## GPT-6構成の適用確認

配布元の編集とlive配置を分ける。配置時は`config.example.toml`の必要section、`config/agents.example.toml`の3 role、`agents/`、使用する`astra.config.toml`／`sol.config.toml`、hookと関連文書を同じ有効なCodex homeへ揃える。認証・MCP binding・無関係な設定は上書きしない。

1. TOMLの構文、role参照先、親・一般child・roleのmodelとeffortをREADMEの表と照合する。hookの出力、3モデル以外の明示指定の拒否、Astra→Astraの拒否、`fork_turns = none`と他引数の保持を確認する。
2. 配置後の新規sessionで、`gpt-6-astra`、`gpt-6-sol`、`gpt-6-luna`の提供状態、3 roleの実model・effort、hookのtrust・到達を確認する。APIでの公開だけを、当該Codex環境で利用可能な証拠にしない。
3. 許可された代表作業で、Lunaの限定作業、Solの複雑な判断、非Astra親からのAstraへの限定委譲を確認する。必須のtest価値reviewはSkillの契約どおり実施する。未提供・未実行・失敗は別に報告し、許可された構成での実行結果を確認する。

上記は手順であり、適用・実測の完了記録ではない。API単価や公式評価だけで、実作業の速度、再作業量、Codex消費枠の改善を実証したとは扱わない。
