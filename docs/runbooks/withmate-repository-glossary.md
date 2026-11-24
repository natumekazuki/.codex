# WithMate Repository Glossaryの接続と診断

WithMateで起動したCodex Sessionのmanaged HTTP接続を扱う。用語をいつ登録してよいかは[WithMate利用guide](../guides/withmate.md)、操作方法は現在のruntime-managed `withmate-glossary` SkillとMCP契約が正本である。この配布元でSkill・store・権限表を複製しない。

## 読み取りだけで接続を確かめる

WithMateは `withmate-glossary-http`（`/mcp/glossary`）をSessionへ供給する。通常の `config.toml` への手動登録は不要。URL・短命tokenを設定・ログへ残さない。永続設定の `codex mcp list` だけではSessionの一時接続は確認できない。

起動したSessionでmanaged SkillとMCP toolの公開を確認し、`glossary.list_targets` で許可されたprimary checkoutを読む。Session ID・任意のpath・Additional Directories・別worktreeを対象にすり替えない。`withmate-glossary-v1` のrepository側の正本は `.withmate/glossary.yaml`（schema v1）。ファイルがなくても読取確認で作成しない。schemaやauthorityの差異が問題なら、配置されたSkillの `.withmate-managed-skill.json` の `bundleVersion`、本文、該当releaseの契約を照合する。

## 障害を切り分ける

- toolが見えない、またはtransportに接続できない：起動元WithMateと対象Sessionへの供給を確認する。利用不能な場合に限り、managed Skillが許すCLI fallbackを検討する。Sessionのbindingとprimary checkoutを確認できないままwriteしない。
- structuredなauthority・Settings・validationエラー：接続は別経路に変えず、対象・入力を確認する。無効なproactive createや上限超過をexplicit createへ読み替えない。
- revision競合：現在値を読み直して変更目的を再評価する。同じ更新のrevisionだけ差し替えない。結果不明（`effect: unknown`）ならread-backし、新たなwriteを選ぶ前にユーザーへ確認する。

## 手動STDIOによる開発・診断

手動clientで `withmate-glossary mcp-server` を試す場合は、当該Sessionが供給した次の**変数名**をCodex server設定の `env_vars` に列挙して転送する。実値を固定・複製しない。

- `WITHMATE_AGENT_RUNTIME_BINDING_REFERENCE`
- `WITHMATE_AGENT_RUNTIME_BINDING_REQUIRED`
- `WITHMATE_AGENT_RUNTIME_TURN_CAPABILITY`
- `WITHMATE_AGENT_RUNTIME_APPLICATION_INSTANCE_ID`
- `WITHMATE_AGENT_RUNTIME_GENERATION_ID`

`GLOSSARY_SESSION_BINDING_REQUIRED` では当該Sessionのbindingと、この経路を使う時だけ5変数の転送を確認する。別Sessionの値で補わない。managed HTTPと重複して登録せず、接続経路の変更で操作対象・承認範囲を広げない。
