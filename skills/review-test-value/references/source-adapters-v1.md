# Source Adapters v1

各adapterはsource declarationを構文解析し、runtime runnerのcollection結果は再現しない。一回のCLI呼び出しには同一言語のpathだけを渡す。

## Python

- Extensions: `.py`
- Parser: Python `ast`と`tokenize`
- Declarations: moduleまたはclass直下で、名前が`test`から始まる`def` / `async def`
- Parameterization: decoratorを含む一つのsource declarationとして抽出する
- Excluded: nested function、`setattr`、metaclass、loopなどによる動的生成

Result fields:

- `adapter`: `python-source-v1`
- `coverage`: `python-source-declarations-v1`

## TypeScript

- Extensions: `.ts`、`.tsx`
- Parser: TypeScript Compiler API
- Declarations: `test()`、`it()`、`test.only()`、`it.skip()`などのstatic call
- Parameterization: `test.each(...)(...)`と`it.each(...)(...)`を一つのsource declarationとして抽出する
- Grouping: `describe()`と`test.describe()`のstatic titleをqualified symbolへ含める
- Supported declaration modifiers: `only`、`skip`、`todo`、`fixme`、`fail`、`fail.only`
- Supported group modifiers: `only`、`skip`、`fixme`、`parallel`、`serial`と、`parallel.only`、`serial.only`
- Overload classification: importやtypeを解決せず、先頭引数のstatic titleをdeclaration overloadの識別に使う。`test.skip()`、`test.fail()`、`test.fixme()`の先頭引数がstatic titleでなければruntime annotationとして扱う
- Non-declaration API: Playwrightのhook、`test.use()`、`test.extend()`、`test.info()`、`test.setTimeout()`、`test.step()`、`test.abort()`、`test.describe.configure()`、runtime annotation overloadなどはtest recordにしない
- Unsupported diagnostic: 未対応modifier、未対応のnested / tagged call chain、動的titleのtest / describe、同一行に複数あるtest declaration、行頭から宣言までに空白以外がある形
- Excluded: alias経由のcall、computed property、factory生成、runtime parameter case

Jest、Vitest、Playwrightのpackage identityやimport解決は行わない。上記のcall構文をtest declarationとして扱う。

Result fields:

- `adapter`: `typescript-source-v1`
- `coverage`: `typescript-source-declarations-v1`

## C#

- Extension: `.cs`
- Parser: Roslyn
- Declarations: methodへ付いた次のattributeを構文上のtest declarationとして扱う
  - xUnit: `Fact`、`Theory`
  - NUnit: `Test`、`TestCase`、`TestCaseSource`
  - MSTest: `TestMethod`、`DataTestMethod`
- `Attribute` suffixとnamespace-qualified nameを許可する
- Parameterization: data attributeを含む一つのsource declarationとして抽出する
- Unsupported diagnostic: project固有のpreprocessor symbolが必要な条件付きコンパイル領域
- Excluded: attribute aliasの意味解決、source generator、継承やruntime discoveryだけで生成されるtest、展開後data row

Result fields:

- `adapter`: `csharp-source-v1`
- `coverage`: `csharp-source-declarations-v1`

## Common Failure Boundary

- syntax errorを含むfileから部分recordを出力しない。
- staticに識別できるtest declarationが未対応形なら`TEST_DECLARATION_UNSUPPORTED`を返す。
- 行頭からtest declarationまでに空白以外がある行は、同じ行の全test declarationを除外し、物理行につき一件の`TEST_DECLARATION_UNSUPPORTED`を返す。直前のmetadata blockは`TEST_VALUE_UNBOUND`とする。
- UTF-8 BOMはencoding markerとして除去し、source内容やindentには含めない。
- frameworkのimport、runner設定、skip状態、実行結果は検証しない。
