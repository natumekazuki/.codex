# WithMate Memory / Characterの接続設定と障害調査

通常操作は現在提供されているMCP instructions・tool説明・schemaと[Memory・Affect・共有情報の利用](../guides/withmate.md)に従う。このrunbookはWithMate 6.3.29の接続設定と接続障害の調査時に参照する。

## セットアップ

WithMateから起動するprovider Sessionは、WithMateの共有localhost HTTP MCPへ自動接続する。Memory／CharacterのCodex登録名は`withmate-memory-http`、endpointは`/mcp/memory`である。WithMateが接続URLと当turnの短命tokenを一時設定へ渡すため、`config.toml`への手動登録は不要であり、URLやtokenを永続設定・設定例・ログへ保存しない。

1. WithMateでCodexのSessionを開始する。
2. そのSessionへ公開されたMCPの`tools/list`で、`memory.*`とCharacter用toolが利用できることを確認する。実行時のtool名・schema・利用条件は現在のMCPを正本とする。
3. 必要な操作に対応するread-only toolで、許可されたtargetや取得結果を確認する。接続確認だけを目的にMemoryやAffectを書き込まない。

通常の`codex mcp list`は永続設定の確認に使う。WithMateがSessionへ渡す一時設定の接続成否は、それだけでは判定せず、当該Sessionのtool公開・応答で確認する。

## 手動STDIOによる開発・診断

手動clientの開発・診断では、WithMateが配置する`withmate-memory mcp-server`をSTDIO server commandとして使用できる。これは通常のmanaged HTTP接続とは別経路であり、HTTPの未接続を迂回するための自動切替ではない。

Codexを手動STDIO clientにする場合は、診断用server設定の`env_vars`で、WithMateが当該Sessionへ注入した次の変数を転送する。

- `WITHMATE_AGENT_RUNTIME_BINDING_REFERENCE`
- `WITHMATE_AGENT_RUNTIME_BINDING_REQUIRED`
- `WITHMATE_AGENT_RUNTIME_TURN_CAPABILITY`
- `WITHMATE_MEMORY_RUNTIME_APPLICATION_INSTANCE_ID`
- `WITHMATE_MEMORY_RUNTIME_GENERATION_ID`

設定へ保存するのは変数名だけであり、実値を`env`へ固定・複製しない。接続先は起動元のapplication instanceとMemory runtime generationに固定される。設定を変更した場合は診断用clientを再起動し、initializeと`tools/list`を確認する。

## 障害の切り分け

- managed HTTPでtoolが公開されない場合は、WithMate本体の起動と当該Sessionへの接続設定の供給を確認する。URLやtokenを推測・固定せず、起動元WithMateから新しいSessionで確認する。
- 手動登録もある場合は、同じ機能の重複登録と実際に利用している経路を確認する。共有設定例の更新だけで既存のlocal登録が消えたとは扱わず、第三者MCPを一括変更しない。
- 手動STDIOでは`codex mcp get <手動登録名>`で5変数が転送設定に含まれることを確認する。`env: -`なら`env_vars`とclientの再起動を確認する。変数の値や認証情報をログへ出さない。
- `MEMORY_PRINCIPAL_REQUIRED`なら、起動元WithMateとprovider Sessionのbindingを確認する。手動STDIOの場合は5変数の転送も確認する。
- generation mismatchや複数instanceのambiguous resultでは、起動元WithMateとSessionの対応を確認する。別runtimeを推測して接続しない。
- CLI fallbackの可否と再試行手順は、MCP toolの説明と返されたerrorに従う。MCP未設定・起動不能・初期化失敗をCLIで迂回せず、接続設定を復旧する。独自databaseやfallback fileを作らない。

呼出しの成否や拒否理由は`withmate-memory character-metrics`で調べる。Memory本文、会話本文、affect evidence、機密情報を調査ログやmetricsへ保存しない。通信失敗後に保存済みか不明な操作は成功扱いせず、toolが定める確認手順に従う。

## 背景登録と添付の診断

背景処理の実行結果と操作診断はWithMateの`userData/logs/background-failures.jsonl`で、Agentの終了状態と個々のtool操作の成否・保存効果を分けて読む。`completed`は全件保存成功の証明ではなく、操作拒否の併存だけで実行全体を`failed`へ読み替えない。全操作拒否も正常な登録不要とは扱わない。

このログには正常終了した実行の操作拒否・失敗・結果不明も記録される。ログの存在だけから実行失敗を推定せず、先行する保存を巻き戻したり、実行全体を無条件に再送したりしない。

MCP／CLIが`WITHMATE_MEMORY_INVALID_INPUT`を返した場合は、`error.details.tool`と`error.details.issues`のfield位置・制約・代替条件を読んで入力を修正し、呼び直す。unionの候補内の条件はすべて必要だが、候補間は代替関係であり、全候補を同時に満たす必要はない。公開schemaでの拒否は当該呼出しが保存前に拒否されたことを示し、`effect: none`を他の操作の保存まで未実施という意味にしない。

この入力拒否を認可・通信・保存の障害やCLI fallbackの許可へ読み替えず、変更なしの要求を繰り返さない。Memory本文・会話本文・prompt・tool引数や応答本文・入力値全体・secret・認証情報を追加dumpしない。

背景thread・前回失敗・待機状態はアプリ再起動をまたいで復元されないが、保存済みMemory・Affectは保持される。threadの継続や失敗情報の有無から保存状態を推測しない。

添付の取込元・復元先とローカルwriteの可否は当該呼出しの許可範囲で確認する。復元の拒否をMCP全体の未接続と同一視したり、権限を緩めて迂回したりしない。適用境界は[WithMate利用guide](../guides/withmate.md)に従う。
