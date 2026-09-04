# ADR-0017: WithMate Character contextはlifecycle注入とMCPを単一正本へ接続する

- Status: accepted
- Date: 2026-08-10
- Updated: 2026-09-05

## Context

WithMateはProject Memory、Character Memory、Character affectを保持し、通常Sessionの応答前にCharacter contextを注入する。Character context、追加想起、Character episode、affect候補をCodexから利用するには、毎turnの儀式的なtool callを避けつつ、lifecycle、MCP、CLIのmutation ownerを混在させない必要がある。

Project Memoryやsemantic Memoryは同義entryの重複を避ける。一方、Character episodeは別時点の類似した出来事自体に想起価値があり、semantic duplicateと同じ抑止規則を適用できない。同一eventのretryだけはidempotencyで抑止する必要がある。

WithMate 6.3.26は、Character context injection、Provider共通の`withmate-character-context` MCP server、同じapplication serviceへ接続するCLI fallbackを提供する。通常Sessionのmandatory post-turn appraisalはlifecycleが所有し、turn中に具体的な感情変化を認識したAgentはMCPからevent-time appraisalを行える。Memory runtime discoveryはapplication instanceとruntime generationを分離し、Session-bound providerを起動元のtupleへ固定する。別Sessionのsession-layer affectは、保存状態を変更しないread-time afterglowとしてeffective contextへ投影される。

## Decision

- Persisted MemoryとCharacter affectの正本はWithMateとする。Codexは独自の永続状態またはfallback storeを作らない。
- 応答前は現在のユーザー発言とCharacter Definitionを優先し、次にlifecycle-injected Character contextを使う。追加のCharacter recallは、現在の判断または自然な会話継続へ具体的に影響する場合だけMCPで行う。
- Character affectはCharacter自身の反応として扱い、ユーザーの感情を測定、診断、採点しない。affectの対象とlayerを明示し、task、bug、artifact、selfへの反応をuserまたはrelationshipへ誤投影しない。
- user-facing response直前にProject、Character、Character affectの三つのlensでreflectionする。具体的候補がないturnではsearchまたはwriteを行わない。
- Character affectはturn末の最終状態ではなくevent履歴として扱う。具体的な感情変化を認識したAgentは、自然な反応の後、できるだけ早くMCPからappraiseする。後から感情が解消、反転、減衰しても先行eventを消さず、別eventとして追加する。
- cross-session affect afterglowはread-time projectionとしてだけ利用し、新規affect event、Character Memory episode、relationship stateへコピーしない。source Sessionのidentityや根拠を公開projectionから推測しない。
- lifecycleは通常Sessionのmandatory post-turn appraisalを所有するが、event-time appraisalの単一ownerではない。Agentはlifecycleの同じpost-turn requestをMCPへ再送しない。即時eventと後続のpost-turn eventは、意味が似ていても別eventとして保存できる。
- Affect eventと同じ出来事に属するlinked episodeは同じappraisalへ含め、`character_memory.append_episode`から重複mutationしない。
- Character context、affect、episode、general semantic Memoryの通常操作はMCPを第一選択とする。CLIはMCP availability failureまたはoperatorによるinspect、migration、manual recoveryに限定し、同じWithMate application serviceと永続化先を確認できる場合だけ使う。
- Semantic Memoryは同義のactive entryを重ねない。Character episodeとCharacter affect eventは別時点または別の根拠を持つ出来事なら、意味やmotifが似ていても別entryまたは別eventとして残す。同一eventのtimeout、response loss、client resendだけはrequestとidempotency keyを維持する。
- runtime bindingで解決されたAgentは、許可された明示targetのMemoryをユーザーの代理として自律的に検索、取得、追加、訂正、forget、moveできる。許可targetは`user-global`、明示Project、actor Session自身のCharacter、actor Session自身のCharacterと明示Projectの組み合わせに限定し、別Characterをownerに持つtargetは読み書きとも拒否する。
- Memoryの訂正、forget、moveは具体的な理由とidempotency keyを伴わせ、mutation後にcurrent stateをread-backする。general Memoryのbulk forgetは実行前にdry-runする。
- MCPのdomain rejection、authority不足、invalid input、version conflict、idempotent replay、migration requiredをavailability failureへ読み替えず、CLIで迂回しない。`saved`、`rejected`、`replayed`、effect certainty、read-backを区別し、未確認の保存結果を推測しない。
- Session-bound Memory operationは起動元のapplication instanceとMemory runtime generationへ固定し、別instanceまたは再起動後のgenerationへfallbackしない。generation mismatchとambiguous selectionはstructured discovery resultとして扱い、transport availability failureへ読み替えない。
- affect correction、sessionまたはrelationship affect reset、relationship boundary変更には明示的なユーザー指示またはoperator authorityを要求し、mutation後にcurrent stateをread-backする。
- Exact tool schemaとannotationはMCPの`tools/list`、runtimeのauthority、version、idempotency、error semantics、fallback commandはWithMateのrelease contractを正本とする。`AGENTS.md`はCodexの判断原則とstanding authorizationだけを所有し、端末設定と運用手順はrunbookへ置く。
- CodexのSTDIO MCP設定は、WithMateがCodex processへ注入するSession binding、turn capability、runtime identityの5変数名を`env_vars`へ列挙する。値はSessionごとに変わるため、固定値を`config.toml`へ保存しない。
- Global `AGENTS.md`のMemory policyがinstruction discoveryのbyte limit外へ切り落とされないよう、portable Codex configで`project_doc_max_bytes`を明示する。端末固有のlocal configは利用者がportable sectionを反映する。

## Alternatives

- Character context取得、Memory検索、affect更新を毎turn必須にする: tool利用が儀式化し、具体的な候補がないturnでも不要な処理を発生させるため採用しない。
- Affectをturn末の最終状態だけで保存する: turn中に発生して後から解消または反転した感情が失われ、event履歴として再構成できないため採用しない。
- task由来の一時的なaffectをrelationship layerへ昇格する: 長期的な関係状態へ短期の作業感情を混入させるため採用しない。
- Codex側でCharacter affectまたはMemoryのlocal storeを持つ: WithMateのauthority、scope、version、idempotency、correctionと分岐するため採用しない。
- Character操作を通常からCLIへ統一する: MCP tool schema、annotation、structured effect、client統合を失い、operator authorityとの境界も曖昧になるため採用しない。
- Character episodeをsemantic duplicateとして統合する: 別時点の反復を共有episodeとして残せないため採用しない。
- MCP domain rejectionをCLIで再試行する: application serviceのvalidationまたはauthorityを迂回する経路になるため採用しない。

## Consequences

- Positive: injected contextと追加tool利用の境界が明確になり、routineなtool実況なしで会話へ継続性を反映できる。
- Positive: lifecycle、MCP、CLIが同じWithMate application serviceへ収束し、別local stateを避けられる。
- Positive: turn中に解消または反転した感情もeventとして保持し、semantic duplicate、別episode、別affect event、同一event retryを異なる規則で扱える。
- Negative: Codex hostごとにMCP server設定、`env_vars`、新Sessionでの認識確認が必要になる。
- Negative: Global instructionとproject instructionの合計sizeを見直し、configured byte limit内に維持する必要がある。
- Negative: Character responseの自然さは自然言語上の判断を含み、shadow modeの観測と段階的な有効化が必要になる。
- Negative: MCP unavailable時は同一runtimeを確認できる範囲でしかCharacter CLI writeへfallbackできない。

## Contract Anchors

- Codex policy: `AGENTS.md`の「WithMate-managed Context and Repository Metadata」
- Portable MCP configuration: `config.example.toml`
- Operator verification: `docs/runbooks/withmate-character-context.md`
- Runtime procedure: `docs/runbooks/withmate-character-context.md`
- External contract: WithMate 6.3.26 `docs/adr/024-provider-common-memory-mcp-boundary.md`
- External decision: WithMate `docs/adr/020-memory-affect-mcp-application-boundary.md`、`docs/adr/024-provider-common-memory-mcp-boundary.md`
- External executable contracts: WithMate `scripts/tests/withmate-memory-mcp.test.ts`、`scripts/tests/character-context-cli-mcp-integration.test.ts`、`scripts/tests/withmate-memory-runtime-discovery.test.ts`、`scripts/tests/character-affect-storage.test.ts`
