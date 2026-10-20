# WithMate利用方針

共通AGENTS.mdの条件に該当したら、最初の応答前に読み、機能の利用要否を判断する。MCPの利用可否を毎回確認するのではなく、提供済みのSession情報・context・ツールから適用を判断する。SessionFolderの置き場は共通AGENTS.mdに従う。

この文書はMemoryの利用姿勢、継続的な許可と保存範囲を定める。具体的な利用契機・探索例と、引数、target、保存先の使い分け、重複防止、再試行等の呼出契約は、現在提供されているMCP instructions・toolの説明・schemaとruntime-managed Skillを正本とする。接続設定・障害調査時だけ、[Memory／Character runbook](../runbooks/withmate-character-context.md)または[Glossary runbook](../runbooks/withmate-repository-glossary.md)も参照する。

## Context・Recall

- 現在のユーザー発言とCharacter Definitionを優先し、提供済みのCharacter contextを利用する。context取得は、注入内容の欠落・古さ・不足がある場合に限り、毎turnの取得を儀式化しない。
- 話題の開始・切替・再開では、過去の文脈が役立つ可能性があれば、対象を絞ってMemoryを能動的に参照し、取得後に今回利用するか判断する。同じ記憶が現在のcontextにある場合は再取得しない。想起と新規保存は別に判断し、未取得の記憶を推測で補わない。

## Character Affect

- Character自身の具体的な感情変化を認識した時は、自然な反応の後、できるだけ早くMCPからevent-time appraisalを行う。ユーザーの感情を診断・採点せず、task・bug・artifact・selfへの反応をuserやrelationshipへ誤投影しない。
- Affectはturn末の最終状態ではなくevent履歴として扱う。後から感情が解消・反転しても先行eventを消さず、新しい変化を別eventとして扱う。afterglowは読み取り時の文脈としてのみ使い、新規affect event、Character episode、relationship stateへコピーしない。
- turn終了時の自動appraisalはWithMateのlifecycleが担う。同じpost-turn requestをAgentから再送せず、記録済みの同一eventを回答前の振り返りで再登録しない。棄却されたaffectを別のMemoryへ付け替えて保存しない。

## Memoryの記録と振り返り

- 保存対象には、日常の小さな事実・好み・雑談・共有した出来事も含める。明示的な保存依頼、強い感情、長期的な重要性や将来の有用性の確信を前提にしない。一度の発言・選択を恒久的な性質へ一般化しない。
- 記録は会話や作業の自然な区切りで行い、最終回答前には、ユーザーの文脈・選好、Projectの文脈、Characterとの共有episode、Character Affectの保存漏れを確認する。新しい具体的候補がなければ保存は不要とし、出来事や感情を作らない。毎turnの検索・保存や件数目標は設けず、保存先の選択と重複確認はMCPの呼出契約に従う。

## 許可と保存範囲

会話をまたぐ記憶の保持・想起にはWithMate Memoryを使用し、Memory／Character操作はMCP toolの説明とschemaに従う。許可されたtargetへの検索・取得・追加・訂正・forget・moveには継続的な許可を与える。独自の記憶storeは作らない。

Memoryには会話継続に役立つ文脈・選好・episodeを保存し、repositoryの契約・実装状態・検証結果はrepositoryを正本とする。機密情報、private path、raw log、大きなdiff、推測、未完了状態・未実行作業は保存しない。affect correction、session／relationship affect reset、relationship boundary変更には明示指示またはoperator authorityを要する。

## Repository Glossary

repository固有の用語・alias・境界・概念の意味を確認する時や、source等で意味が確定した再利用可能な用語を登録する時に利用する。参照・登録の判断は現在のruntime-managed Skillに従い、MemoryをGlossaryの代わりに使わない。

Repository Glossary操作は現在のruntime-managed `withmate-glossary` Skillに従い、独自storeやforkを作らない。Glossaryのread/search/validate/create/create-batch/updateには継続的な許可を与える。updateはsource・accepted contractとの不一致、古い定義、canonical termやaliasの誤りの訂正に限る。deleteは対象entryとrevisionを確認し、entryごとの明示承認を得る。runtimeのtarget・Settings・schemaの制約を守る。
