# Subagent Routing Mode

`subagent-routing.ps1` は現在の Spark mode と quota fallback だけを hook で追加する。role の責務、禁止事項、出力契約、model、sandbox は `agents/*.toml` を正本とする。
mode は `hooks/subagent-routing.local.json` に保存される。このファイルは個人の現在状態なので git 管理しない。

## Mode

| Mode | 用途 | 振り分け |
| --- | --- | --- |
| `balanced` | 既定。Spark と GPT-5.6 family を作業内容に応じて使う | 低から中リスクの小さい作業は `fast_*`、高リスクや曖昧な作業は通常 role |
| `spark-first` | Spark 残量が十分あり、Spark を優先したいとき | 低から中リスクの小さい作業を `fast_*` に強めに寄せる |
| `standard-only` | 自動選択で standard role だけを使いたいとき | 自動選択は通常の GPT-5.6 family role に限定する。ユーザーが exact `fast_*` role を明示した場合だけ例外として実行できる |

## Commands

`.codex` ルートで実行する。

macOS / Linux:

```sh
# 既定に戻す
hooks/set-spark-routing.ps1 balanced

# Spark を優先する
hooks/set-spark-routing.ps1 spark-first

# Spark を避けて GPT-5.6 family role に寄せる
hooks/set-spark-routing.ps1 standard-only
```

Windows / PowerShell:

```powershell
# 既定に戻す
pwsh -NoProfile -ExecutionPolicy Bypass -File hooks\set-spark-routing.ps1 balanced

# Spark を優先する
pwsh -NoProfile -ExecutionPolicy Bypass -File hooks\set-spark-routing.ps1 spark-first

# Spark を避けて GPT-5.6 family role に寄せる
pwsh -NoProfile -ExecutionPolicy Bypass -File hooks\set-spark-routing.ps1 standard-only
```

## Check

macOS / Linux:

```sh
cat hooks/subagent-routing.local.json
rm hooks/subagent-routing.local.json
```

Windows / PowerShell:

```powershell
Get-Content hooks\subagent-routing.local.json
```

`subagent-routing.local.json` が存在しない場合、hook は `balanced` として動作する。

```powershell
Remove-Item hooks\subagent-routing.local.json
```

role の選択基準は `AGENTS.md`、各 role の静的契約は `agents/*.toml` を参照する。この文書には runtime mode の操作方法だけを置く。
