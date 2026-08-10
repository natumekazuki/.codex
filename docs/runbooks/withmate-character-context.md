# WithMate Character contextをCodexで利用する

## 対応契約

このrunbookはWithMate 6.3.19で確認した次のinterfaceを対象とする。

| Contract | Value |
| --- | --- |
| MCP server | `withmate-character-context` 1.0.0 |
| Verified MCP protocol | `2025-06-18` |
| Character context schema | `withmate-character-context-v1` |
| Affect candidate schema | `withmate-affect-v1` |
| STDIO command | `withmate-memory mcp-server` |

実行時の正本は、WithMateが配置した`skills/withmate-memory/.withmate-managed-skill.json`の`bundleVersion`と、同Skillの`reference/character-context.md`である。versionまたはschemaが変わった場合は、固定値を推測で読み替えず、配布SkillとWithMateのrelease contractを再確認する。

## Setup

1. WithMateを起動し、`withmate-memory` commandと`skills/withmate-memory/`が配置されていることを確認する。
2. `config.example.toml`の`mcp_servers.withmate-character-context` sectionをlocal `config.toml`へ反映する。
3. `project_doc_max_bytes`がglobal `AGENTS.md`と対象project instructionを収容できることを確認する。portable設定では131072 bytesを使う。
4. Codexを再起動するか新しいsessionを開始する。MCP設定と`AGENTS.md`はsession開始時に読み直される。
5. `codex mcp list`またはCodexのMCP表示で`withmate-character-context`がenabledであることを確認する。
6. 公開toolが次の6個であることを確認する。
   - `character_context.get`
   - `character_affect.appraise`
   - `character_memory.search`
   - `character_memory.append_episode`
   - `character_memory.correct`
   - `character_memory.forget`

MCP serverはWithMateのloopback application serviceへ接続する。WithMate停止中に別databaseまたはfallback fileを作ってはならない。

## Integration scenarios

通常のWithMate Sessionではinjected Character contextとlifecycle-owned post-turn appraisalを使う。同じturnを`character_affect.appraise`へ重複送信しない。

1. 関連するepisodeを含むinjected contextが応答の温度または話題のつながりへ薄く反映される。
2. 関係のないMemoryでは追加検索または会話への持ち込みが起きない。
3. 同義のsemantic preferenceはgeneral Memory CLIのduplicate preflightで増えない。
4. 同じmotifを持つ別時点の出来事は別episodeとして保存できる。
5. 同一eventのretryは同じrequestとidempotency keyを使い、`replayed`を新規保存として扱わない。
6. bugへのnegative affectは`targetType=bug`として扱い、userまたはrelationshipへ誤投影しない。
7. rejected affect候補を保存済みとせず、別storeまたはsemantic Memoryへ移さない。
8. MCP availability failure時だけ`--fallback-from mcp`でCharacter CLIを使い、復旧後のMCP read-backと同じscope、versionを確認する。
9. `authority_denied`、`invalid_input`、`version_conflict`その他のdomain resultをCLIで迂回しない。
10. routineなcontext取得、Memory検索、affect処理をuser-facing responseで逐次実況しない。
11. correctionまたはforgetは明示的なユーザー指示に基づいて実行し、scope、version、`readBack`を報告する。
12. affect contextがない場合は状態を捏造せず、現在のCharacter Definitionと会話だけで応答を継続する。

破壊的なscenarioを検証だけのために本番Memoryへ実行しない。correction、forget、resetは明示指示またはoperator recoveryの対象がある場合だけ確認する。

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

metricsへ会話本文、Memory本文、affect evidence、推定したユーザー感情、secret、raw transcriptを保存しない。
