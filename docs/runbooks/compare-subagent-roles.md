# 指示構成の小さな比較と導入

今回の比較は旧指示と候補指示を対象にする。同じ開始commit、Astra、effort、利用toolで2〜3件の代表作業を別の新規sessionから実行する。model変更と指示変更の効果を混同しない。比較のためにproductionへの外部副作用を発生させない。

小さな通常修正、testの新規・意味変更、独立した調査と小実装から代表例を選ぶ。成果の正しさ、重要な見落とし、人の手直し、不要なcode・test・document、経過時間、観測できる実使用量を見る。文字数やtool call数だけで優劣を決めない。

結果は開始commit、候補commit、OS／CLI／model、実施内容、集計と未確認範囲を短く記録する。少数例から普遍的な優位や週枠の保証を断定せず、secret、private path、生transcriptを公開しない。新たなbenchmark frameworkや常設DBは作らない。

## 導入確認

- 新規sessionで親Astra、一般child既定Sol、汎用Sol/Lunaと専門2roleのmodel・effort、Standard速度、実際の読込元を確認する。自己申告だけを証拠にしない。
- 通常の小修正には不要な職種別handoffや校正工程を足さず、明示的な文書推敲では任意Skillを利用できることを確認する。
- test変更は親・汎用子とも必須審査へ到達する。[専門runbook](activate-test-value-review.md)の同一候補の検証結果を再利用し、未完了ならliveへ部分配布しない。
- 再開・compactionで短い抑制と必須審査を保ち、専門workerへの入力混入を防ぐ。WithMateの正本・対象・revision・個別承認を維持する。

これは今回変更する入口の導入確認であり、全taskに毎回要求する一覧ではない。offlineのcheckと実モデル・新規sessionの結果を区別する。

## 適用と切戻し

検証済み候補のAGENTS、4role、Skill、hookを整合した単位で適用する。端末localのconfigは必要差分だけを反映し、MCP・認証・private設定を上書きしない。既存sessionと旧routingのlocal stateを一括削除しない。live変更には操作範囲への承認を得る。

Astraの利用量が厳しい場合は`codex --profile gpt56`で親をSolへ明示切替できる。同じ4role・短いルール・必須審査を維持する。審査の障害は親modelの変更で省略せず、BLOCKEDとして修復する。

適用変更を戻す場合は既知の差分だけをレビュー可能な形で戻す。v2利用後にv1専用extractorへ戻さず、未解決ledgerと必要な読取能力を保つ。ユーザーworktreeをresetしない。

## 2026-09-06の限定比較

Windows／Codex CLI 0.153.4で、同じfixture commit `d037268744e83273ebc01ee50295beb36cd7a47e`から4つの独立した新規runを実行した。起動指定はAstra/medium/Standard。旧AGENTSは`81b1ee7`、候補AGENTSのSHA-256は`4d5619a160358e1a595cd72719393002d6e1c9661f3ff8c23331576e772a898c`。両条件とも同じtool設定で、hook・Skill自動入力・multi-agentを無効にし、AGENTS本文の差だけを比較した。全構成の導入smokeや必須審査のE2Eを代替しない。

| 例 | 指示 | 結果 | 秒 | input tokens | cached input | output tokens |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 空白正規化の小修正 | 旧 | 正常、追加fileなし | 47.9 | 134396 | 110720 | 637 |
| 同上 | 候補 | 正常、追加fileなし | 74.3 | 154825 | 132352 | 843 |
| 空入力のread-only調査 | 旧 | 正答、変更なし | 16.2 | 43750 | 21632 | 137 |
| 同上 | 候補 | 正答、変更なし | 15.4 | 35411 | 17408 | 139 |

修正例は前後の空白除去と連続空白の単一ハイフン化を外側から確認し、調査例は空配列の合計が0である説明とsource不変を確認した。test追加とcommitは依頼していない。全runがexit 0、手直し不要だった。tokenはCLIのturn.completed実測値であり、subscriptionの請求額や週枠ではない。候補は修正例で時間・inputが増え、調査例で減った。各1回の小例なので、速度や利用量の改善は確定していない。
