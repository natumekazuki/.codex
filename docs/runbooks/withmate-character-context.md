# WithMate Memory / Characterの接続設定と障害調査

通常操作はMCP toolの説明・schemaと`AGENTS.md`の保存方針に従う。このrunbookはセットアップと接続障害の調査時に参照する。

## セットアップ

以下はWithMate 6.3.26、MCP server `withmate-character-context` 1.0.0で確認した設定である。実行時のtoolとschemaはMCPの`tools/list`を正本とする。

1. WithMateを起動し、`withmate-memory` commandが配置されていることを確認する。
2. `config.example.toml`の`mcp_servers.withmate-character-context` sectionをlocal `config.toml`へ反映する。STDIO commandは`withmate-memory mcp-server`を使う。
3. 同sectionの`env_vars`に、次の5変数名を指定する。

   - `WITHMATE_AGENT_RUNTIME_BINDING_REFERENCE`
   - `WITHMATE_AGENT_RUNTIME_BINDING_REQUIRED`
   - `WITHMATE_AGENT_RUNTIME_TURN_CAPABILITY`
   - `WITHMATE_MEMORY_RUNTIME_APPLICATION_INSTANCE_ID`
   - `WITHMATE_MEMORY_RUNTIME_GENERATION_ID`

4. 新しいCodex Sessionを開始し、MCP processを再起動する。
5. `codex mcp list`でserverがenabledであることを確認し、MCPの`tools/list`でMemory／Character用toolが公開されていることを確認する。

設定へ保存するのは変数名だけである。値はWithMateがSessionごとのprocessへ注入するため、`env`へ固定しない。接続先は起動元のapplication instanceとMemory runtime generationに固定される。

## 障害の切り分け

- `codex mcp get withmate-character-context`で5変数が転送設定に含まれることを確認する。`env: -`なら`env_vars`の設定と、新規SessionでのMCP再起動を確認する。変数の値や認証情報をログへ出さない。
- `MEMORY_PRINCIPAL_REQUIRED`なら、WithMate本体の起動、5変数の転送、新規Sessionでの再起動を順に確認する。
- generation mismatchや複数instanceのambiguous resultでは、起動元WithMateとSessionの対応を確認する。別runtimeを推測して接続しない。
- CLI fallbackの可否と再試行手順は、MCP toolの説明と返されたerrorに従う。MCP未設定・起動不能・初期化失敗をCLIで迂回せず、接続設定を復旧する。独自databaseやfallback fileを作らない。

呼出しの成否や拒否理由は`withmate-memory character-metrics`で調べる。Memory本文、会話本文、affect evidence、機密情報を調査ログやmetricsへ保存しない。通信失敗後に保存済みか不明な操作は成功扱いせず、toolが定める確認手順に従う。
