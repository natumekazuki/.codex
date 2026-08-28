# Test Value Comment Format v1

## Binding

- 対応するtest declarationは[source-adapters-v1.md](source-adapters-v1.md)に従う。
- `@test-value v1`から`@end-test-value`までを同じindentの連続した行コメントとして書く。
- 終了markerの直後へ、空行を挟まず最初のdecorator、attribute、またはtest declarationを置く。
- payloadは言語固有の行コメントprefixと直後の空白一つを除去した後、TOMLとして成立させる。
- 一つのtest declarationへ複数blockを付けない。

行コメントprefixはPythonが`#`、TypeScriptとC#が`//`である。block commentとdoc commentはmetadataとして扱わない。

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

```typescript
// @test-value v1
// kind = "invariant"
// claim = "同一keyによる再試行で請求件数が1件を超えない"
// oracle = { type = "contract", ref = "PAYMENT-004" }
// failure_mode = "応答喪失後の再送で請求を二重に永続化する"
// scope = "payment-api"
// lifecycle = "permanent"
// @end-test-value
test("retry after response loss", async () => {
  // ...
});
```

```csharp
// @test-value v1
// kind = "invariant"
// claim = "同一keyによる再試行で請求件数が1件を超えない"
// oracle = { type = "contract", ref = "PAYMENT-004" }
// failure_mode = "応答喪失後の再送で請求を二重に永続化する"
// scope = "payment-api"
// lifecycle = "permanent"
// @end-test-value
[Fact]
public async Task RetryAfterResponseLoss()
{
    // ...
}
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

`oracle`はinline tableのkey-valueとして書く。通常tableの`[oracle]`や`oracle.type`のようなdotted keyでは書かない。

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

v1は安定IDを持たない。blockは言語別の隣接規則でtest declarationへ結合する。一つの抽出結果かつ同じsource revision内では、`source.path`と`source.declaration_start_line`の組をrecord locatorとし、この組は一意である。`source.symbol`は人間向けの表示と説明に使う値であり、一意性を持たないためrecord keyに使わない。record locatorをsourceの編集、移動、renameをまたぐ恒久identityとして扱わない。
