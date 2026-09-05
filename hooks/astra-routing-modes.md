# Astra routing mode

通常のrootとsubagentはSol / Lunaを使い、Astraは`astra_consultant`と`astra_reviewer`に限定する。静的なmodel、effort、sandbox、role責務は`agents/*.toml`、runtimeのmode、親user turnごとの共有枠、同時実行状態、明示許可は`hooks/astra-routing.ps1`を正本とする。

## Mode

| mode | Astra投入 |
| --- | --- |
| `conditional` | 具体的な調査後も残る重要な設計判断または矛盾、既に必要と判定されたreview内の難しい反例に限り、親user turnにつき合計1回まで自動投入できる |
| `manual` | 現在のsession、turn、role、回数へ明示grantがある場合だけ投入できる。既定値 |
| `off` | Astraを投入しない |

`conditional`でも、差分量、file数、単発のcommand失敗、権限や情報の不足、modelの利用可否、「念のため」は選択理由にならない。2 roleは共有枠を使い、spawn、follow-up、retryが1回を消費する。wait、status確認、結果取得、terminationは消費しない。同じroot sessionではAstraの起動または予約を同時に1件だけ許可する。

## 切替

```powershell
pwsh hooks/set-astra-routing.ps1 -Mode manual
pwsh hooks/set-astra-routing.ps1 -Mode conditional
pwsh hooks/set-astra-routing.ps1 -Mode off
```

状態はGit管理外の`hooks/astra-routing.local.json`と`hooks/.astra-routing-state/`へ保存する。`CODEX_ASTRA_ROUTING_MODE`、`CODEX_ASTRA_ROUTING_CONFIG_PATH`、`CODEX_ASTRA_ROUTING_STATE_DIR`は隔離した検証や一時的な上書きに使える。

`manual`のgrantは、`UserPromptSubmit` hookが記録した現在の`session_id`と`turn_id`へ限定して作る。

```powershell
pwsh hooks/set-astra-routing.ps1 `
  -SessionId '<session_id>' `
  -TurnId '<turn_id>' `
  -Role astra_consultant `
  -Count 1
```

新しいuser turnでは前turnのgrantを破棄する。追加回数を許可する場合も、対象roleと回数を明示する。

## 境界と検証

`PreToolUse`は専用roleまたは明示された`gpt-6-astra`を検出し、mode、turn、共有枠、同時実行、manual grantを満たさない呼出しを拒否する。`SubagentStart`と`SubagentStop`で実行中のAstraを追跡し、通常roleの`SubagentStart`も記録してfollow-up先を識別する。`SessionStart`では既存stateを再注入する。state破損時はAstra投入と、対象modelを判定できない既存agentへのfollow-upを拒否する。新しいSol / Luna作業は継続できる。破損状態は次のturnで自動解除しない。該当sessionでAstraが動作中でないことを確認して対象state fileを削除すると、次のuser promptで再生成される。削除前のagent識別情報は復元しないため、そのagentへのfollow-upは拒否される。必要な作業は新しいSol / Luna agentを起動して継続する。

hookは対応するlocal function toolへのguardrailであり、特殊なtool経路やhook自体の未実行まで完全に封鎖するsecurity boundaryではない。導入時は`/hooks`で内容を確認してtrustし、新規session、spawn、follow-up、compaction、resumeで実効modelと拒否結果を確認する。専用role以外のlocal aliasへAstraを設定し、spawn時にmodelを省略するとhookは実効modelを判定できないため、その構成は追加しない。

```powershell
pwsh hooks/test-astra-routing.ps1
```
