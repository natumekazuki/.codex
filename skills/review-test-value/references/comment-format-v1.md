# Test Value Comment Format v1

## Binding

- Pythonのmodule直下またはclass直下にある、名前が`test`で始まる`def`または`async def`へ付ける。
- `@test-value v1`から`@end-test-value`までを同じindentの連続した行コメントとして書く。
- 終了markerの直後へ、空行を挟まず最初のdecoratorまたはtest declarationを置く。
- payloadは行頭の`#`と直後の空白一つを除去した後、TOMLとして成立させる。
- 一つのtest declarationへ複数blockを付けない。

```python
class PaymentTests(unittest.TestCase):
    # @test-value v1
    # kind = "invariant"
    # claim = "同一のidempotency keyによる再試行で請求件数が1件を超えない"
    # oracle = { type = "contract", ref = "PAYMENT-004" }
    # failure_mode = "決済成功後の応答喪失を受けた再送で二重請求される"
    # scope = "payment-api"
    # lifecycle = "permanent"
    # distinction = "通常の重複送信ではなく、決済成功後の応答喪失を扱う"
    # @end-test-value
    def test_retry_after_response_loss(self):
        ...
```

長い値にはTOMLの複数行文字列を使う。

```python
# claim = """
# 応答を受信できなかったクライアントが同じidempotency keyで再送しても、
# 永続化された請求件数は1件のままである
# """
```

## Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `kind` | yes | `contract`、`invariant`、`regression`、`security`、`reference`、`compatibility` |
| `claim` | yes | testが成立または不成立を観測できる単一の主張 |
| `oracle` | yes | `type`と`ref`だけを持つinline table |
| `failure_mode` | yes | testが検出する具体的な欠陥と観測可能な影響 |
| `scope` | yes | 検証対象となる安定した境界 |
| `lifecycle` | yes | `permanent`、`characterization`、`ephemeral` |
| `distinction` | no | 近いtestと異なる入力、状態遷移、観測点、failure timing |
| `expires_on` | conditional | `characterization`の見直し日。`YYYY-MM-DD` |
| `review_when` | conditional | `characterization`の見直し条件 |

`characterization`には`expires_on`または`review_when`を一つ以上書く。他のlifecycleでは両fieldを書かない。

`oracle.type`は次のいずれかとする。

- `contract`
- `schema`
- `adr`
- `issue`
- `incident`
- `reference-model`
- `characterization`

全文字列fieldへ空白だけの値を書かない。unknown field、unknown enum、型不一致を抽出器が補正することはない。

## Identity

v1は安定IDを持たない。blockは隣接規則でtest declarationへ結合し、抽出recordはrepository相対pathとqualified symbolで識別する。この組をrenameをまたぐ恒久identityとして扱わない。
