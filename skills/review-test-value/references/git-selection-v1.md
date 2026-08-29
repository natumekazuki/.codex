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
- test本文だけ、構造化コメントだけを変更した場合も選ぶ。
- metadata markerや隣接関係を壊してnew-sideでblockを結合できなくなった場合も、base側のrecord対応からsurviving testとdiagnosticを選ぶ。
- surviving testの本文行または隣接する`@test-value` blockを削除した場合は、new-sideの削除anchorから対応recordを選ぶ。test declaration全体の削除は選ばない。
- 対応sourceはGit属性の`-diff`やtext conversionを適用せず、raw textとしてhunkを取得する。
- 変更していないrecordと、そのrecordだけに属するmetadata diagnosticは結果から除外する。
- pure renameと削除は選ばない。renameと同時に内容を変更した場合は変更recordを選ぶ。
- source全体の解析を信頼できなくするsyntax、decode、adapter failureは隠さない。
- 対象言語に変更recordがない場合は空の`tests`と`diagnostics`を返し、exit `0`とする。

明示pathを渡す従来modeは、既存file全体の審査やmigrationにだけ使う。新規・変更testの標準審査でGit modeをpath指定へ置き換えない。
