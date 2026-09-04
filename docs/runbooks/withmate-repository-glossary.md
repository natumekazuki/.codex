# WithMate Repository GlossaryをCodexで利用する

## 対応契約

このrunbookはWithMate 6.3.26で確認した次のinterfaceを対象とする。

| Contract | Value |
| --- | --- |
| MCP server | `withmate-glossary` 1.0.0 |
| Glossary schema | `withmate-glossary-v1` |
| Repository file | `.withmate/glossary.yaml` schema v1 |
| STDIO command | `withmate-glossary mcp-server` |

実行時の正本は、WithMateが配置した`skills/withmate-glossary/.withmate-managed-skill.json`の`bundleVersion`と同Skillの`SKILL.md`である。schemaやauthorityが変わった場合は、固定値を推測で読み替えず、配布SkillとWithMateのrelease contractを再確認する。

## Setup

1. WithMateを起動し、`withmate-glossary` commandと`skills/withmate-glossary/`が配置されていることを確認する。
2. `config.example.toml`の`mcp_servers.withmate-glossary` sectionをlocal `config.toml`へ反映する。
3. Codexを再起動するか新しいSessionを開始する。MCP設定、managed Skill、`AGENTS.md`はSession開始時に読み直される。
4. `codex mcp list`またはCodexのMCP表示で`withmate-glossary`がenabledであることを確認する。
5. `glossary.list_targets`、`glossary.list`、`glossary.search`、`glossary.get`、`glossary.create`、`glossary.create_batch`、`glossary.update`、`glossary.delete`、`glossary.validate`が公開されていることを確認する。

MCP serverはWithMateのSession-bound runtimeへ接続する。Session ID、repository path、branch名をauthority入力にせず、`glossary.list_targets`が返すprimary checkoutだけを操作する。

`mcp_servers.withmate-glossary`の`env_vars`には、Character context MCPと同じ5つの`WITHMATE_*` Session binding変数をすべて指定する。値はWithMateがSessionごとのCodex processへ注入するため、固定値を`env`へ保存しない。設定変更後は新しいCodex Sessionを開始し、MCP processを再起動する。

## Codexの操作権限

`AGENTS.md`は次のstanding authorizationを所有する。

- read、search、validate、create、create-batch、updateは自律実行できる。
- proactive createはWithMate Settings、active turn capability、1 turnあたりの上限、managed Skillの登録条件に従う。
- updateはsource、accepted document、executable contractとの不一致、明確に古い定義、canonical termまたはaliasの誤りを直す場合に限る。単なる表現変更は行わない。
- deleteはcurrent entryとrevisionを読み、対象entryごとの明示確認を得てから実行する。

update requestの`explicitUserRequest: true`は、`AGENTS.md`に記録された継続的な明示authorizationを表す。deleteではstanding authorizationを使わず、対象entryに対する現在の明示確認を必要とする。

## Integration scenarios

1. `glossary.list_targets`が現在のSessionのprimary checkoutを1件だけ返す。
2. Additional Directories、別worktree、callerが指定したpathへauthorityが広がらない。
3. missingなGlossaryをreadしても`.withmate/`や`glossary.yaml`を作らない。
4. proactive createが無効または上限超過の場合、explicit createへ読み替えず拒否する。
5. updateはreadで得たcurrent revisionを使い、適用後のentryをread-backする。
6. revision conflictでは新しいrevisionを使って自動再試行せず、current valueと変更目的を再評価する。
7. `effect: unknown`では同じ操作を自動実行しない。current valueをread-backし、新しいwriteを選ぶ前にユーザーへ確認する。
8. structured validation、authority、revision、conflict errorをCLIで迂回しない。
9. Glossaryの内容をMemory、Session data、prompt、別cacheへ複製しない。

## 障害時の扱い

MCPが未設定、起動不能、またはtransport-levelで利用不能な場合だけ、managed Skillの手順に従ってCLI fallbackを使用できる。CLIも同じactive provider Session bindingを必要とする。bindingとprimary checkoutを確認できない場合はwriteせず、Glossary操作を未実行として報告する。

`codex mcp get withmate-glossary`の`env`が`-`の場合は、`config.example.toml`の`env_vars`をlocal設定へ反映して新しいSessionを開始する。`glossary.list_targets`が`GLOSSARY_SESSION_BINDING_REQUIRED`を返した場合も同じ設定を確認する。structuredなauthority、validation、revision、conflict errorはavailability failureへ読み替えず、CLIで迂回しない。
