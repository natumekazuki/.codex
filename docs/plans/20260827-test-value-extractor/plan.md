# テスト価値コメント抽出Skill

## Goal

- テスト宣言へ隣接して記述された構造化された価値コメントとテスト本文を、AIによる推論を介さず再現可能なJSONへ変換する。
- AIは抽出済みJSONだけを入力として、価値コメントの妥当性とテスト本文との整合を審査できる。
- MVPの実装前に、コメント形式、テストとの結合規則、共通出力、failure mode、対象外を固定する。

## Accepted Contract

### Canonical owner

- テスト価値の主張は、テスト宣言へ直接隣接する`@test-value`コメントブロックが所有する。
- 抽出規則と構文検証は、Skillへ同梱する決定論的な抽出CLIが所有する。
- AIはコメントの補完、テスト宣言との対応付け、source rangeの決定を行わない。
- JSONはsourceとコメントから再生成できる派生物であり、正本としてrepositoryへ保存しない。

### Invariants

#### TVE-001: 一つの価値コメントは一つのテスト宣言だけに結合する

- Accepted anchor: ユーザー要求。AIは決定論的に抽出されたテストと、そのテストへ明示的に書かれた価値コメントを受け取る。
- Scope / owner: source adapterのコメント結合処理。
- Failure mode: コメントが別のテストへ誤結合され、AIが異なる主張と本文を審査する。
- Direct verification: 隣接、空行、decorator、同一indent、複数ブロックを含むfixtureで結合結果を検証する。
- Gate: ready。

#### TVE-002: 抽出器は意味を推論しない

- Accepted anchor: 抽出器の主体は決定論的な抽出であり、価値判断は下流AIが行う。
- Scope / owner: parser、validator、JSON projection。
- Failure mode: 欠落項目や曖昧な値を抽出器が補完し、作者が書いていない主張をAI入力へ混入する。
- Direct verification: 欠落、unknown field、不正enum、不正TOMLを入力し、補完せずdiagnosticを返すことを検証する。
- Gate: ready。

#### TVE-003: 同じ入力は同じJSONを生成する

- Accepted anchor: AI入力を決定論的に生成するというユーザー要求。
- Scope / owner: path正規化、source slice、metadata canonicalization、record順序、hash生成。
- Failure mode: OS、filesystem列挙順、改行コード、JSON key順序によってAI入力やhashが変わる。
- Direct verification: 入力順、CRLF / LF、Windows / POSIX形式のpath表現、parser diagnosticのUI cultureを変えてbyte-equivalentなJSONを検証する。
- Gate: ready。

#### TVE-004: 対応できないsourceを成功として扱わない

- Accepted anchor: 未確認事実を捏造せず、曖昧な結合を行わない。
- Scope / owner: source adapterとCLI exit status。
- Failure mode: syntax error、検出可能な未対応構文、境界外pathを黙って無視し、supported declarationを全件抽出できたように見せる。
- Direct verification: 各failure fixtureで安定したdiagnostic codeとnon-zero exitを検証する。
- Gate: ready。

#### TVE-005: 言語adapterは共通metadata契約を迂回しない

- Accepted anchor: Pythonに加えてC#とTypeScriptも同じ目的で扱うというユーザー要求。
- Scope / owner: 言語native parser、共通binding、metadata validator、JSON projection。
- Failure mode: adapterごとにコメントschemaやprojectionが分岐し、同じ価値コメントから異なる意味のAI入力を生成する。
- Direct verification: Python、TypeScript、C#の等価fixtureで同じmetadata objectとhashを生成し、言語固有fieldはresult-levelの`adapter`と`coverage`だけで表すことを検証する。
- Gate: ready。

#### TVE-006: 一つの抽出結果内でrecord locatorを一意にする

- Accepted anchor: 下流consumerが抽出recordを別のtestへ誤対応または上書きせず、一件ずつ審査できること。
- Scope / owner: source adapterと共通JSON projection。
- Failure mode: 人間向けのqualified symbolが衝突し、consumerが別testのreview結果を誤対応または上書きする。
- Direct verification: 同じpath内でqualified symbolが衝突するfixtureから、異なるdeclaration start lineを持つ二つのrecordを抽出し、pathとstart lineの組が一意であることを検証する。
- Gate: ready。

## Structured Comment Format v1

### Syntax

- ブロックの開始行を`@test-value v1`、終了行を`@end-test-value`とする。
- 開始行と終了行の間は、言語固有の行コメントprefixを除去した後にTOMLとして解釈する。
- Pythonでは行コメントprefixを`#`、TypeScriptとC#では`//`とし、prefix直後の半角空白を一つだけ除去する。
- ブロック全体は、結合対象となるテスト宣言または最初のdecorator / attributeと同じindentに置く。
- 終了行とテスト宣言または最初のdecorator / attributeの間へ、空行、通常コメント、別の文を置かない。
- 一つのテスト宣言へ複数の`@test-value`ブロックを結合しない。

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

長い値にはTOMLの複数行文字列を使える。

```python
# @test-value v1
# kind = "regression"
# claim = """
# 応答を受信できなかったクライアントが同じidempotency keyで再送しても、
# 永続化された請求件数は1件のままである
# """
# oracle = { type = "incident", ref = "INCIDENT-2026-014" }
# failure_mode = "再送を新規請求として扱い、請求を二重に永続化する"
# scope = "payment-api"
# lifecycle = "permanent"
# @end-test-value
def test_retry_after_response_loss():
    ...
```

### Fields

| Field | Required | Contract |
| --- | --- | --- |
| `kind` | yes | `contract`、`invariant`、`regression`、`security`、`reference`、`compatibility`のいずれか |
| `claim` | yes | テストが成立または不成立を観測できる単一の主張。空白だけの値は禁止する |
| `oracle` | yes | `type`と`ref`を持つinline table。現在の実装結果そのものを根拠にしない |
| `failure_mode` | yes | このテストが検出する具体的な欠陥と観測可能な影響。空白だけの値は禁止する |
| `scope` | yes | 検証対象となる安定した境界。空白だけの値は禁止する |
| `lifecycle` | yes | `permanent`、`characterization`、`ephemeral`のいずれか |
| `distinction` | no | 近いテストと異なる入力条件、状態遷移、観測点、failure timing |
| `expires_on` | conditional | `characterization`で`review_when`がない場合に必須。`YYYY-MM-DD` |
| `review_when` | conditional | `characterization`で`expires_on`がない場合に必須。見直し条件を記述する |

`oracle.type`はv1で次を許可する。

- `contract`
- `schema`
- `adr`
- `issue`
- `incident`
- `reference-model`
- `characterization`

`oracle.ref`は空白でない文字列とする。参照先の存在確認と内容抽出はv1のsource extractorに含めず、後続のoracle resolver候補とする。

unknown field、unknown enum、型不一致はerrorとする。抽出器は既定値を補わない。

v1は安定IDを持たない。コメントは隣接規則によってテスト宣言へ結合する。一つの抽出結果かつ同じsource revision内では、repository相対pathとdeclaration start lineの組を一意なrecord locatorとする。qualified symbolは人間向けの表示値であり、一意性を持たない。record locatorをsourceの編集、移動、renameをまたぐ恒久identityとして扱わない。

schema validatorはTOMLの構文だけでなく、root field、`oracle`内のfield、enum、文字列の非空白、`lifecycle`と見直しfieldの組合せを検証する。`expires_on`と`review_when`は`characterization`でだけ許可する。

## Source Binding v1

### Supported Python declarations

- module直下またはclass直下の`def`と`async def`を対象にする。
- 名前が`test`で始まる宣言をテスト候補とする。
- function内部にネストされた宣言は対象外とする。
- decorator付き宣言では、最初のdecoratorを宣言範囲の開始位置とする。
- パラメータ化されたテストは、runtime caseではなく一つのsource declarationとして抽出する。

この規則はPython source adapter v1の規則であり、pytestや`unittest`のruntime collectionを再現するとは主張しない。

名前が`test`で始まるnested functionなど、AST上で検出できるがsupported scope外の宣言は`TEST_DECLARATION_UNSUPPORTED`とする。`setattr`、metaclass、loopなどによる動的生成は網羅的に検出できないため、diagnosticを保証しない。出力の`coverage`でsource declarationだけを対象にした結果であることを明示する。

TypeScriptとC#のsupported declaration、framework構文、parameterization、対象外は`skills/review-test-value/references/source-adapters-v1.md`を正本とする。各native parserは宣言範囲と行コメントtokenを返し、TOML parse、schema validation、binding、projectionは共通CLIが行う。

### Python binding algorithm

1. ASTからsupported declarationとsource rangeを取得する。
2. 宣言の最初のdecorator、decoratorがなければ`def`の直前行を調べる。
3. 直前行が同一indentの`@end-test-value`である場合だけ、対応する`@test-value v1`まで連続した行コメントを逆向きに取得する。
4. 取得したpayloadをTOMLとしてparseし、v1 schemaで検証する。
5. ブロックがない場合もテスト候補自体は出力し、`metadata`を`null`、diagnosticを`TEST_VALUE_MISSING`とする。
6. 未結合の`@test-value`ブロックは`TEST_VALUE_UNBOUND`とする。

通常コメントやdocstringは構造化metadataへ昇格しない。これらはテストsource sliceに含まれる場合だけ、本文の一部としてAIへ渡す。

## Normalized Output v1

```json
{
  "schema_version": 1,
  "adapter": "python-source-v1",
  "coverage": "python-source-declarations-v1",
  "repository_root": ".",
  "tests": [
    {
      "source": {
        "path": "tests/test_payment.py",
        "symbol": "PaymentTests.test_retry_after_response_loss",
        "metadata_start_line": 4,
        "metadata_end_line": 12,
        "declaration_start_line": 13,
        "declaration_end_line": 25
      },
      "metadata": {
        "kind": "invariant",
        "claim": "同一のidempotency keyによる再試行で請求件数が1件を超えない",
        "oracle": {
          "type": "contract",
          "ref": "PAYMENT-004"
        },
        "failure_mode": "決済成功後の応答喪失を受けた再送で二重請求される",
        "scope": "payment-api",
        "lifecycle": "permanent"
      },
      "source_text": "def test_retry_after_response_loss(self):\n    ...\n",
      "source_hash": "sha256:...",
      "metadata_hash": "sha256:..."
    }
  ],
  "diagnostics": []
}
```

### Projection rules

- pathはrepository root相対のPOSIX区切りへ正規化する。
- 入力pathは正規化後のpath、source start line、symbolの順でsortする。
- 一つの抽出結果かつ同じsource revision内では、`source.path`と`source.declaration_start_line`の組を一意なrecord locatorとする。`source.symbol`はrecord keyに使わない。
- source textの改行はLFへ正規化する。Unicode normalizationは行わない。
- `source_hash`はLFへ正規化したUTF-8のsource textから算出する。
- `metadata_hash`はkey順を固定したcanonical JSONから算出する。
- `source_text`は言語adapterが返した最初のdecorator、attribute、またはtest callからdeclaration末尾までとし、構造化コメントブロックを含めない。
- `metadata_start_line`と`metadata_end_line`は開始markerと終了markerを含む。metadataがないrecordでは両方を`null`とする。
- `declaration_start_line`は最初のdecorator、attribute、またはtest callの行とする。
- JSONはUTF-8、`ensure_ascii=false`、固定key順、末尾改行一つで出力する。
- repository外を指すpathと、repository外へ解決されるsymlinkは拒否する。

## Diagnostics and Exit Status

v1では次の安定したdiagnostic codeを定義する。

- `SOURCE_OUTSIDE_ROOT`
- `SOURCE_DECODE_ERROR`
- `SOURCE_SYNTAX_ERROR`
- `TEST_VALUE_MISSING`
- `TEST_VALUE_DUPLICATE`
- `TEST_VALUE_UNBOUND`
- `TEST_VALUE_PARSE_ERROR`
- `TEST_VALUE_SCHEMA_ERROR`
- `TEST_DECLARATION_UNSUPPORTED`

各diagnosticは`code`、`path`、`line`、`message`を持つ。機械判定は`code`を使い、`message`の文面を契約にしない。

- exit `0`: error diagnosticなしで抽出した。
- exit `1`: sourceまたはmetadataのerror diagnosticを返した。取得できたrecordはJSONへ残す。
- exit `2`: CLI引数、I/O、内部処理の失敗により、信頼できる抽出結果を構築できなかった。

## Skill Boundary

Skillは次を行う。

1. repository instructionと対象frameworkを確認する。
2. 審査対象となる明示的なsource pathを選ぶ。
3. 抽出CLIを実行する。
4. error diagnosticがあれば、AI審査へ進まずsourceまたはコメントの修正対象として扱う。
5. errorのないtest recordをAIへ渡し、価値コメントの妥当性と本文との整合を審査する。

抽出CLIはAIを呼び出さない。AIのmodel、prompt、判定、cache、CI gateは別の責務とする。

## Scope

- 新しいSkillのtriggerとworkflowの定義。
- Python source adapter v1。
- TypeScript source adapter v1。
- C# source adapter v1。
- `@test-value v1`コメントblockのparseとvalidation。
- 明示されたrepository内pathからのtest record抽出。
- normalized JSON、hash、diagnostic、exit status。
- parser、binding、projection、diagnosticのexecutable contract。

## Out of Scope

- pytest、`unittest`などのtest runnerによるruntime collectionとの照合。
- 動的生成、metaclass、継承だけで生成されるテストの発見。
- JavaScript、Java、Go、Rust用adapter。
- Git diffからの対象test自動選択。
- oracle参照先の存在確認、内容抽出、hash生成。
- AI reviewerのmodel、prompt、出力schema、cache、CI gate。
- sidecar、価値ID、repository全体のmetadata migration。
- 既存テストへの一括導入とmerge policy。

## Steps

- [x] Skill名と配置を確定し、`skill-creator`のinitializerで`SKILL.md`、`agents/openai.yaml`、`scripts/`、`references/`を生成する。
- [x] コメント形式とnormalized outputのv1 schemaを、scriptとtest fixtureの正本へ落とす。
- [x] Python source adapterとCLIを実装する。
- [x] parser、binding、projection、diagnosticを直接検証するtestを追加する。
- [x] Skill workflowからCLIを呼び、抽出されたrecordだけをAI審査へ渡す。
- [x] このplanの定義と実装済みschema、source、testの差を確認し、長期判断をADR-0020へ移す。
- [x] TypeScript Compiler APIによるJest、Vitest、Playwright形式のsource adapterを追加する。
- [x] RoslynによるxUnit、NUnit、MSTest形式のsource adapterを追加する。
- [x] 言語固有parserを共通metadata validationとJSON projectionへ接続する。

## Validation

- 同じsourceを複数回、入力順を変えて抽出し、byte-equivalentなJSONになることを確認する。
- CRLFとLFのfixtureが同じsource textとhashへ正規化されることを確認する。
- valid、missing、duplicate、unbound、parse error、schema errorの各コメントblockを検証する。
- decorator付き、class method、async function、nested function、parameterized declarationのsource bindingを検証する。
- repository外pathとsymlink境界を拒否することを検証する。
- TypeScriptのstatic title、modifier、`describe`、`test.each`、TSX、syntax errorを検証する。
- C#のxUnit、NUnit、MSTest attribute、parameterized declaration、syntax errorを検証する。
- 複数言語を一回のCLI呼び出しへ混在させた場合にexit `2`で拒否することを検証する。
- Skill folderを`skill-creator`の`quick_validate.py`で検証する。

## Risks

- Pythonの`test*`命名だけではruntime runnerの収集集合と一致しない。この差はv1で意図的に受け入れ、runtime collection対応時に別adapter contractとして扱う。
- TypeScriptはcall構文、C#はattribute構文だけを認識し、import、alias、runner設定を意味解決しない。誤認を避けるため対象source pathを明示し、coverageをruntime collectionとして扱わない。
- TypeScriptとC# adapterは固定済み外部依存のrestoreを必要とする。依存未準備は部分JSONを返さないexit `2`として扱う。
- TOML comment blockは機械的に扱いやすい一方、作者の記述量が増える。実利用で負荷が高い場合も、曖昧な自由記述へ戻さずauthoring helperを追加する。
- oracle参照をv1で解決しないため、存在しない参照や循環した根拠は抽出後のAI審査または後続resolverまで検出できない。
- 既存テストへ適用するenforcement policyは未定義であり、このplanだけではCI導入できない。
