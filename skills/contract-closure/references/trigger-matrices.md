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

## Review Candidate / Evidence Convergence

展開する範囲:

- provenanceとして分離したbase ref label
- source identityを構成するmode、resolved base commit / tree OID、changed / untracked manifest、file mode、object type、content identity、削除marker、作成recipe、read-only verification recipe
- accepted anchor、Invariant ID、matrix cell定義、trigger済みlens scope、review contract revision / recipe
- targeted / broader check、specialist / targeted closure / holistic review、coverage status、構造収束gate
- Candidate ID、evidence status、通常index、一時index

反例:

- sourceを変えずにcheckを追加しただけでCandidate IDや既存reviewの`current`状態が失効しないか
- source contentまたはfile modeを変更した後、旧Candidateのreviewやcheckを現行証拠として再利用していないか
- source identityとreview contractを同時に変更した後、source identityの失効規則を優先せず、旧Candidateのevidenceを`unconfirmed`へ移行または新Candidateへ再関連付けしていないか
- 既存cellのcoverage statusを`covered`へ更新しただけでCandidate IDを変更していないか
- accepted anchor、Invariant ID、cell定義、lens scopeを変更した後、影響するlensやholistic evidenceを`current`のまま残していないか
- source diff、accepted anchor文字列、Invariant IDが同じでも、anchorの契約上の意味、Invariant定義、supported contract scopeを変更した後、新Candidateを発行せず、またはholistic review対象は変わっていないとして旧holistic evidenceを残していないか
- accepted anchor、Invariant ID、cell定義、lens scopeが同じでも、review contract revision / recipeだけを変更した後に旧Candidateのevidenceを再利用していないか
- review contract変更の影響を受けないlensを、新Candidate上のdelta非影響確認なしに自動継承していないか
- source identity変更後の他lensによるdelta非影響確認を、新Candidate上の新しいreview evidenceではなく旧Candidate evidenceの再関連付けとして記録していないか
- review-contract-only変更後、旧entryのCandidate IDを書き換え、実行Candidateと適用Candidateを同一に見せていないか
- 新Candidateの定義差分非影響確認が、独立したEntry ID、元entryのEntry IDとCandidate ID、確認した定義差分、非影響の根拠を持っているか
- review entryまたはvalidation reportのprojectionからentry固有のresultが欠け、複数entryの結果を区別できなくなっていないか
- 定義差分非影響確認のprojectionからreviewed definition deltaまたはnon-impact rationaleが欠け、origin参照だけで`current`になっていないか
- 旧entryを元Candidateに保持せず、新しい確認entryの代わりに同じentryを`current`として移動していないか
- specialist findingの修正後、finding lensのtargeted closureと他lensのdelta非影響確認より先にholistic reviewへ進んでいないか
- holistic reviewがCandidate IDを問わず、Ledger review entryまたはspecialist evidenceを入力として消費していないか
- Candidate treeを作るために通常のGit indexまたは既存staged変更を変更していないか
- `.git`またはobject databaseへのwrite authorityがない作成側へCandidate tree生成を要求し、`manifest-digest`へ切り替えずreview lifecycleを停止させていないか
- read-only reviewerが`read-tree`、`write-tree`、`hash-object -w`、`update-index`などGit index、object database、worktreeへ書き込むcommandを実行していないか
- manifest作成、reviewer検証、creator-tree前後確認でplain `git status`を使い、optional index refreshを書き戻していないか
- revision peel expressionをquoteせず、PowerShellなどのshellが`^{commit}`または`^{tree}`を別構文や別引数として解釈していないか
- `creator-tree` modeで、作成側が生成したtree OIDが存在しない、読めない、またはtype不一致のとき、reviewerがtreeを再作成していないか
- `manifest-digest`のrecordからmode-only変更、untracked content、symlink target、submodule OID、削除markerの該当項目が欠けていないか
- `manifest-digest`のalgorithm、record framing、path encoding、入力byte列、filter適用、正規化が曖昧で、同じ値を異なるsource stateから生成できないか
- Candidate作成後に`HEAD`やbranchを移動したとき、同じbase ref labelを再解決してmanifestまたはraw diffが変化していないか
- informationalなbase ref labelをsource identity valueまたはidentity recipeの入力へ含め、label文字列の変更だけでCandidateを失効させていないか
- `read-tree`、manifest、raw diffの再生成で、記録済みbase tree / commit OIDではなく現在のbase ref labelを使っていないか
- Candidateを再作成したとき、同じbase ref labelが旧Candidateと別OIDへ解決されたのにsource identity変更として扱わず、または既存Candidateのlabel driftだけで記録済みOIDに基づく証拠を失効させていないか
- reviewerがbase ref labelのdriftを理由に記録済みOIDを置換またはCandidate mismatchとし、固定OIDからの再現を行っていないか
- 一時indexのresolved base OID、対象path、mode、untracked contentがCandidate Definitionのsource identityと一致しているか
- `GIT_INDEX_FILE`が通常indexのpostcondition確認まで残り、一時indexを通常indexとして誤確認していないか
- 一時indexのcleanup失敗を見逃し、staleなindexを後続Candidateで再利用していないか
- 一時index削除後、`GIT_INDEX_FILE`を継承しないfresh processで通常indexのtree OIDとstatusを再確認したか
