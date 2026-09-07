# Test Value Comment v2

対応するtest declarationの直前に、言語の行コメントで`@test-value v2`から`@end-test-value`までのTOMLを置く。結合と宣言範囲は[source adapter契約](source-adapters-v1.md)に従う。

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

`kind`、`claim`、`oracle`、`scope`、`lifecycle`は必須である。`oracle`は`type`と非空の`ref`だけを持つinline tableとする。参照文字列だけでは参照先の存在やclaimの裏付けを証明しない。

`fault`は失敗させるべき具体的な欠陥、`observable`はassertionが直接読む値、状態、eventまたはartifactであり、いずれも非空文字列を必須とする。`observation_boundary`は`consumer`、`public-boundary`、`component-behavior`、`declaration`、`implementation`のいずれかを必須とする。

任意の`impact`には下流の影響を記載できる。直接観測を主張するfieldではない。`distinction`は既存checkとの違いを表す非空文字列である。

任意の`risk_tags`は`security`、`authentication`、`authorization`、`billing`、`irreversible-data-loss`、`privacy`の配列とする。reviewerの追加review要否はmetadataだけで自動決定せず、親エージェントが対象コードとreview結果から判断する。

| lifecycle | 条件 |
| --- | --- |
| `permanent` | `expires_on`、`review_when`、`remove_when`を禁止する。 |
| `characterization` | `expires_on`または非空の`review_when`を必要とする。`remove_when`はこの条件の代用にならない。 |
| `ephemeral` | 非空の`remove_when`を必要とする。 |

`expires_on`は`YYYY-MM-DD`形式の日付とする。未知field、不正型、未知enumを補正しない。抽出器はsourceとmetadataの構文・schema・対応付けを検証し、意味上の価値や保持方針はreviewerへ委ねる。

## v1 metadata

既存sourceを読むため、抽出器はv1 markerも認識し、選択されたv1には`TEST_VALUE_V2_REQUIRED` diagnosticを返す。v1の`failure_mode`を推測でv2 fieldへ分割しない。現在のtestをreviewへ渡す前に、必要な`fault`、`observable`、`observation_boundary`を人が確認してv2へ移行する。
