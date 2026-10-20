# WithMate Repository GlossaryをCodexで利用する

本書は、WithMate 6.3.29の接続設定・導入確認・障害調査の手順である。通常作業の利用方針と操作権限は[WithMate利用方針](../guides/withmate.md)、呼出契約は現在のMCP instructions・tool説明・schemaとruntime-managed Skillが正本である。

## 対応契約

このrunbookは次のinterfaceを対象とする。

| Contract | Value |
| --- | --- |
| Codex managed HTTP登録名 | `withmate-glossary-http` |
| HTTP endpoint | `/mcp/glossary` |
| Glossary schema | `withmate-glossary-v1` |
| Repository file | `.withmate/glossary.yaml` schema v1 |
| 開発・診断用STDIO command | `withmate-glossary mcp-server` |

実行時の正本は、WithMateが配置した`skills/withmate-glossary/.withmate-managed-skill.json`の`bundleVersion`と同Skillの`SKILL.md`である。schemaやauthorityが変わった場合は、固定値を推測で読み替えず、配布SkillとWithMateのrelease contractを再確認する。

## Setup

WithMateはprovider Sessionへ、Memoryと同じ共有localhost listenerのHTTP接続設定を自動供給する。`config.toml`への手動登録は不要であり、URLや当turnの短命tokenを永続設定・設定例・ログへ保存しない。

1. WithMateを起動し、runtime-managed `skills/withmate-glossary/`が配置されていることを確認する。
2. WithMateでCodexのSessionを開始し、そのSessionでmanaged Skillと公開されたMCP toolを確認する。
3. `tools/list`で`glossary.list_targets`等のGlossary用toolが公開されていることを確認し、`glossary.list_targets`で許可されたtargetを取得する。接続確認だけを目的にGlossaryを作成・変更しない。

MCP serverはWithMateのSession-bound runtimeへ接続する。Session ID、repository path、branch名をauthority入力にせず、`glossary.list_targets`が返すprimary checkoutだけを操作する。

通常の`codex mcp list`による永続設定の確認だけで、一時設定の接続成否を判定しない。Memory／Characterとの共通の接続確認は[Memory／Character runbook](withmate-character-context.md)を参照する。

## 手動STDIOによる開発・診断

手動clientの開発・診断では`withmate-glossary mcp-server`を使う。診断用のCodex server設定では、[Memory／Character runbookの手動STDIO](withmate-character-context.md#手動stdioによる開発診断)と同じ5変数を`env_vars`で転送する。Session bindingの実値を固定・複製せず、通常のmanaged HTTP接続との重複を避ける。接続経路を変えてもtargetや操作権限は広がらない。

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

MCPが未設定、起動不能、またはtransport-levelで利用不能な場合だけ、managed Skillの手順に従ってCLI fallbackを使用できる。CLIも同じactive provider Session bindingを必要とする。bindingとprimary checkoutを確認できない場合はwriteしない。

managed HTTPでtoolが公開されない場合は、起動元WithMateと当該Sessionへの接続設定の供給を確認する。`GLOSSARY_SESSION_BINDING_REQUIRED`ではprovider Sessionのbindingを確認し、手動STDIOの場合だけ5変数の転送設定も確認する。別Sessionの値や推測したURL・tokenで補わない。structuredなauthority、validation、revision、conflict errorはavailability failureへ読み替えず、CLIで迂回しない。
