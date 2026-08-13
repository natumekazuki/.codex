# Trigger Matrices

変更に該当する節だけを使う。問いを網羅的な一般チェックリストとして消化せず、変更した不変条件を壊す反例へ変換する。

## Explicit Input / Authority / Capability

展開する範囲:

- CLI flag、environment、config、request body、discovery、default
- capabilityの発行、伝播、選択、更新、失効、retry、cleanup
- owner identity、generation、接続先本人確認

反例:

- 明示値が不正なとき、暗黙のdefaultへfallbackしないか
- staleまたはrevokedな値が残ったとき、別ownerへ誤接続しないか
- 複数instanceが同じartifactをpublish / cleanupしたとき、他方を壊さないか
- validation前にsecretやmutation bodyを未確認の相手へ送らないか

## Public API / Validation / Projection

展開する範囲:

- CLI、HTTP、IPC、JSON、generated client、raw client、public export
- runtime validator、shared type、schema、docs、shipped helper
- success、domain error、transport error、unknown input

反例:

- shorthandだけで検証し、raw bodyや別adapterから迂回できないか
- dynamic import、alias、barrel export、bracket accessで境界を迂回できないか
- unknown field、invalid enum、不正な組合せが内部処理へ到達しないか
- internal DTOやerror spreadからprivate fieldが漏れないか
- responseの不正な状態組合せをtypeで構築できないか

## Coupled Invariant / Versioned Selection

展開する範囲:

- provider / catalog revision / model / reasoning depth
- owner / scope / permission、status / run state、schema version / row shape
- create、load、update、clone、import、migration、recovery、retry、fallback
- 組を解決するcanonical source、atomic update、永続化後の再検証

反例:

- 各fieldは単独で妥当でも、tupleとして未対応の組合せにならないか
- 一つのfieldを変更したとき、依存fieldが古い値のまま残らないか
- 既存データのmigrationだけ直し、新規createやcloneが古いdefaultを使わないか
- fallbackが新しいidentityと古いcapability / revisionを混在させないか
- tupleの一部だけを保存し、再読込後に構築不能な状態を作らないか
- validate、persist、public projectionが同じ組合せ規則を使っているか

## Mutation / External Side Effect

展開する範囲:

- validation前、admission前、side effect直前、commit直後、response送信中
- timeout、abort、cancel、process crash、response loss
- initial request、同一request retry、delete後retry
- batchの先頭、中間、末尾での失敗
- operation、correlation owner、request / response / notificationの到着順
- side effect certainty、pending / ambiguous / committed / terminal、owner解放

反例:

- callerへeffect noneを返しながらside effectが実行されないか
- commit後response lossから同じrequestで収束できるか
- 後半failureで前半だけcommitされないか
- all-not-foundなどmutationなしの結果もidempotencyへ記録されるか
- recoveryに必要なpending / ambiguous状態を再起動後に列挙できるか
- responseより先にnotificationが到着しても正しいownerへ帰属するか
- timeoutやterminal後の遅延eventが新しいoperationや別ownerへ誤帰属しないか
- deliveryが曖昧な状態でsafe retry可能なeffect noneを返さないか
- owner解放条件が兄弟operationとfailure timingで一致するか
- mutationのpostcondition検証をcommit後に実行し、検証失敗時にも変更を残していないか
- 対象resourceの存在確認より先にopen / connectが新規resourceを作成していないか

## Owner / Scope / Projection

展開する範囲:

- create、read、write、authorization、projection、subscription、audit、cleanup、recovery
- parent / child、session / run、summary / full、source / derived cache

反例:

- UIだけownerを切り替え、readやauditが旧ownerのまま残らないか
- 親がidleでもchildがrunningのとき、deleteやcapacity判定を誤らないか
- summary projectionをsourceへ書き戻してfull dataを失わないか
- summary権限からfull payloadを取得できないか
- owner削除後もretry、retention、remote cleanupに必要なidentityを保持できるか

## Limit / Concurrency / Resource

展開する範囲:

- per-item、per-batch、concurrent、session / root、provider、process、storage全体
- pagination、stream、chunk、queue、cache lifetime
- memory、CPU、disk、WAL、一時領域、IPC copy

反例:

- per-item上限内の入力を最大並列したとき、aggregate上限を超えないか
- 複数rootやproviderの合計でprocess hard capを超えないか
- cacheやtombstoneがprocess lifetimeで無制限に増えないか
- summary / list APIがfull payloadをhydrateしないか
- transaction内で重いdecode、sanitize、hash、I/Oを実行しないか
- exact limitで `>=` / `>` の意味がcreateとrefreshで一致するか

## Process / Resource Lifecycle

展開する範囲:

- identity resolve、claim / lock、listener、worker / child、application、client bootstrap
- starting、ready、busy、draining、fatal、closed
- startup failure、ready後crash、disconnect、abort、shutdown、replacement
- generation、owner、effect settlement、resource取得と逆順cleanup
- Windows / Unixのidentity、permission、endpoint、queue、process lifecycle

反例:

- 起動deadlineが一部stageだけを覆い、claimやlistener取得で停止しないか
- claimを解放した時点でworker終了、effect settlement、listener closeが揃っているか
- ready後のworker crashで壊れたgenerationを再利用しないか
- startup clientのdisconnectがhost全体を意図せず終了させないか
- abort済みacceptやqueued connectionがcapacityとcleanupを占有し続けないか
- security確認前にsecret-bearing responseまたはrequest bodyを送らないか
- platform別実装が同じidentity、authority、cleanup契約を持つか

## Migration / Repair / Existing Data

展開する範囲:

- supported old schemaごとのempty / populated / malformed state
- column、index、table、foreign key、triggerの適用順序
- 各failure injection point、rollback、再実行、fallback
- backfill、owner preservation、data visibility

反例:

- column追加前に、そのcolumnを使うindexを作らないか
- table rebuildのDROPがFK actionでchild dataを変更しないか
- repair途中の失敗でpartial schemaやdata lossを残さないか
- old rowの追加columnが空値のまま残らないか
- repair不能な新DB候補が、validな旧DB fallbackを妨げないか
- migrationを再実行しても同じ最終状態へ収束するか

## Reactive State / Cache / Async UI

展開する範囲:

- state owner、effect dependency、request generation、subscription lifetime
- in-flight refresh中のevent、out-of-order response、draft / metadata変更
- source state、derived state、error state、loading state

反例:

- metadataだけ変わったときderived previewがstaleにならないか
- draft修正後も古いerrorが操作をblockしないか
- refresh中に受信したeventを捨てて表示がstaleにならないか
- 古いresponseが新しいstateを上書きしないか
- object identityの変化だけで重複requestを発行しないか

## Review Source Identity

high-riskまたはnon-localな同一review cycleでCandidate helperを使う場合だけ展開する。

展開する範囲:

- resolved base commit / tree OID、changed / untracked manifest、file mode、object type、content identity、削除marker
- raw diff digest、作成recipe、read-only verification recipe
- review target、included / excluded scope、review contract revision
- 通常indexと、一時indexを使う場合のauthorityとpostcondition

反例:

- source content、file mode、untracked content、review contractの変更後に旧Candidateまたは旧review resultを再利用していないか
- Candidateをsession handoff、作業再開、commit後、別branch、merge後のsource identityとして扱っていないか
- base ref labelを再解決し、記録済みbase commit / tree OIDと異なるsourceからmanifestやraw diffを作っていないか
- read-only reviewerが`read-tree`、`write-tree`、`hash-object -w`、`update-index`などGit index、object database、worktreeへ書き込むcommandを実行していないか
- plain `git status`のoptional index refresh、replacement object、lazy fetchにより検証対象またはrepository stateを変えていないか
- manifestからmode-only変更、untracked content、symlink target、submodule OID、削除markerが欠けていないか
- digestのalgorithm、record framing、path encoding、入力byte列、filter、正規化が曖昧で、異なるsource stateが同じidentityにならないか
- `creator-tree`で必要なauthorityまたはpostconditionを満たせないのに開始し、途中から別modeへfallbackしていないか
- 一時indexの環境変数やfileが残り、通常indexのpostcondition確認または後続Candidateを汚染していないか
