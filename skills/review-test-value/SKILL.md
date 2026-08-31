---
name: review-test-value
description: Python、TypeScript、C#のtest sourceへ隣接する構造化された`@test-value`コメントとtest declarationを決定論的に抽出し、コメントの検証価値とtest本文の整合を審査する。pytest・unittest、Jest・Vitest・Playwright、xUnit・NUnit・MSTest形式の新規・変更テストの価値レビュー、価値コメントの追加・修正、曖昧・重複・実装詳細へ結合したテストの見直し、AIレビュー入力の生成で使う。runtime test collection、動的生成caseの展開、CI gateの構築には使わない。
---

# Review Test Value

構造化コメントとtest sourceの対応付けをscriptへ任せ、metadata単体の価値、test sourceとの整合、必要なbounded deep review、保持先を分けて審査する。欠落した値や曖昧な結合を会話内で補完しない。

抽出CLIには`tomllib`を含むPython 3.11以降を使う。TypeScriptにはNode.jsと固定済みnpm依存、C#には.NET 8 SDKと固定済みNuGet依存を追加で使う。

## Workflow

1. repository instructionと対象pathを確認する。
2. 対象言語とsource adapterの対応範囲を[references/source-adapters-v1.md](references/source-adapters-v1.md)で確認する。動的生成、runtime collectionとの一致が必要なtestはv1対象外として報告する。
3. 価値コメントを書くか直す場合は、先に[references/comment-format-v1.md](references/comment-format-v1.md)を読む。
4. TypeScriptまたはC#を初めて抽出する環境では、対応する依存を準備する。

```powershell
npm ci --prefix <skill-dir>/scripts/adapters/typescript
dotnet restore <skill-dir>/scripts/adapters/csharp/TestValue.CSharpExtractor.csproj
```

5. 新規・意味変更testの審査では[references/git-selection-v1.md](references/git-selection-v1.md)を読み、task開始時に固定したbase commitから対象snapshotまでのGit差分で抽出する。対象pathやline rangeを手で選ばない。複数言語は言語ごとに実行を分ける。

```powershell
python -X utf8 <skill-dir>/scripts/extract_test_values.py `
  --root <repository-root> `
  --changed-from <task-base-commit> `
  --language python
```

明示的なfile全体の審査またはmetadata migrationでは、repository rootと同一言語のsource pathを指定する従来modeを使う。

```powershell
python -X utf8 <skill-dir>/scripts/extract_test_values.py `
  --root <repository-root> `
  <test-source-path> [<test-source-path> ...]
```

6. exit `1`ではstdoutの`diagnostics`を読み、sourceまたはコメントを修正してから再実行する。抽出器を迂回してAI審査へ進まない。
7. exit `2`ではstderrを読み、root、path、依存、I/Oを直す。信頼できる部分結果があるとみなさない。
8. exit `0`のresultからmetadata packetを作る。packetは[references/metadata-review-contract.md](references/metadata-review-contract.md)に従い、source locator、source text、source hashを含めない。

```powershell
python -X utf8 <skill-dir>/scripts/build_review_packets.py metadata `
  --extractor <extractor-result.json>
```

9. `test_value_luna`をmetadata phaseとして起動し、packetだけを渡す。結果を次で検証し、schema不正なら審査結果として採用しない。

```powershell
python -X utf8 <skill-dir>/scripts/validate_review_result.py metadata `
  --input <metadata-result.json> `
  --packet <metadata-packet.json>
```

10. 固定済みmetadata resultと同じextractor resultからalignment packetを作る。同じ`test_value_luna` childへfollow-upできる場合は二turn目として渡し、できない場合だけ別childを起動する。二phaseを一promptへ統合しない。Phase 1が`REDESIGN`のrecordも省略しない。契約は[references/alignment-review-contract.md](references/alignment-review-contract.md)を使う。

```powershell
python -X utf8 <skill-dir>/scripts/build_review_packets.py alignment `
  --extractor <extractor-result.json> `
  --metadata-result <metadata-result.json>

python -X utf8 <skill-dir>/scripts/validate_review_result.py alignment `
  --input <alignment-result.json> `
  --packet <alignment-packet.json>
```

11. [references/routing-policy.md](references/routing-policy.md)に従ってrecordごとのrouting inputを作り、次のscriptでSol routingを決める。Phase 1 `NEEDS_CONTEXT`、Phase 2 `RECHECK`、bounded contextが必要、高リスク、監査対象のrecordだけを[references/deep-review-contract.md](references/deep-review-contract.md)のpacketへ入れ、`test_value_sol`へ渡す。packet外を探索させない。

```powershell
python -X utf8 <skill-dir>/scripts/review_routing.py --input <routing-input.json>

python -X utf8 <skill-dir>/scripts/build_review_packets.py deep `
  --alignment-packet <alignment-packet.json> `
  --alignment-result <alignment-result.json> `
  --routing <routing-manifest.json> `
  --context <context-by-record.json>
```
12. required agentを起動できない場合は親agentが代行せず、そのrecordを`status = NEEDS_CONTEXT`、`disposition = null`、`gate = BLOCKED`として停止する。別modelへsilent fallbackしない。
13. alignment packetの一record、同じrecordのPhase 2 result、検証対象routing manifest、requiredな場合のSol result、保持根拠、artifact stateを`validate_review_result.py aggregate`へ渡し、`status`、`disposition`、`gate`を決める。`sol_required`やphase verdictを独立したscalarとして再入力しない。Bootstrapではmetadata v1を読み、v1 `ephemeral`の削除条件、resolution ledger、元test削除後の`PASS`を有効化しない。
14. JSON field、diagnostic、exit statusの確認が必要なら[references/output-v1.md](references/output-v1.md)を読む。

## Extraction Rules

- 従来modeでは明示されたpathだけをscriptへ渡す。抽出器へ対象testの選択を推測させない。
- Git modeでは対象pathとline rangeをGit差分選択器へ任せ、個別指定へ置き換えない。
- 一回の呼び出しへ`.py`、`.ts` / `.tsx`、`.cs`を混在させない。
- `metadata`、`source_text`、line locator、hashを抽出結果のまま扱う。
- 通常コメントやdocstringを構造化metadataへ昇格しない。
- `metadata: null`をAIが推定値で埋めない。
- `coverage`をruntime runnerの収集結果として扱わない。
- JSONを恒久artifactやsource of truthとして保存しない。必要なら同じsourceから再生成する。

## Review Result

test recordごとに`status`、`disposition`、`gate`を分けて返す。

- `status`: `ACCEPT`、`REDESIGN`、`NEEDS_CONTEXT`
- `disposition`: `KEEP_PERMANENT`、`KEEP_TEMPORARY`、`MOVE_TO_POLICY_CHECK`、`DROP`、または未確定の`null`
- `gate`: `PASS`、`CHANGES_REQUIRED`、`BLOCKED`

phase判定には`evidence`、`unverified`、必要なら`next_action`を添える。oracle本文が入力されていない場合は`oracle.ref`を必ず`unverified`へ残し、参照先の存在、claimの裏付け、非循環性を確認済みと表現しない。文章の巧拙だけを`REDESIGN`理由にしない。

## Validation

Skillまたはscriptを変更したら次を実行する。

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values_multilang.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_packets.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_result_schema.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/extract_test_values.py
python -X utf8 -m py_compile skills/review-test-value/scripts/git_diff_selection.py
python -X utf8 -m py_compile skills/review-test-value/scripts/build_review_packets.py
python -X utf8 -m py_compile skills/review-test-value/scripts/review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/validate_review_result.py
python -X utf8 <skill-creator>/scripts/quick_validate.py skills/review-test-value
```
