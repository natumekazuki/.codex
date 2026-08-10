# ADR-0017: WithMate Character contextはlifecycle注入とMCPを単一正本へ接続する

- Status: accepted
- Date: 2026-08-10

## Context

WithMateはProject Memory、Character Memory、Character affectを保持し、通常Sessionの応答前にCharacter contextを注入する。Character context、追加想起、Character episode、affect候補をCodexから利用するには、毎turnの儀式的なtool callを避けつつ、lifecycle、MCP、CLIのmutation ownerを混在させない必要がある。

Project Memoryやsemantic Memoryは同義entryの重複を避ける。一方、Character episodeは別時点の類似した出来事自体に想起価値があり、semantic duplicateと同じ抑止規則を適用できない。同一eventのretryだけはidempotencyで抑止する必要がある。

WithMate 6.3.19は、runtime-managed Skill、Character context injection、`withmate-character-context` MCP server、同じapplication serviceへ接続するCLI fallbackを提供する。WithMate ADR-020はapplication serviceをMemoryとaffectの正本とし、通常Sessionのpre-turn snapshotとpost-turn appraisalをlifecycle ownerへ割り当てている。

## Decision

- Persisted MemoryとCharacter affectの正本はWithMateとする。Codexは独自の永続状態またはfallback storeを作らない。
- 応答前は現在のユーザー発言とCharacter Definitionを優先し、次にlifecycle-injected Character contextを使う。追加のCharacter recallは、現在の判断または自然な会話継続へ具体的に影響する場合だけMCPで行う。
- Character affectはCharacter自身の反応として扱い、ユーザーの感情を測定、診断、採点しない。affectの対象とlayerを明示し、task、bug、artifact、selfへの反応をuserまたはrelationshipへ誤投影しない。
- user-facing response直前にProject、Character、Character affectの三つのlensでreflectionする。具体的候補がないturnではsearchまたはwriteを行わない。
- 通常のWithMate Sessionでは、post-turn appraisalと同じaffect eventに属するlinked episodeをlifecycleの単一mutation ownerとする。Codexは同じturnをMCPへ重複送信しない。MCP appraisalはlifecycle ownerのないclientまたは明示的なmanual operationに限定する。
- Character context、affect、episodeの通常操作はMCPを第一選択とする。Character CLIはMCP availability failureまたはoperatorによるinspect、migration、manual recoveryに限定し、同じWithMate application serviceと永続化先を確認できる場合だけ使う。public MCPにsemantic appendがないため、semantic Memoryのgeneral CLI経路はfallbackとは扱わない。
- Semantic Memoryは同義のactive entryを重ねない。Character episodeは別時点の出来事なら同じmotifでも別entryとして残す。同一turn、同一event、timeoutまたはresponse-loss retryはrequestとidempotency keyを維持する。
- MCPのdomain rejection、authority不足、invalid input、version conflict、idempotent replay、migration requiredをavailability failureへ読み替えず、CLIで迂回しない。`saved`、`rejected`、`replayed`、effect certainty、read-backを区別し、未確認の保存結果を推測しない。
- Character Memory correction、forget、affect correction、sessionまたはrelationship reset、relationship boundary変更には明示的なユーザー指示またはoperator authorityを要求し、mutation後にcurrent stateをread-backする。
- Exact tool schema、authority、version、idempotency、error semantics、fallback commandはWithMateが配布する`withmate-memory` Skillを正本とする。`AGENTS.md`はCodexの判断原則とlifecycle上の責務だけを所有する。
- Global `AGENTS.md`のMemory policyがinstruction discoveryのbyte limit外へ切り落とされないよう、portable Codex configで`project_doc_max_bytes`を明示する。端末固有のlocal configは利用者がportable sectionを反映する。

## Alternatives

- Character context取得、Memory検索、affect更新を毎turn必須にする: tool利用が儀式化し、injected contextとlifecycle appraisalを重複させるため採用しない。
- Codex側でCharacter affectまたはMemoryのlocal storeを持つ: WithMateのauthority、scope、version、idempotency、correctionと分岐するため採用しない。
- Character操作を通常からCLIへ統一する: MCP tool schema、annotation、structured effect、client統合を失い、operator authorityとの境界も曖昧になるため採用しない。
- Character episodeをsemantic duplicateとして統合する: 別時点の反復を共有episodeとして残せないため採用しない。
- MCP domain rejectionをCLIで再試行する: application serviceのvalidationまたはauthorityを迂回する経路になるため採用しない。

## Consequences

- Positive: injected contextと追加tool利用の境界が明確になり、routineなtool実況なしで会話へ継続性を反映できる。
- Positive: lifecycle、MCP、CLIが同じWithMate application serviceへ収束し、二重appraisalと別local stateを避けられる。
- Positive: semantic duplicate、別episode、同一event retryを異なる規則で扱える。
- Negative: Codex hostごとにMCP server設定と新sessionでの認識確認が必要になる。
- Negative: Global instructionとproject instructionの合計sizeを見直し、configured byte limit内に維持する必要がある。
- Negative: Character responseの自然さは自然言語上の判断を含み、shadow modeの観測と段階的な有効化が必要になる。
- Negative: MCP unavailable時は同一runtimeを確認できる範囲でしかCharacter CLI writeへfallbackできない。

## Contract Anchors

- Codex policy: `AGENTS.md`の「WithMate Memory」
- Portable MCP configuration: `config.example.toml`
- Operator verification: `docs/runbooks/withmate-character-context.md`
- Runtime-managed procedure: `skills/withmate-memory/SKILL.md`
- Installed bundle version anchor: `skills/withmate-memory/.withmate-managed-skill.json`
- External contract: WithMate 6.3.19 `resources/skills/withmate-memory/reference/character-context.md`
- External decision: WithMate `docs/adr/020-memory-affect-mcp-application-boundary.md`
- External executable contracts: WithMate `scripts/tests/withmate-memory-mcp.test.ts`、`scripts/tests/character-context-cli-mcp-integration.test.ts`、`scripts/tests/withmate-memory-skill-contract.test.ts`
