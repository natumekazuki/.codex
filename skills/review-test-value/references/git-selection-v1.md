# Git Selection v1

## Purpose

Git差分へ含まれる新規・意味変更testだけを抽出し、変更していない既存testへ`@test-value`の一括導入を要求しない。

## Invocation

working treeをtask baseと比較する。

```powershell
python -X utf8 <skill-dir>/scripts/extract_test_values.py `
  --root <repository-root> `
  --changed-from <task-base-commit> `
  --language python
```

`--language`は`python`、`typescript`、`csharp`のいずれか一つとする。複数言語を変更した場合は言語ごとに実行する。

比較対象をindexへ限定する場合は`--staged`、commitへ固定する場合は`--head <commit>`を追加する。両方は同時に指定しない。省略時はworking treeを使う。

## Snapshot Semantics

- working tree: base以降のcommit、staged、unstaged、non-ignored untracked fileを含む。sourceはfilesystemから読む。
- staged: baseとindexを比較し、sourceはindexから読む。
- head: baseと指定commitを比較し、sourceは指定commitから読む。

baseとheadは直接比較する。CLIはmerge-base、upstream、task開始commitを推測しない。

working treeのsource pathがsymlinkなどによってrepository root外へ解決される場合は、外部内容を読まず`SOURCE_OUTSIDE_ROOT`を返す。stagedとheadはGit objectから読み、working treeのsymlinkを追跡しない。

## Selection

- 対象言語の変更fileはGit差分から自動発見する。個別pathやline rangeは受け取らない。
- test declarationのrange、または直接隣接する`@test-value` blockへdiff hunkのold-sideかnew-sideが交差したsurviving recordを選ぶ。
- base側recordのdeclaration startをnew側へ投影する。開始境界を削除した場合は削除anchorの直後へ対応付け、先頭decoratorやattributeだけを削除して開始行が変わったsurviving recordも選ぶ。
- test本文だけ、構造化コメントだけを変更した場合も選ぶ。
- metadata markerや隣接関係を壊してnew-sideでblockを結合できなくなった場合も、base側のrecord対応からsurviving testとdiagnosticを選ぶ。
- surviving testの本文行または隣接する`@test-value` blockを削除した場合は、new-sideの削除anchorから対応recordを選ぶ。test declaration全体またはtest file全体の削除はbase snapshotのrecordを`DELETED.before`へ保持する。
- 対応sourceはGit属性の`-diff`やtext conversionを適用せず、raw textとしてhunkを取得する。LFとCRLFの相互変換だけではrecordを選ばず、同じfileで同時に行われた内容変更は選択対象に残す。
- 変更していないrecordと、そのrecordだけに属するmetadata diagnosticは結果から除外する。
- pure renameは選ばず、空の`tests`と`transitions`を返す。renameと同時に内容を変更した場合は変更recordを選ぶ。
- Git modeは変更recordごとに`ADDED`、`SURVIVED`、`DELETED`のtransitionを返す。file pair内でrecord hashとhunkから投影したdeclaration位置を照合し、symbol名だけでは対応付けない。hashと位置が別recordを指すなど対応を一意に確定できない場合は`RECORD_TRANSITION_UNRESOLVED`で停止する。
- `ADDED`と`SURVIVED`の`after`集合は、順序を含めて`tests`と一致する。`DELETED`は`tests`へ含めない。
- `DELETED.before`に結合したv1 metadataや抽出diagnosticは削除によって消さず、`TEST_VALUE_V2_REQUIRED`などの元diagnosticで停止する。
- source全体の解析を信頼できなくするsyntax、decode、adapter failureは隠さない。
- 静的に識別した未対応test declarationは内部rangeで差分と対応付け、開始行以外の本文変更も`TEST_DECLARATION_UNSUPPORTED`として返す。内部rangeは公開diagnosticへ追加しない。
- 対象言語に変更recordがない場合は空の`tests`と`diagnostics`を返し、exit `0`とする。

明示pathを渡す従来modeは、既存file全体の審査やmigrationにだけ使う。新規・変更testの標準審査でGit modeをpath指定へ置き換えない。
