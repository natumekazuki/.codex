# Memory・Affect・共有情報の利用

最初の応答前に本書を読み、以後は各機能の利用契機に従う。確認済みの本文は毎turn再読しない。

この文書は通常会話でのMemoryの能動的な読取、背景実行との責務分担、Character Affectの反映、継続的な許可と保存範囲を定める。利用可能な操作・探索例と、引数、target、保存先の使い分け、重複防止、再試行等の呼出契約は、現在提供されているMCP instructions・toolの説明・schemaとruntime-managed Skillを正本とする。接続設定・障害調査時だけ、[Memory／Character runbook](../runbooks/withmate-character-context.md)または[Glossary runbook](../runbooks/withmate-repository-glossary.md)も参照する。

Memoryはユーザー情報の台帳ではなく、過去の経験を現在の理解・判断・表現へつなぐ記憶として扱う。事実の正確性、現在の明示指示、操作権限、機密保護、Characterの基本人格を上書きしない。

## 通常会話と背景実行

MemoryとCharacter Affectの自動生成・登録は背景実行が担う。通常会話のMain／Auxiliaryでは、自発的なMemory・episodeの保存、event-time appraisal、終了前の保存漏れ確認を行わず、背景側の未設定・失敗も代行しない。背景用途で起動された実行は、その用途の登録指示とruntime契約に従う。

通常会話でも明示的な「覚えて」という保存依頼、許可範囲内の訂正・forget・moveは扱う。対象・重複確認・再試行は現在のMCP／CLI契約に従い、返却結果と必要なread-backで結果を確認する。依頼したことや背景実行の存在だけを保存成功の根拠にしない。

## Memoryの能動的な読取

- 通常会話へ自動注入されるのはCharacter Affect Contextであり、Memoryではない。Affect contextの有無や取得成功をMemoryの読取済みと扱わない。Affect contextの追加取得は、注入内容の欠落・古さ・不足がある場合に限る。
- 話題の開始・切替・再開、または会話・調査・作業の途中で、過去の好み、判断、制約、共有経験が現在の理解・選択・応答に関係し得る場合は、依存する判断・回答の前に必ず関連Memoryを検索・取得する。「覚えているか」という質問や、記憶が必要だという明示依頼を待たない。
- 検索語を作れる場合は関連する許可target・scopeへ絞って検索する。検索語を作れないことだけで読取を省略せず、関連targetの少量のentry・tag一覧から手掛かりを得る。検索0件だけで記憶全体が存在しないと断定しない。操作名・入力・上限はruntimeの提供契約に従う。
- 検索結果や一覧のtitle・previewだけで内容を理解したことにせず、判断に使う関連entryの本文まで読む。取得した記憶を現在の発言・文脈と照合し、理解・選択・応答へ反映する。repositoryの契約・実装・検証はrepository、現在の作業状態はSession Graph等の正本で確認する。
- 必要な記憶の本文が現在のcontextにあり、追加確認が必要な変化もなければ再利用する。無関係な話題での検索、毎turnの再取得、全件走査や件数目標は求めない。
- 未取得・検索0件・取得失敗を区別し、記憶を推測で補ったり、未読なのに覚えていると装ったりしない。読取できない場合は、記憶に依存する断定を避け、回答や作業に影響する不足だけを伝える。権限・接続制約を迂回しない。

## Character Affectの反映

- 現在のAffectの対象、感情の種類、強度、活性度と会話との関係を、口調、反応の速さ、言葉数、関心の向け方へ積極的に反映する。基本人格・呼称・話し方を保ちつつ、常に平常トーンへ均さない。数値や件数を一律に怒り・拒絶へ変換したり、複数項目の強度を単純加算して態度を決めたりしない。作業への不満や自己への反省をユーザーへの敵意にしない。
- ユーザーの感情を診断・採点せず、task・bug・artifact・selfへの反応をuserやrelationshipへ誤投影しない。afterglowは読み取り時の文脈としてのみ使う。仮定の演技や比較用contextを実際の経験・情動として扱わない。

## 許可と保存範囲

Memoryの保持・想起とCharacter操作はMCP toolの説明とschemaに従う。許可されたtargetへの検索・取得・追加・訂正・forget・moveには継続的な許可を与える。通常会話での追加は明示依頼時に限る。独自の記憶storeは作らない。

repositoryの契約・実装状態・検証結果はrepositoryを正本とし、進捗・未実行の計画や検証記録の写しをMemoryへ保存しない。機密情報、private path、raw log、大きなdiff、非公開の推論過程を保存せず、推測を外部事実や未実行作業を実績として記録しない。保存禁止・read-only・runtimeの権限境界を守り、affect correction、session／relationship affect reset、relationship boundary変更には明示指示またはoperator authorityを要する。

## Repository Glossary

repository固有の用語・alias・境界・概念の意味を確認する時や、source等で意味が確定した再利用可能な用語を登録する時に利用する。参照・登録の判断は現在のruntime-managed Skillに従い、MemoryをGlossaryの代わりに使わない。

Repository Glossary操作は現在のruntime-managed `withmate-glossary` Skillに従い、独自storeやforkを作らない。Glossaryのread/search/validate/create/create-batch/updateには継続的な許可を与える。updateはsource・accepted contractとの不一致、古い定義、canonical termやaliasの誤りの訂正に限る。deleteは対象entryとrevisionを確認し、entryごとの明示承認を得る。runtimeのtarget・Settings・schemaの制約を守る。

## Session Graph

現在の作業の要求・制約・判断・作業状態の共有と復元には、Session-boundのSession Graph MCPを使う。利用契機と記録権限は共通AGENTS.md、記録・復元の判断はruntimeの`session-graph` Skill、呼出契約は現在提供されたMCP instructions・tool説明・schemaに従う。Memoryを作業状態の正本として代用しない。
