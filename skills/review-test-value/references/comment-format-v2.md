# Test Value Comment v2

候補版のmetadata契約である。有効化の前提と状態は[有効化runbook](../../../docs/runbooks/activate-test-value-review.md)を確認する。

対応するtest declarationの直前に、言語の行コメントで`@test-value v2`から`@end-test-value`までのTOMLを置く。結合と宣言範囲は既存の[source adapter契約](source-adapters-v1.md)を維持する。

```python
# @test-value v2
# kind = "invariant"
# claim = "同じkeyの再送では請求件数が増えない"
# oracle = { type = "contract", ref = "PAYMENT-004" }
# fault = "再送を新規請求として永続化する"
# observable = "APIから取得した請求件数"
# observation_boundary = "public-boundary"
# scope = "payment-api"
# lifecycle = "permanent"
# @end-test-value
def test_retry_preserves_charge_count():
    ...
```

`kind`、`claim`、`oracle`、`scope`、`lifecycle`の意味とenumはv1から維持する。`oracle`は`type`と非空の`ref`だけを持つinline tableとする。参照文字列の存在は参照先の検証済み証拠ではない。

`fault`は失敗させるべき具体的な欠陥、`observable`はassertionが直接読む値、状態、eventまたはartifactであり、いずれも非空文字列を必須とする。`failure_mode`は使用しない。`observation_boundary`は`consumer`、`public-boundary`、`component-behavior`、`declaration`、`implementation`のいずれかを必須とする。

任意の`impact`には下流の影響を記載できる。直接観測を主張するfieldではないため、間接的な影響であることだけをoverclaimとは判定しない。`distinction`は既存checkとの違いを表す非空文字列である。

任意の`risk_tags`は`security`、`authentication`、`authorization`、`billing`、`irreversible-data-loss`、`privacy`の配列とする。親workflowのriskを解除する用途には使えない。

| lifecycle | 条件 |
| --- | --- |
| `permanent` | `expires_on`、`review_when`、`remove_when`を禁止する。 |
| `characterization` | `expires_on`または非空の`review_when`を必要とする。`remove_when`はこの条件の代用にならない。 |
| `ephemeral` | 非空の`remove_when`を必要とする。 |

`expires_on`は実在する日付を表す`YYYY-MM-DD`文字列とする。期限や削除条件の記載は削除権限でも、条件未成立の証拠でもない。未知field、不正型、未知enumを補正しない。

## v1からの移行

v1の読取りは、そのtask内で対象sourceをv2へ移行するために限る。path modeとGit modeの両方で、対象v1は`TEST_VALUE_V2_REQUIRED`とexit `1`を返す。読めたv1を審査packetへ渡してはならない。

実際のtest本文とaccepted contractを確認し、`fault`、`observable`、`observation_boundary`を記述してsourceを更新する。同じ選択条件で再抽出し、exit `0`になってからv2審査へ進む。情報不足や編集権限不足で移行できなければ停止する。`failure_mode`の分割や推測による自動変換、対象外v1の一括移行は行わない。
