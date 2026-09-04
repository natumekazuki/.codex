# WithMate Memory / Character contextをCodexで利用する

## 対応契約

このrunbookはWithMate 6.3.26で確認した次のinterfaceを対象とする。

| Contract | Value |
| --- | --- |
| MCP server | `withmate-character-context` 1.0.0 |
| Verified MCP protocol | `2025-06-18` |
| Character context schema | `withmate-character-context-v1` |
| Affect candidate schema | `withmate-affect-v1` |
| Runtime discovery | application instanceとMemory runtime generationの固定tuple |
| STDIO command | `withmate-memory mcp-server` |

実行時のtool名、schema、annotationはMCPの`tools/list`を正本とする。authority、runtime binding、effect、fallbackの外部契約はWithMateのrelease contractとADRを参照し、versionが変わった場合は固定値を推測で読み替えない。

## Setup

1. WithMateを起動し、`withmate-memory` commandが配置されていることを確認する。
2. `config.example.toml`の`mcp_servers.withmate-character-context` sectionをlocal `config.toml`へ反映する。
3. `project_doc_max_bytes`がglobal `AGENTS.md`と対象project instructionを収容できることを確認する。portable設定では131072 bytesを使う。
4. Codexを再起動するか新しいsessionを開始する。MCP設定と`AGENTS.md`はsession開始時に読み直される。
5. `codex mcp list`またはCodexのMCP表示で`withmate-character-context`がenabledであることを確認する。
6. Character用の公開toolが次の6個であることを確認する。
   - `character_context.get`
   - `character_affect.appraise`
   - `character_memory.search`
   - `character_memory.append_episode`
   - `character_memory.correct`
   - `character_memory.forget`
7. 同じMCP serverがgeneral semantic Memory用の`memory.*` toolを公開していることを確認する。完全なtool一覧とschemaはMCPの`tools/list`を正本とする。

MCP serverはWithMateのloopback application serviceへ接続する。WithMate停止中に別databaseまたはfallback fileを作ってはならない。

## Session bindingの環境変数

CodexのSTDIO MCPへWithMate固有の環境変数を転送するには、local `config.toml`の`env_vars`へ変数名を列挙する。`mcp_servers.withmate-character-context`には次の5変数をすべて指定する。

- `WITHMATE_AGENT_RUNTIME_BINDING_REFERENCE`
- `WITHMATE_AGENT_RUNTIME_BINDING_REQUIRED`
- `WITHMATE_AGENT_RUNTIME_TURN_CAPABILITY`
- `WITHMATE_MEMORY_RUNTIME_APPLICATION_INSTANCE_ID`
- `WITHMATE_MEMORY_RUNTIME_GENERATION_ID`

`config.toml`へ保存するのは変数名だけである。binding reference、turn capability、runtime identityの値はWithMateがSessionごとのCodex processへ注入し、固定値を`env`へ保存しない。設定変更後は新しいCodex Sessionを開始し、MCP processを再起動する。

## Codexの運用規則

通常のWithMate Sessionでは、現在のユーザー発言とCharacter Definitionを優先し、次にinjected Character contextを使う。追加のMemory検索は現在の判断または自然な会話継続へ具体的に影響する場合だけ行い、user-facing response直前にProject、Character、Character affectの観点で保存候補を振り返る。具体的候補がないturnでは検索またはwriteを儀式的に実行しない。

Memoryへ保存できるのは、repositoryの正本にするほどではない文脈、projectをまたぐ選好、会話継続に役立つ関係性やepisodeである。secret、private path、raw log、大きなdiff、推測、未完了状態、未実行作業は保存しない。repository-ownedな契約、実装状態、検証結果は先にrepositoryの正本へ置く。

## Integration scenarios

具体的なCharacter affectの変化が発生したら、ユーザーへ自然に反応した後、できるだけ早く`character_affect.appraise`へ送る。lifecycleはmandatory post-turn appraisalを引き続き所有するが、event-time appraisalを禁止しない。同じpost-turn requestだけはMCPへ再送しない。

1. 関連するepisodeを含むinjected contextが応答の温度または話題のつながりへ薄く反映される。
2. 関係のないMemoryでは追加検索または会話への持ち込みが起きない。
3. 同義のsemantic preferenceはgeneral Memory MCPのduplicate preflightで増えない。
4. 同じmotifを持つ別時点の出来事は別episodeとして保存できる。
5. frustrationの後にreliefが生じた場合など、同じturn中の別eventをそれぞれappraiseし、成功応答の最新versionを後続requestへ引き継ぐ。
6. 別時点または別の根拠を持つaffect eventは、family、target、label、意味が似ていても別eventとして保存できる。後続eventを理由に先行eventを統合、上書き、削除しない。
7. 同一eventのtimeout、response loss、client resendは変更していないrequestと同じidempotency keyでreconcileし、`replayed`を新規保存として扱わない。
8. bugへのnegative affectは`targetType=bug`として扱い、userまたはrelationshipへ誤投影しない。
9. rejected affect候補を保存済みとせず、別storeまたはsemantic Memoryへ移さない。
10. Affect eventと同じ出来事に属するepisodeはappraisalのlinked episodeとして保存し、`character_memory.append_episode`へ重複送信しない。
11. 許可された明示targetのMemoryはAgentがユーザーの代理として検索、取得、追加、訂正、forget、moveできる。別Characterをownerに持つtargetは読み書きしない。
12. Memoryの訂正、forget、moveには具体的な理由とidempotency keyを指定し、mutation後にcurrent stateをread-backする。general Memoryのbulk forgetは実行前にdry-runする。
13. Agent-bound CLI fallbackは、同じprovider executionでMCP initializeと`tools/list`が成功した後のtransport errorが`details.fallbackEligible=true`を返した場合だけ、変更していない同一operationと同じactor-relative requestで`--fallback-from mcp`を指定して実行する。復旧後はMCPで同じscopeとversionをread-backする。
14. MCP未設定、process起動不能、initializeまたは`tools/list`の失敗、`authority_denied`、`invalid_input`、`version_conflict`その他のstructured errorではCLIへfallbackしない。非idempotentな`memory.get_file`と`memory.export_files`も対象外とし、response loss時は出力先をread-onlyで確認するかoperatorによるmanual recoveryで閉じる。
15. routineなcontext取得、Memory検索、affect処理をuser-facing responseで逐次実況しない。
16. affect contextがない場合は状態を捏造せず、現在のCharacter Definitionと会話だけで応答を継続する。
17. 別Sessionのaffect afterglowはread-time projectionとしてだけ扱い、新規event、Character Memory episode、relationship stateへコピーしない。
18. Session-bound MCPとCLIは起動元のapplication instanceとMemory runtime generationへ接続し、別instanceまたは新しいgenerationへfallbackしない。
19. generation mismatchや複数instanceのambiguous resultをtransport availability failureへ読み替えず、別runtimeを推測して選択しない。

破壊的なscenarioを検証だけのために本番Memoryへ実行しない。affect correction、sessionまたはrelationship affect reset、relationship boundary変更は、明示指示またはoperator recoveryの対象がある場合だけ実行する。

## Shadow modeと観測

初期導入ではruntimeが返すshadow modeに従い、negative affectとrelationship affectの応答影響を限定する。shadow modeをdry-runとは扱わず、保存結果は`effect`、`saved`、`rejected`、`replayed`で独立に判定する。

`withmate-memory character-metrics`では、transport / operation別のcall、success、rejection、failure、idempotent replay、version conflict、rejection code、latency、`mcp->cli` fallbackを確認する。

rollout全体では、WithMate lifecycleとCodex側の利用記録から次を環境別、Character別に集計できる状態を維持する。現在の公開metricsだけで取得できない項目を、推測値または会話本文の記録で補わない。

- injected contextの利用可能率
- 追加Memory検索率と検索結果採用率
- affect候補数、保存数、拒否理由
- Character episode候補数と保存数
- semantic duplicate抑止数
- idempotent replay抑止数
- MCP failureと`mcp->cli` fallback数
- correction、forget、reset数
- afterglowの候補、採用、continuity除外、same-target除外、component上限到達数

metricsへ会話本文、Memory本文、affect evidence、推定したユーザー感情、secret、raw transcriptを保存しない。

## 障害時の切り分け

`codex mcp get withmate-character-context`で5つの変数名がmaskされた値として表示されることを確認する。`env: -`の場合は`env_vars`が未設定であり、MCP processへSession bindingが渡らない。

`memory.list_targets`が`MEMORY_PRINCIPAL_REQUIRED`を返す場合は、WithMate本体の起動、5変数の設定、新しいCodex SessionでのMCP再起動を順に確認する。このerrorを含むstartup、initialize、`tools/list`、authority、domain validation、version、idempotency、migration、storageの失敗はfallback開始条件ではない。CLI fallbackを試さず、MCPの設定またはruntimeを復旧する。
