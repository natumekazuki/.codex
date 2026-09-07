---
name: review-test-value
description: Python、TypeScript、C#の変更testをGitから抽出し、metadata・本文・bounded contextを一度の意味reviewで分類する。candidate期間は明示起動だけ。削除・移設もhostが確認し、既存checkの実行だけでは起動しない。
---

# Review Test Value

**candidate / explicit-only。** 新contract `test-value-review-v3`自身の実モデルreview、E2E、新規session確認が完了するまでactiveな必須gateへ登録しない。[有効化runbook](../../docs/runbooks/activate-test-value-review.md)が導入状態を所有する。旧多段pipelineへのfallbackはない。

## 対象と判断

task開始時のbaseと現在の変更からPython、TypeScript、C#の新規・意味変更・完全削除testを決定論的に抽出する。pathを手で絞り直したりbaseを取り直したりしない。未変更testを一括移行しない。形式は[comment-format-v2](references/comment-format-v2.md)、対象宣言とsnapshotは[source-adapters-v1](references/source-adapters-v1.md)、[git-selection-v1](references/git-selection-v1.md)を参照する。

testを増やす前に具体的な欠陥、直接の観測、既存checkとの差を考える。実装を写すだけのtestや循環oracleは避け、type/schema/static等が直接的ならそれを使う。別のDesign Gateや提出物は要求しない。意味基準と最終分類は一つの[review contract](references/review-contract-v3.md)に集約する。

## 実行

Python 3.11以降。対象のTypeScript/C# adapterが未準備の場合だけ既存のnpm ci / dotnet restoreを実行する。専用workerは既存のWindows native Codex CLI 0.153.4・ChatGPT Pro認証を対象とし、`agents/test_value_luna.toml`のLuna/maxを維持する。認証情報はhostだけが利用し、別API課金や認証fileのコピーをしない。

repository外のtask専用state directoryを用意する。working treeが既定、indexは`--staged`、固定commitは`--head <commit>`。同じtaskではbase、mode、task-id、stateを維持する。

```powershell
python -X utf8 <skill-dir>/scripts/run_test_value_review.py `
  --root <repository-root> --changed-from <task-base> --task-id <task-id> `
  --state-dir <outside-repository-state> --cli <absolute-native-codex.exe> --prepare
```

prepareはmodelを呼ばず、identityとhost evidenceの雛形を返す。雛形の選択集合・hashを手計算で作り直さず、実際に読んだ情報を記入してtask外のJSONへ保存する。

```powershell
python -X utf8 <skill-dir>/scripts/run_test_value_review.py `
  --root <repository-root> --changed-from <task-base> --task-id <task-id> `
  --state-dir <outside-repository-state> --cli <absolute-native-codex.exe> `
  --host-evidence <host.json> --batch-size 8 --max-workers 2 --timeout-seconds 900
```

一回の入口が全言語抽出、closed input、事前batch、単一review、ordinal検証、identity付与、現在の保持/解消条件、全体gateを処理する。fresh runのcall数は`ceil(record数 / batch-size)`。空selectionはmodelを呼ばずBLOCKED。全recordが大きすぎるbatchは送信前にBLOCKEDとし、recordを切り捨てない。各batchの入力上限は800,000文字、件数1〜100、並列1〜8、deadline10〜1800秒。既定値は上の例であり、性能上の最適値とはしない。

通常reviewはtoolsを公開せず、repository探索、合成canary、通常audit、後続deepを行わない。設定とCLI/role/contractのpreflightは決定論的に実行する。独立したfilesystem拒否smokeは有効化時・runtime変更時に明示実行するもので、毎batchの完了条件ではない。

## Host evidence

`test-value-host-v3`雛形には親riskのtags/summary/context、各recordのcontext/retention/resolution、過去義務のhistorical_resolutions、明示的supersessionsがある。unknownなriskを無根拠に「なし」としない。

contextは次のいずれか。repositoryは指定snapshotをhostが読み、外部contextはhostが実際に取得した内容を渡す。hashはscriptが計算する。

```json
{"source":"repository","ref":"src/helper.py","kind":"helper","start_line":10,"end_line":30}
```

start_line/end_lineがともにnullならfile全体。範囲指定の参照名は`src/helper.py#L10-L30`となる。root外path、symlink経由のroot外読取、存在しないsourceは拒否する。

```json
{"source":"host-observed","ref":"issue:123","kind":"accepted-contract","authority":"issue","content":"実際に確認した契約本文"}
```

authorityはissue / external-contract / explicit-user-requirement。必要なoracle、fixture、helper、mock、SUTだけを含める。missing contextを推測して生成しない。

retentionは`basis`（SUPPORTED/UNSUPPORTED/UNRESOLVED）、`reason`、根拠contextの`evidence_refs`、`temporal`。期限/条件付きの場合、temporalは`observed_on`（UTC日付）、`state`（ACTIVE/EXPIRED/UNRESOLVED）、`reason`、`evidence_refs`で現在状態を示す。直接確認した証拠でありmodelの推測ではない。

削除・移設のresolutionは`action`、現在の`snapshot_hash`、`reason_kind`、`reason`、`evidence_refs`、`target`、`check`。DROPのreason_kindはNO_ALTERNATIVE_REQUIREDかCOVERED_BY_EXISTING_CHECK、MOVEはPOLICY_CHECK。代替不要の場合だけtarget/checkをnullにできる。移設/代替先は`{ref, content_hash}`、checkは`{snapshot_hash, target_hash, exit_code, output_hash}`。hostが実際に確認した現artifactと成功receiptを入力し、自由文から成功やhashを作らない。

## 不足・再開・完了

`0 = PASS`、`1 = CHANGES_REQUIRED`、`2 = BLOCKED`。意味上のNEEDS_CONTEXTも正常なreview結果としてBLOCKEDになる。summary/findings/context_requestの空値を追加のsemantic validatorで拒否しない。詳細な分類とhost条件はreview contract、型とordinalはscriptが正本である。

不足contextを確認してhost JSONを更新し、同じ入口を再実行する。変わったrecord inputだけをreviewし、他の結果を使い回す前に現行の保持・artifact条件を確認する。同じinputでの意味判定の自動retryはしない。transport、timeout、schema、ordinal失敗の明示再実行だけ`--retry-transport`を使える。

旧candidateのtask-manifest/generations/resolution-ledgerは拒否し、自動移行しない。旧taskをv3 stateで継続したと偽らない。新しいcontractのtaskとして同じ固定baseから全対象と削除義務を再確認する。

途中失敗の成功batchはcanonical stateへ保存され、未完了はBLOCKEDで残る。消失したstateや過去の未解消recordを空selectionで消さない。historical_resolutionsは過去record_idと新しいcontext/retention/resolutionを渡す。recordの位置・契約が変わり自動対応できない場合だけsupersessionsへold_record_id/current_record_id、reason、現contextのevidence_refsを渡し、現在の新reviewがPASSであることを別に確認する。

stateは単一のtask-local`review-state.json`と所有marker/lockだけ。raw prompt/source/CLI全文/secretを恒久logへ残さない。resultには安全なfailure categoryとbatch index/ordinal/record IDだけを残す。PASSはtestそのものの実行成功や通常のcode/security reviewを代替しない。

## 検証

```powershell
python -m pip install -r <skill-dir>/scripts/requirements-test.txt
python -X utf8 -m unittest discover -s <skill-dir>/scripts -p test_single_review.py
python -X utf8 -m unittest discover -s <skill-dir>/scripts -p test_review_worker.py
python -X utf8 -m unittest <skill-dir>/scripts/test_extract_test_values.py
```

関係するadapter変更時は既存`test_extract_test_values_multilang.py`も実行する。CIのoffline成功と実モデル・Windows境界・fresh sessionの成功を区別する。明示的な実モデルE2Eとcandidate自身のreviewは[runbook](../../docs/runbooks/activate-test-value-review.md)を使う。未実施をACCEPTやactive化済みとしない。
