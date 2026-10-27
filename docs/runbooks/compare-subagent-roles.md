# 指示構成の小さな比較と導入

本書は、本repositoryが配布する指示・model構成を比較して導入する際の検証手順である。通常作業の委譲ルールは[Subagent Review Boundary](../architecture/subagent-workspace.md)が正本である。

同じ開始commit、親model、effort、利用toolで、代表作業を別の新規sessionから実行する。model変更と指示変更の効果を混同せず、productionへの外部副作用を発生させない。

小さな通常修正、testの新規・意味変更、独立した調査と小実装から代表例を選ぶ。成果の正しさ、重要な見落とし、人の手直し、不要なcode・test・document、経過時間、観測できる実使用量を見る。文字数やtool call数だけで優劣を決めない。

結果は開始commit、比較対象、OS／CLI／model、実施内容、集計を短く記録する。少数例から普遍的な優位や週枠の保証を断定せず、secret、private path、生transcriptを公開しない。新たなbenchmark frameworkや常設DBは作らない。

通常のtest変更では、`review-test-value`の決定論的な抽出結果と、親から選択したサブエージェントへ渡したread-only reviewの結果を確認する。抽出、review、修正の結果を同じtaskの変更状態へ結び付け、モデル実行の成功だけで完了扱いにしない。

これは導入確認であり、全taskに毎回要求する一覧ではない。offline checkとreview結果を区別し、既知の差分だけをレビュー可能な形で戻す。ユーザーworktreeをresetしない。

## 4 model構成の適用確認

配布元の編集とlive配置を分ける。配置時は`config.example.toml`の必要section、`config/agents.example.toml`の4 role、`agents/`、使用する`astra.config.toml`／`sol.config.toml`、hookと関連文書を同じ有効なCodex homeへ揃える。認証・MCP binding・無関係な設定は上書きしない。

1. TOMLの構文、role参照先、親・一般child・roleのmodelとeffortをREADMEの表と照合する。hookの出力、4モデル以外の明示指定の拒否、Astra→Astraの拒否、Terraへの再通知matcher、`fork_turns = none`と他引数の保持を確認する。
2. TerraではCodex CLI 0.159.0以降を使う。配置後の新規sessionで、`gpt-6.1-sol`、`gpt-6-luna`、`gpt-6.1-terra`、`gpt-6-astra`の提供状態、4 roleの実model・effort、hookのtrust・到達を確認する。API公開やmodel cacheへの掲載だけを、当該環境での実起動成功の証拠にしない。
3. 許可された代表作業で、通常作業と一般childの既定がSol、手順・期待結果がほぼ決まっている作業がLuna、明確な入力・完了条件を持つ視覚・文章・局所修正がTerraの候補、高度な判断が必要な作業が非Astra親からAstraへの限定委譲になることを確認する。taskの短さ・単価や下位modelの形式的な試行を選択基準にしない。必須のtest価値reviewや実描画の確認は既存の契約どおり実施する。

TerraとSolの比較は同じ入力・effort・tool・完了条件で始め、正しさ・見落とし・手直し・全体時間・観測できる使用量を確認する。effortを変える比較は同一modelで分け、maxを初期設定にしない。旧modelを比較対象やfallbackとして復帰させない。

上記は手順であり、適用・実測の完了記録ではない。API単価や公式評価だけで、実作業の速度、再作業量、Codex消費枠の改善を実証したとは扱わない。
