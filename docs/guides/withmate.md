# WithMate Memory・Character・Glossaryの操作

該当機能を使う前に読む。SessionFolderの置き場は共通AGENTS.mdに従う。接続設定・障害調査時だけ、[Memory／Character runbook](../runbooks/withmate-character-context.md)または[Glossary runbook](../runbooks/withmate-repository-glossary.md)も参照する。

会話をまたぐ記憶の保持・想起にはWithMate Memoryを使用し、Memory／Character操作はMCP toolの説明とschemaに従う。許可されたtargetへの検索・取得・追加・訂正・forget・moveには継続的な許可を与える。独自の記憶storeは作らない。

Memoryには会話継続に役立つ文脈・選好・episodeを保存し、repositoryの契約・実装状態・検証結果はrepositoryを正本とする。機密情報、private path、raw log、大きなdiff、推測、未完了状態・未実行作業は保存しない。affect correction、session／relationship affect reset、relationship boundary変更には明示指示またはoperator authorityを要する。

Repository Glossary操作は現在のruntime-managed `withmate-glossary` Skillに従い、独自storeやforkを作らない。Glossaryのread/search/validate/create/create-batch/updateには継続的な許可を与える。updateはsource・accepted contractとの不一致、古い定義、canonical termやaliasの誤りの訂正に限る。deleteは対象entryとrevisionを確認し、entryごとの明示承認を得る。runtimeのtarget・Settings・schemaの制約を守る。
