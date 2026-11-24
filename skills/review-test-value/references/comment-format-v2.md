# Test Value Comment v2

対応するtest declarationの直前に、言語の行コメントで`@test-value v2`から`@end-test-value`までのTOMLを置く。結合と宣言範囲は[source adapter契約](source-adapters-v1.md)に従う。

blockと宣言の間に空行を入れず、同じindentで直接隣接させる。複数blockの隣接や未結合blockを拒否し、metadataがない場合に本文から補完しない。文字列内のmetadata風の記述をコメントblockとして扱わず、未知のmarker versionも診断対象にする。

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

`lifecycle`はそのtestの扱いを記すfieldであり、維持契約や保持価値の証明ではない。[Skillのreview観点](../SKILL.md#一回のreviewで確認する観点)で確認する。

任意の`risk_tags`は`security`、`authentication`、`authorization`、`billing`、`irreversible-data-loss`、`privacy`の配列とする。reviewerの追加review要否はmetadataだけで自動決定せず、親エージェントが対象コードとreview結果から判断する。

| lifecycle | 条件 |
| --- | --- |
| `permanent` | `expires_on`、`review_when`、`remove_when`を禁止する。 |
| `characterization` | `expires_on`または非空の`review_when`を必要とする。`remove_when`はこの条件の代用にならない。 |
| `ephemeral` | 非空の`remove_when`を必要とする。 |

`expires_on`は`YYYY-MM-DD`形式の日付とする。未知field、不正型、未知enumを補正しない。抽出器はsourceとmetadataの構文・schema・対応付けを検証し、意味上の価値や保持方針はreviewerへ委ねる。

## oracleの根拠参照

`ref`は期待値を裏付ける仕様・契約・資料を、第三者が辿れる形で示す。「ユーザー依頼」「合意済み」等の会話上の説明だけで代用せず、要求ID等を使う場合も正本へ解決できるようにする。根拠が見つからない場合は不足を明示して確認し、参照先や判断理由を作らない。

文書を参照する場合はpathまたはURLに加え、claimの根拠となる見出し・anchor・節番号を優先して示す。適切な見出しがなければ行番号等で箇所を特定し、見出しが広すぎる場合も補足する。例は `docs/contracts/payment.md: 「再送時の請求」`。複数箇所が必要ならそれぞれ示し、参照先の変更で位置がずれた場合は更新する。文字列の構文検証と、参照先の実在・該当記述・claimの裏付けの確認は区別する。

## v1 metadata

既存sourceを読むため、抽出器はv1 markerも認識し、選択されたv1には`TEST_VALUE_V2_REQUIRED` diagnosticを返す。v1の`failure_mode`を推測でv2 fieldへ分割しない。現在のtestをreviewへ渡す前に、必要な`fault`、`observable`、`observation_boundary`を人が確認してv2へ移行する。
