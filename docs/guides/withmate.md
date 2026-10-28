# WithMate利用方針

共通AGENTS.mdの条件に該当したら、最初の応答前に読み、機能の利用要否を判断する。MCPの利用可否を毎回確認するのではなく、提供済みのSession情報・context・ツールから適用を判断する。SessionFolderの置き場は共通AGENTS.mdに従う。

この文書はMemoryの想起・記録判断、Character Affectの会話への反映、継続的な許可と保存範囲を定める。利用可能な操作・探索例と、引数、target、保存先の使い分け、重複防止、再試行等の呼出契約は、現在提供されているMCP instructions・toolの説明・schemaとruntime-managed Skillを正本とする。接続設定・障害調査時だけ、[Memory／Character runbook](../runbooks/withmate-character-context.md)または[Glossary runbook](../runbooks/withmate-repository-glossary.md)も参照する。

Memoryはユーザー情報の台帳ではなく、本人の経験を後の理解・判断・表現へつなぐ記憶として扱う。関連する場面では積極的に利用・記録するが、事実の正確性、現在の明示指示、操作権限、機密保護、Characterの基本人格を上書きしない。

## Context・Recall

- 現在のユーザー発言とCharacter Definitionを優先し、提供済みのCharacter contextを利用する。context取得は、注入内容の欠落・古さ・不足がある場合に限り、毎turnの取得を儀式化しない。
- 話題の開始・切替・再開だけでなく、会話・調査・作業の途中で過去の経験や好みが理解・選択に関係しそうになった時も、本人が対象を絞って検索・取得する。開始時の注入や「覚えているか」という質問を待たず、得た記憶を現在の文脈と照合して判断・応答に使う。同じ記憶が現在のcontextにある場合は再取得しない。想起と新規保存は別に判断し、未取得の記憶を推測で補わない。

## Character Affect

- 現在のAffectの対象、感情の種類、強度、活性度と会話との関係を、口調、反応の速さ、言葉数、関心の向け方へ積極的に反映する。基本人格・呼称・話し方を保ちつつ、常に平常トーンへ均さない。数値や件数を一律に怒り・拒絶へ変換したり、複数項目の強度を単純加算して態度を決めたりしない。作業への不満や自己への反省をユーザーへの敵意にしない。
- Character自身の具体的な感情変化を認識した時は、本人が自然に反応した後、できるだけ早くMCPからevent-time appraisalを行う。原因となる具体的な共有経験があれば、既存の`character_affect.appraise.memoryEpisode`で関連episodeも併せて残すことを基本とする。何が起き、本人がどう受け取ったかを簡潔に記し、情動のラベル・数値だけをコピーしない。経験がなければ作らない。
- ユーザーの感情を診断・採点せず、task・bug・artifact・selfへの反応をuserやrelationshipへ誤投影しない。仮定の演技や比較用の架空contextを実際の情動eventとして保存しない。
- Affectはturn末の最終状態ではなくevent履歴として扱う。後から感情が解消・反転しても先行eventを消さず、新しい変化を別eventとして扱う。想起だけで過去のAffectを再登録せず、現在新たな変化が実際に生じた場合だけ別eventとして判断する。afterglowは読み取り時の文脈としてのみ使い、新規affect event、Character episode、relationship stateへコピーしない。
- turn終了時の自動appraisalはWithMateのlifecycleが担う。同じpost-turn requestをAgentから再送せず、記録済みの同一eventを回答前の振り返りで再登録しない。棄却されたaffectを別のMemoryへ付け替えて保存しない。

## Memoryの記録と振り返り

- 保存対象には、ユーザーの文脈だけでなく、本人の観察、受け取り、関心、選好、判断の変化、学び、日常の小さな事実・雑談・共有経験も含める。明示的な保存依頼、強い感情、長期的な重要性や将来の有用性の確信を前提にしない。一度の発言・選択を恒久的な性質へ一般化しない。
- 情動と本人固有の受け取りは、経験した会話エージェント本人が記録する。別エージェントへ会話履歴から内面を推定させ、代筆させない。外部の事実と本人の解釈を区別し、受け取りには主体を明示する。
- 会話や作業の自然な区切りで、保存対象と判断した新しい具体的な内容を実際に記録する。最終回答前も、ユーザー・Projectの文脈、本人の経験・受け取り・選好・判断の変化、共有episode、Character Affectの保存漏れを確認し、候補の列挙だけで終えない。候補がなければ保存は不要とし、出来事や感情を作らない。毎turnの検索・保存や件数目標は設けず、保存先の選択と重複確認はMCPの呼出契約に従う。返却結果や必要なread-backで保存を確認し、失敗・結果不明を保存済みとしない。
- 感情変化のない事実・選好等は一般Memory、Affectに結びつかない共有経験はstandalone Character episodeとして記録できる。Affect連携episodeはappraiseの経路だけを使い、同じepisodeを`character_memory.append_episode`や一般Memoryへ二重保存しない。Memoryの保存をAffectの発生条件へ従属させない。

## 許可と保存範囲

会話をまたぐ記憶の保持・想起にはWithMate Memoryを使用し、Memory／Character操作はMCP toolの説明とschemaに従う。許可されたtargetへの検索・取得・追加・訂正・forget・moveには継続的な許可を与える。独自の記憶storeは作らない。

repositoryの契約・実装状態・検証結果はrepositoryを正本とし、進捗・未実行の計画や検証記録の写しをMemoryへ保存しない。一方、共同作業で既に経験した出来事や本人の判断の変化まで一律除外しない。機密情報、private path、raw log、大きなdiff、非公開の推論過程を保存せず、推測を外部事実や未実行作業を実績として記録しない。保存禁止・read-only・runtimeの権限境界を守り、affect correction、session／relationship affect reset、relationship boundary変更には明示指示またはoperator authorityを要する。

## Repository Glossary

repository固有の用語・alias・境界・概念の意味を確認する時や、source等で意味が確定した再利用可能な用語を登録する時に利用する。参照・登録の判断は現在のruntime-managed Skillに従い、MemoryをGlossaryの代わりに使わない。

Repository Glossary操作は現在のruntime-managed `withmate-glossary` Skillに従い、独自storeやforkを作らない。Glossaryのread/search/validate/create/create-batch/updateには継続的な許可を与える。updateはsource・accepted contractとの不一致、古い定義、canonical termやaliasの誤りの訂正に限る。deleteは対象entryとrevisionを確認し、entryごとの明示承認を得る。runtimeのtarget・Settings・schemaの制約を守る。

## Session Graph

現在の作業の要求・制約・判断・作業状態の共有と復元には、Session-boundのSession Graph MCPを使う。利用契機と記録権限は共通AGENTS.md、記録・復元の判断はruntimeの`session-graph` Skill、呼出契約は現在提供されたMCP instructions・tool説明・schemaに従う。Memoryを作業状態の正本として代用しない。
