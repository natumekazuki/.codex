---
name: contract-closure
description: 境界、public API、永続化、migration、外部副作用、認可、並行処理、resource limit、owner / scope変更を実装・修正・reviewするとき、変更した不変条件と複合値の組を兄弟入口、状態遷移、failure timing、aggregate scope、public projection、executable contractまで展開し、独立した反証reviewで閉じる。review findingやbug fixを局所修正で終わらせず、同じ不変条件familyの再発を防ぐときに使う。
---

# Contract Closure

変更行ではなく、変更した不変条件の到達範囲を確認する。green testや指摘箇所の修正だけで完了扱いにしない。

## Workflow

1. 変更またはfindingを、観測されたcaseと、その背後の不変条件へ分ける。
2. 関連するsource、test、type、schema、static check、accepted ADR、外部consumerを読み、accepted contractの根拠とexact anchorを特定する。
3. capability、operation、owner、状態、resource scopeが同じ兄弟経路を検索し、supported scopeと対象外を分ける。
4. 単独では妥当でも組合せで不正になるfield、version、generation、owner / scopeを一つの複合不変条件として列挙する。
5. 該当triggerの展開軸を `references/trigger-matrices.md` から選ぶ。複数該当する場合は必要な節だけを組み合わせ、選ばなかった高リスク軸には短い理由を付ける。
6. sourceまたはexecutable contractを編集する前に、task-localなClosure Mapと選択したInvariant Matrixの行をPre-Implementation Closure Planとして固定する。主要なfailure mode、consumerへの観測可能な影響、最も直接的な確認方法を対応付け、Accepted Contract Gateを`ready`または`unresolved`と判定する。
7. `ready`の場合だけ編集へ進み、Pre-Implementation Closure PlanのInvariant IDとmatrix行を後続工程でも維持する。
8. 各不変条件を最も強い実行可能な場所へ置く。type / schema / shared validation / static checkで強制できる契約をtestだけへ退避しない。
9. 実装または修正後、Pre-Implementation Closure Planで選んだfailure modeのtargeted checkとSibling Sweepを行う。
10. 非局所的または高リスクな変更にはCandidate Definitionを凍結し、Evidence Ledgerへcheckとreviewを記録しながら、triggerされたreview lensでIndependent Closure Reviewを行う。
11. 未確認cell、意図的な例外、実行不能なcheckを残リスクとして報告する。

## Accepted Contract Gate

実装前に、契約の根拠、適用範囲、主要なfailure mode、直接検証を確定する。この判定は`contract-closure`をtriggerするchange / build / fixだけに適用し、pure refactor、局所的な機械変更、文言変更には適用しない。

- 根拠は、明示されたユーザー要求、public protocol / schema、accepted ADR、外部consumer、または根拠を確認できる既存のexecutable contractに置く。
- external schemaやprotocolへ依存する場合は、version、revision、checksum、JSON pointerなど、requiredness、default、enum、failure semanticsを再確認できるexact anchorを残す。
- 現在のsourceやtestが存在することだけをaccepted contractにしない。
- 既存のClosure MapとInvariant Matrixから今回の変更がtriggerする軸だけを選ぶ。関係しない高リスク軸を空欄埋めのために展開しない。
- 根拠が競合し、required / optional、default、failure semantics、supported scope、外部consumer互換性、後戻り困難な永続化・migration・security上の選択、または業務ルールの結論が変わる場合は、reviewerに選択させず`unresolved`とする。
- `unresolved`ではsourceとexecutable contractを編集しない。ユーザーには、確定できない問い、確認した根拠、選択肢ごとのconsumer影響、根拠がある場合の推奨案だけを短く示し、自由記述のチェックリストや承認作業を求めない。
- 調査量が多い、内部実装方法が未確定、複数の内部実装案がある、または追加情報があると便利という理由だけで`unresolved`にしない。既存の正本から安全に解決できる内容はCodexが判断する。
- 必要な情報が揃っている場合は、ユーザーによる記入や承認を要求せず`ready`とし、実装へ進む。

## Pre-Implementation Closure Plan

sourceまたはexecutable contractを編集する前に、会話または既存のtask-local artifactへ必要な項目だけを固定する。Pre-Implementation Closure Planは、Accepted Contract Gateの状態、下記のClosure Map、選択したInvariant Matrixの行をまとめたtask-localな見方であり、同じ情報を持つ別のartifactではない。独立したplan fileや恒久文書を既定にしない。

```text
Pre-Implementation Closure Plan:
Gate status: ready | unresolved
Unresolved contract decisions:
Closure Map: <下記の必要なfield>
Invariant Matrix: <今回選んだ行>
```

- failure modeごとに、現実的な到達条件、consumerから観測できる影響、最も直接検出するexecutable contractまたは理由付きの代替確認を対応付ける。
- mock、spy、metadata、static checkを選ぶ場合は、それが対象failureを最も直接検出する安定境界である理由を示す。build成功や内部callの確認だけで、利用者から観測可能なfailureの検証を代用しない。
- `Gate status: ready`は、accepted contractとexact anchor、supported scopeと対象外、変更する不変条件とcanonical owner、同じ不変条件を共有する兄弟経路、主要なfailure mode、consumer影響、直接検証、未確定判断の有無を確定できた状態とする。
- `Gate status: unresolved`は、信頼できる根拠が不足または競合し、選択によってaccepted behaviorが変わる状態に限る。read-only調査とユーザー確認を続け、`ready`へ更新するまでsourceとexecutable contractを編集しない。
- 実装中にaccepted contract、supported scope、canonical owner、外部consumerのいずれかが変わった場合は、新たな編集を止めてこのゲートを再判定する。既存のworktree変更は巻き戻さず、`unresolved`なら回答を得るまで追加編集しない。
- Pre-Implementation Closure Planで固定したInvariant ID、scope、failure mode、consumer影響、直接検証を、test設計、targeted check、Invariant Matrix、specialist review、Review Brief、validation reportへ同じ意味のまま引き継ぐ。実装後に新しい契約軸が判明した場合もreviewだけへ追加せず、このゲートへ戻る。

## Closure Map

会話またはtask-local noteへ、必要な項目だけ短く作る。恒久文書を既定にしない。

```text
Accepted contract / exact anchor:
Supported scope / excluded scope:
Invariant ID / definition / canonical owner:
Coupled invariants / valid combinations:
Trigger:
Canonical anchors:
Sibling channels:
State / operation sequences:
Failure modes / reachability:
Consumer impacts / public projections:
Owner / scope / projections:
Resource scopes:
Counterexamples:
Reachability / occurrence evidence:
Promotion span / disposition:
Direct verifications / executable contracts / stable boundaries:
Unresolved contract decisions:
Independent review evidence:
Uncovered risks:
```

空欄を埋めることを目的にしない。今回の変更で意味が変わる軸だけを選び、選ばなかった高リスク軸には理由を付ける。

## Invariant Matrix

変更した不変条件familyごとに、兄弟経路とfailure timingをmatrixへ置く。行または列は変更に応じて選び、一般チェックリストとして全項目を埋めない。

```text
Invariant ID:
Accepted anchor:
Canonical owner:

| Sibling channel | Coupled values | State / evidence order | Failure mode / timing | Consumer impact / public projection | Owner / effect certainty | Direct verification / executable anchor | Cell status |
```

`Cell status`は次のいずれかにする。

- `planned`: Pre-Implementation Closure Planでfailure modeと直接検証を対応付け、実装と確認の実行前である
- `covered`: sourceとexecutable contractまたは理由付きの直接確認で閉じた
- `anchored-exception`: accepted contractの根拠を持つ意図的な例外
- `residual-risk`: 発生条件、影響、検知、復旧、follow-up要否を分類した
- `unresolved`: 契約または反例の確認が不足し、Candidateをreviewへ渡せない

Candidate Definitionにはcellの軸と判定条件を含むmatrix cell definitionを固定し、`Cell status`はEvidence Ledgerのcoverage statusとして更新する。`unconfirmed`はEvidence Ledgerのcheck / review entry専用であり、Matrix cellへ設定しない。

Pre-Implementation Closure Planで選んだcellは`planned`から開始し、実装と直接検証の結果で`covered`、`anchored-exception`、`residual-risk`、`unresolved`のいずれかへ更新する。Candidateをreviewへ渡す時点では`planned`を残さない。

観測されたcaseを閉じただけで同じInvariant IDの兄弟cellを未確認にしない。無関係なoperation、platform、既存負債へ無制限に広げず、同じcapability、owner、state、resource scope、public projectionを共有する範囲へ限定する。

## Candidate Definition and Evidence Ledger

high-risk / non-localな変更でIndependent Closure Reviewを行う場合は、source、適用可能なexecutable contract、targeted check、該当する構造収束gateが揃ったexact source stateをtask-localに凍結する。

### Canonical Boundary

- Candidate Definitionのfieldと意味、source identityの生成・read-only検証、Candidate preflight、Candidate失効、Evidence Ledgerのentryとstatus、Invariant Matrix、lens選択、Review BriefはこのSkillだけで規範的に定義する。
- `AGENTS.md`はCandidate reviewの開始条件、specialist reviewとfinding対応の合流順序、holistic reviewの開始条件、finding分類、review回数、完了gateを定め、この節のfieldや失効アルゴリズムを再定義しない。
- `agents/slice_reviewer.toml`は通常sliceのbounded targeted review、`agents/targeted_reviewer.toml`は高リスクtargeted review、specialist review、targeted closure、`agents/reviewer.toml`はholistic complete-diff reviewのread-only安全境界、受け取れる情報、findingとcoverageの出力を定める。各reviewerはこの節のReview Briefを検証し、CandidateやLedgerの意味を独自に補完または変更しない。
- `skills/validation-report/`はtask-localなCandidate evidenceをuser-facingな完了報告へ投影する。表示のためにCandidate identityやevidence statusを再計算しない。

```text
Candidate Definition:
Candidate ID:
Base ref label (informational):
Resolved base commit OID:
Resolved base tree OID:
Source identity mode: manifest-digest | creator-tree
Source identity value:
Creation recipe / authority:
Read-only verification recipe:
Candidate tree OID: <OID or not applicable>
Changed / untracked path manifest:
Supported-scope cleanliness recipe / result:
Raw diff command:
Raw diff digest: <algorithm:value over exact stdout bytes>
Accepted contract anchors:
Accepted contract meaning:
Supported contract scope:
Review contract revision / recipe:
Invariant IDs / definitions / matrix cell definitions:
Triggered lens scope:

Evidence Ledger:
Logical change ID:
Candidate ID:
Evidence entries:
  Entry ID / kind / executed-on Candidate ID / origin entry ID and Candidate ID (confirmation only) / result / reviewed definition delta (confirmation only) / non-impact rationale (confirmation only) / evidence status:
Structural convergence gate / result:
Review entries:
  Entry ID / review kind / executed-on Candidate ID / origin entry ID and Candidate ID (confirmation only) / result / reviewed definition delta (confirmation only) / non-impact rationale (confirmation only) / lens / reviewed and unreviewed cells / evidence status:
Review-cycle state:
  Full-review gate / holistic discovery Entry ID / executed-on Candidate ID / immutable result / holistic review count:
Final Candidate closure chain:
  Current direct-check Entry IDs / targeted-closure Entry IDs / specialist-cell Entry IDs:
Coverage status:
Validation gaps / hardening candidates / residual risks:
```

- Candidate Definitionはsource identityとreview contractを識別する不変の記録である。Candidate IDはEvidence Ledgerを結び付けるtask-localな識別子であり、hash algorithmを暗黙に表さない。作成側は作成recipeと必要なauthorityを、reviewer向けにはGit index、object database、worktreeを変更しないread-only verification recipeを別々に記録する。reviewerはID文字列ではなくread-only verification recipeを再実行してsource identityとreview contractを確認する。
- Evidence Ledgerは同じCandidateへ追加する可変の完了証拠である。check、review、coverage status、構造収束gate、gap、hardening candidate、residual riskの追加または更新だけではCandidate IDを変更しない。失敗したcheckは完了をblockするが、Candidate Definitionを変更しない。
- Candidate作成時に、replacement objectとpromisor remoteからのlazy fetchを無効にしたGit processでbase revision expressionを一つのquoted argumentとして`git --no-replace-objects --no-lazy-fetch rev-parse --verify "<base-ref-label>^{commit}"`へ渡し、commit OIDへ一度だけ解決する。そのcommitから`git --no-replace-objects --no-lazy-fetch rev-parse "<resolved-base-commit-oid>^{tree}"`でtree OIDを得て両方を記録する。各commandのexit code、出力が単一OIDであること、同じprocess条件の`git cat-file -t`で期待object typeであることを確認し、失敗またはmissing objectではfetchせずCandidateをreview-readyにしない。PowerShellとPOSIX shellのどちらでも、peel suffixを含むrevision expression全体を一つのargumentとしてquoteする。base ref labelは由来を説明する情報であり、Candidate作成後の再解決結果をsource identity、再現、失効判定へ使わない。ref labelが移動しても、記録済みOIDが変わらない限りCandidateは変化しない。
- 標準のsource identity modeは`manifest-digest`とする。Git metadataへのwrite authorityを要求せず、記録済みbase OID、read-onlyなGit query、worktreeのreadだけで作成と再検証を完結させる。すべてのGit processでreplacement objectとlazy fetchを無効にし、`git status`を使う場合はさらに`--no-optional-locks`を指定してindex refreshを含むoptional writeを無効化する。changed / untracked pathをNUL区切りなど曖昧でない形式で安定sortし、各recordへpath、追加・変更・削除、Git mode、object type、regular fileのexact byte digest、symlink target bytesのdigest、submodule OID、削除markerを該当分だけ含める。全体digestにはalgorithm、record framing、path encoding、入力byte列、filter適用の有無、改行を含む正規化規則を明記する。raw diffでは記録済みbase commit OIDを使い、external diffとtext conversionを無効にしたbinary/full-index形式のcommandと、stdoutのexact bytesに対するalgorithm付きdigestを記録する。untracked contentはraw diffへ含まれない場合もmanifestのexact content identityへ固定し、Review Briefでは検証済みpathの内容を別途review対象に含める。mode-only変更とuntracked contentをpath名だけで識別してはならない。
- `creator-tree` modeは、Candidate作成側に一時indexとGit object databaseへのwrite authorityが既にある場合だけ選べる。作成recipeの開始からpostcondition確認まで、一時indexの構築、Candidate tree生成、manifestとraw diffの生成を含むすべてのGit commandへ`--no-replace-objects --no-lazy-fetch`を指定する。通常indexの作成前とcleanup後にtree OIDとstatusを確認するGit commandには、同じ条件に加えて`--no-optional-locks`も指定する。作成側は最初にその条件で通常indexのtree OIDとstatusを記録し、task-localで一意な一時indexへ`GIT_INDEX_FILE`を限定して、記録済みbase tree OIDから対象source stateを構築し、Candidate treeを生成する。Candidate Definitionへtree OIDを必ず記録し、manifestとraw diffは記録済みbase commit OIDとそのtree OIDから生成し、raw diffのstdout exact bytesに対するalgorithm付きdigestを記録する。必要なobjectがローカルに存在しない場合はfetchせず、Candidateをreview-readyにしない。操作後は環境変数を解除して一時indexを削除し、同変数を継承しないfresh processで、同じGit安全条件の下、通常indexのtree OIDとstatusが作成前と一致することを確認する。必要なauthorityまたはpreflight条件を最初のwrite-capable commandの試行前に満たせない場合だけ、`creator-tree`を開始せず`manifest-digest`へ切り替えられる。最初のwrite-capable commandを試行した後は、途中失敗、一時indexのcleanup失敗、またはnormal-index postconditionの不一致・確認不能があればCandidateを発行せず停止し、validation gapまたは安全境界の失敗として報告する。write開始後に`manifest-digest`へ切り替えたり、生成途中のobjectを再利用したりしない。
- reviewerはsource identity modeにかかわらず`read-tree`、`write-tree`、`hash-object -w`、`update-index`その他Git index、object database、worktreeへ書き込むcommandを実行しない。検証processの全Git queryでは`--no-replace-objects`と`--no-lazy-fetch`を使い、statusなどoptional writeがあり得るcommandでは`--no-optional-locks`も使う。記録済みcommitからreplacement objectなしで得たtree OIDが記録済みbase tree OIDと一致することを確認する。`manifest-digest`では宣言済みmanifest recipeをread-onlyで再計算し、記録済みbase commit OIDと検証済みworktreeから宣言済みraw diff commandを再実行する。`creator-tree`では作成側が記録した既存tree OIDの存在とtypeを確認し、記録済みbase commit OIDとtree OIDからmanifestとraw diffを再生成する。どちらのmodeでも再生成したraw diffのstdout exact bytesを記録済みalgorithmでdigestし、Candidate Definitionの値と一致した場合だけ、その再生成bytesとmanifestで固定したuntracked contentをsubstantive reviewへ使う。Review Briefに別のraw diff artifactが含まれる場合はそのexact-byte digestも記録値と一致させ、一致しないartifactをreview対象にしない。必要なobjectがローカルに存在しない、読めない、またはmanifest、raw diff、その他identity fieldが一致しない場合は、reviewerがfetchまたは再作成せずCandidate mismatchまたはvalidation gapとして停止する。
- Candidateのread-only検証結果は`verified`、`mismatch`、`validation-gap`のいずれかとする。宣言済みrecipeを完了して全fieldが一致した場合だけ`verified`、recipeを完了して不一致を確認した場合は`mismatch`、必須field、object、query、sandbox capabilityの不足により一致・不一致を判定できない場合は`validation-gap`とする。`verified`の場合だけsubstantive reviewへ進み、reviewed cellとreview evidenceを生成できる。`mismatch`または`validation-gap`ではsubstantive reviewを開始せず、validation-only outputとしてOverall judgmentを`not assessed — mismatch`または`not assessed — validation-gap`、Blocking finding statusを`not assessed`、review scopeを`Candidate verification only`、reviewed cellを`none`とし、検証evidenceとvalidation gapだけを返す。rootはその結果を現行Candidateのcheck / review entryへ記録せず、Evidence Ledgerのvalidation gapとして扱う。この検証結果はreviewerのimmutableな出力であり、Candidate Definitionのfield、Candidateの失効判定、Evidence Ledger entryのstatusとして扱わない。
- root sessionはreviewer起動前に、Candidate Definitionの必須field、identity mode、digest framing、path encoding、object type、宣言済みread-only verification recipe、draft Review Briefの必須fieldを決定的なローカルcheckで検証する。この結果を`Candidate preflight`と呼び、`verified`、`mismatch`、`validation-gap`のいずれかでtask-localに記録する。全項目が一致した`verified`だけをReview Briefへ記録してreviewerを起動し、`mismatch`または`validation-gap`ではReview Briefを発行せずreviewを開始しない。
- `Candidate preflight`はroot sessionのreview開始条件であり、Candidate Definition、Evidence Ledger entry、reviewerの`Candidate verification result`のいずれでもない。reviewerは`Candidate preflight=verified`を受け取った後も宣言済みread-only verification recipeを独立に実行し、前項の`Candidate verification result`を返す。rootの事前検証を理由にreviewerの検証を省略しない。
- 通常のGit indexをCandidate作成のためだけに変更しない。既存indexを使えるのは、ユーザーがcommit用stageを明示的に許可し、staged scopeがCandidate Definitionの対象と一致すると確認できた場合に限る。
- Evidence entryはtask-localに一意なEntry ID、実行または作成されたCandidate ID、kind、resultを不変の出自として持つ。既存entryのCandidate IDを書き換えたり、新Candidateへ移動または再関連付けしたりしない。Ledger statusを更新する場合も、entryの出自は変えない。`definition-delta non-impact confirmation`は、元entryのEntry IDとCandidate IDに加え、reviewed definition deltaとnon-impact rationaleもentry固有の不変fieldとして持つ。
- Evidence Ledgerのcheckとreview entryは`current`、`superseded`、`unconfirmed`のいずれかとする。最終Candidateの正しさを示す完了根拠には、現行Candidateへ紐付く`current`のentryだけを使う。
- holistic discovery entryは実行したCandidateに紐づくimmutableなreview resultであり、同じ論理変更で発見フェーズを一度実施したことをReview-cycle stateへ記録する。source変更後もholistic review countをリセットせず、旧entryを新Candidateへ再関連付けたり`current`へ戻したりしない。Review-cycle stateは発見フェーズの実施記録であり、最終Candidate全体の正しさを示すcompletion evidenceではない。
- holistic findingの`current-scope repair`で新Candidateを発行した場合は、現行Candidateのdirect check、finding family / resulting deltaのtargeted closure、影響を受けるspecialist cellの新規reviewまたはdelta非影響確認をFinal Candidate closure chainへ記録する。このchainと未解決`blocking`がないことを最終Candidateの完了根拠とし、二度目のholistic complete-diff reviewを要求しない。
- targeted closureは新Candidateに対する対象familyとresulting deltaのclosureであり、complete-diff reviewを見た証拠にしない。
- Candidate DefinitionとEvidence Ledgerはtask-localに保持し、現行仕様として恒久設計文書へ複製しない。

### Candidate Transition

Candidateの変更要否はsource identity、review contract、Ledger-only changeの順で判定する。source identityとreview contractが同時に変わった場合はsource identity変更として扱う。

| Observed change | Candidate | Existing evidence | Evidence required for completion |
| --- | --- | --- | --- |
| check、review、coverage status、構造収束gate、gap、hardening candidate、residual riskだけを追加または更新 | 同じCandidateを維持する | entryの出自とstatusを自動変更しない。失敗したcheckは完了をblockする | 現行Candidateの既存`current` entryと新しいLedger entry |
| source identityは不変で、accepted anchorまたはその意味、supported scope、Invariant定義、matrix cell定義、lens scope、review contract revision / recipeのいずれかが変更 | 新Candidateを発行する | 定義差分の影響を受ける旧check / review entryは元Candidateに保持したまま`unconfirmed`とし、新Candidateの対応Matrix cellは`unresolved`とする。旧entryを新Candidateの完了証拠へ移動または再関連付けしない | Review Brief発行前に、影響するcheckの新規実行または定義差分の非影響確認によって対応cellを`covered`、`anchored-exception`、`residual-risk`のいずれかへ更新する。完了には必要な新規review entryも揃える |
| source content、file mode、記録済みbase OID、identity mode / value、manifest、作成recipe、read-only verification recipe、raw diff command / digest recipe / digest valueのいずれかが変更 | 新Candidateを発行する | review contractも同時に変わった場合を含め、旧Candidateの全reviewとsource依存checkを`superseded`とし、`unconfirmed`への移行や新Candidateへの再関連付けをしない | 新Candidate上で新しく実行または確認したevidence |

- Candidateを再作成するとき、同じbase ref labelが旧Candidateと異なるOIDへ解決された場合はsource identity変更である。既存Candidateのref labelを再解決した結果だけでは、そのCandidateを失効させない。
- holistic review対象はexact source stateとcomplete raw diffだけでなく、accepted anchor、そのanchorが定める契約の意味、Invariant、supported scopeを含む。これらの変更はreview contract変更として判定する。
- review-contract-only変更の影響を受けないevidenceも自動継承しない。新Candidate上で定義差分が担当cellへ影響しないことを確認した場合だけ、元entryと元Candidate、reviewed definition delta、non-impact rationaleを持つ独立した`definition-delta non-impact confirmation` entryを`current`にでき、そのentryを根拠に対応cellを正規の`Cell status`へ更新する。影響がある場合は新Candidate上でcheckを実行してReview Brief発行前に`unresolved`を閉じ、必要なreviewを新しい実行entryとして記録する。
- source identity変更後に他のtrigger済みlensが担当cellへのdelta非影響を確認する場合、その確認は新Candidateを対象に新しく得たreview evidenceであり、旧Candidateのevidenceの再関連付けではない。

## Review Brief

reviewerへ渡す入力一式を`Review Brief`と呼ぶ。Session Handoffと区別し、active policyではこの名称へ統一する。

```text
Review Brief:
Logical change ID:
Review kind: targeted review | specialist | targeted closure | holistic complete-diff
Candidate ID / Candidate Definition: <Candidate-bound reviewでは必須>
Candidate preflight result / evidence: verified / <実行したrecipeと結果>
Evidence Ledger: <review kindで必要な現行entry、またはnot requiredと理由>
Review Entry ID: <割当済みIDまたはunassigned>
Goal / accepted contract / canonical anchors:
Included scope / excluded scope:
Assigned lens / matrix cells: <specialistの場合>
Finding family / resulting delta: <targeted closureの場合>
Raw diff / verified untracked content: <review kindで必要な範囲>
Executed checks:
Deadline: <ISO 8601の絶対時刻、UTC offset付き>
Retry: none | <toolまたはtransport failureと維持したCandidate / review contract>
```

- Review Briefの発行前に`Candidate preflight=verified`を要求する。Candidateを使わないreviewではCandidate preflight欄を省略できるが、review scopeと入力artifactのローカル検証を完了する。
- Logical change IDは一つのaccepted contractとreview cycleを識別し、Candidate IDと区別する。source repairでCandidateを更新しても同じ論理変更なら維持し、`boundary prerequisite`またはユーザー確認後の別のaccepted contractへ分けた場合だけ新しいIDを使う。
- deadline、Review Entry ID、transport指定、同じ内容のartifact配置などReview Briefのenvelopeだけを変更してもCandidateを変更しない。accepted anchor、その意味、supported scope、Invariant定義、matrix cell定義、lens scope、review contract revision / recipeを変更した場合はreview contract変更として新Candidateを発行する。source identityの変更はCandidate Transitionに従う。
- deadlineは有限の絶対時刻としてreviewer起動前に固定する。deadline未指定または起動時点で期限切れのReview Briefを発行しない。
- targeted reviewでは、完了したslice、観測可能な契約、適用可能なexecutable contractまたは理由付き代替確認、targeted check、含めるcontract surfaceを渡す。通常sliceは`slice_reviewer`、高リスクtriggerまたは本Skillが要求するIndependent Closure Reviewは`targeted_reviewer`へ割り当てる。
- specialist reviewでは、現行Evidence Ledger、割り当てたlens、対象matrix cell、Closure Mapを渡し、同じlensの一般的な再探索へ広げない。
- targeted closureでは、rootがFinding Promotionを適用したfinding family、accepted contractとの関係、修正delta、direct check、含める兄弟経路、除外scopeを渡す。reviewerは指定familyとresulting deltaだけを確認し、complete diffを新規探索しない。
- holistic complete-diff reviewでは、complete raw diff、検証済みuntracked content、accepted contract、canonical anchors、現行Candidateの実行済みcheckを渡す。過去finding、specialist reviewの結論、claimed resolution、実装者の結論、既存Closure Mapを渡さず、reviewerが不変条件と反例を再構築する。
- deadlineを超えたreviewerはroot sessionが一度interruptし、同じreviewを別reviewerへ自動再投入しない。取得済み出力は採用可能なevidenceと未完了のvalidation gapへ分ける。完了条件を満たさない場合はreview回数を増やさずユーザー判断へ戻る。
- reviewを再試行できるのは、toolまたはtransport failureによりreview evidenceを取得できず、同じCandidateとreview contractを維持できる場合だけとする。finding数、deadline超過、待機時間、または「念のため」を理由に再試行しない。再試行時はReview Briefの`Retry`へfailureと維持した境界を記録する。

## Review Lens Selection

Invariant Matrixからtriggerされた1から3個のlensを同じCandidate Definitionへ適用する。複数の独立したlensがtriggerされた場合は1 lensにつき1 reviewerで並列化し、同じlensへreviewerを重ねない。一つのlensだけなら一人のreviewerへ渡す。

- `contract-schema-projection`: public schema、required / optional、default、runtime validation、generated / raw consumer、success / error projection
- `lifecycle-effect-concurrency`: state transition、effect certainty、correlation owner、retry、delayed event、timeout、disconnect、crash
- `identity-security-ipc`: identity、authority confirmation、authorization、secret-bearing message、IPC peer / endpoint
- `resource-cleanup-platform`: aggregate limit、queue、cleanup owner、process lifetime、storage、platform parity

変更規模やfile数だけでlensを追加しない。一つのlensで閉じる変更へ複数reviewerを要求せず、triggerされたlensが4つある場合も相互依存の強い軸を一つのcomposite lensとして命名し、担当cellと未確認cellを明示して最大3名にする。specialist review後の修正とholistic reviewへの合流順序は`AGENTS.md`のTask Workflowを正本とし、このSkillで条件分岐を再定義しない。

## Finding Promotion

review findingやbugを受けたら、root sessionの最終分類とSibling Sweepの前に比例性を判定する。reviewerの分類提案だけでsourceを広げず、指摘されたcall pathだけを直すことも、理論上の兄弟caseを無条件に現在の論理変更へ取り込むこともしない。

### Proportionality Gate

root sessionは、sourceを広げる前に次をtask-localに固定する。

1. findingが違反するaccepted contractとsupported scope
2. 通常操作または明示された前提からの到達経路と、実発生・再現・外部仕様の根拠
3. 影響、既存の検知・復旧、局所boundaryで閉じられる可能性
4. risk acceptanceできずsource repairが必要な場合だけ、promotion先が同じsemantic owner / subsystemか、新しいowner / subsystemか
5. 現在のaccepted contractを閉じるための修正か、明示した条件で将来再調査するhardeningか

accepted contractとの関係または現実的な到達性が未確定なら`investigation-pending`として最終分類を保留し、sourceを広げる前に必要な証拠を追加調査する。証拠が揃った後、source展開の扱いを次のpromotion dispositionへ分ける。このdispositionは`AGENTS.md`の`blocking`、`risk-candidate`、`non-material`、`invalid`とは別軸であり、dispositionを先に、root sessionの最終分類を後に確定する。`accepted risk`をsource repairのowner判定より先に評価し、修正が必要なfindingだけを`current-scope repair`または`boundary prerequisite`へ分ける。

- `accepted risk`: 現在のaccepted contract違反がsupported scopeで現実的に到達するが、`AGENTS.md`の`risk-candidate`条件をすべて満たし、source repairを行わず完了できる。semantic ownerをまたぐ可能性があっても現在のsource、test、Candidate Definition、review contractを広げず、最終分類は`risk-candidate`とする。将来source repairへ進む場合は、その時点でFinding Promotionを再適用する。
- `current-scope repair`: 現在のaccepted contract違反がsupported scopeで現実的に到達し、risk acceptanceできず、必要なsource repairが同じsemantic ownerに属する。同じowner内の別責務境界であることだけではprerequisiteへ分けず、supported scopeに属する兄弟経路を現在の論理変更で扱う。最終分類は`blocking`とし、Sibling Sweepと修正へ進む。
- `boundary prerequisite`: 現在のaccepted contract違反がsupported scopeで現実的に到達し、risk acceptanceできず、修正に新しいsemantic ownerまたは別subsystemの契約変更を要する。現在のfeatureへ抱き合わせず、独立したaccepted contract、source、executable contract、reviewを持つ先行論理変更へ分ける。依存するfeatureの完了条件は先行変更が閉じるまで満たさず、最終分類は`blocking`とする。
- `hardening follow-up`: 必要な証拠調査後、現在のaccepted contract違反ではない、またはsupported scopeで現実的に到達しないと確認したうえで、契約との具体的な関係、反証可能な仮説、再調査を開始する条件の三つをすべて満たす。現在のsource、test、Candidate Definition、review contractを広げず、current reviewでは`non-material`としてfollow-up候補へ分離する。単なる到達証拠不足はこのdispositionにせず、`investigation-pending`とする。
- `dismissed`: 必要な証拠調査を終えても、`hardening follow-up`の三要件を一つ以上満たさない。実装対象にせず、最終分類は`invalid`とする。追加調査で不足要件を確定できる間だけ`investigation-pending`に残す。

別owner / subsystemでも、各logical changeが自身のsourceとexecutable contractを閉じた後でなお、どの適用・deploy順序でもaccepted contractへ違反し、独立して有効な中間境界状態を作れず、かつ現在のaccepted contractが横断変更を明示的に要求する場合だけ、同じ論理変更へ残せる。その場合は、分割不能なatomicityの根拠と含める責務を記録する。通常のtest-before-code、sourceとtestの編集順、Candidate失効、review再実行、commitやPR作成の手間、同じbranchに既に変更があることは、抱き合わせの根拠にしない。

auth bypass、secretまたはpersonal dataの露出、現実的なinjection、不可逆なdata lossは、supported scopeで現実的に到達するなら現在の完了をblockする。影響が大きいことだけで到達根拠を省略せず、不明ならsourceを広げる前に追加調査して分類する。

### Sibling Sweep

`current-scope repair`だけを、次の順で同じ不変条件familyへ展開する。

1. 観測されたfailureを一文で固定する。
2. failureを許した不変条件の欠落を一文で表す。
3. 同じ入力源、operation family、owner、state transition、resource scopeを横断検索する。
4. 同型failureを起こす反例を追加し、まとめて修正する。
5. targeted regression testと、可能なら共有境界のtype / schema / validation / static checkを更新する。
6. 過去findingと同じfamilyなら、局所再発ではなくworkflow gapとして報告する。

Findingへのreply、thread resolve、対象testの追加だけをSibling Sweepの代わりにしない。`boundary prerequisite`または`hardening follow-up`を、Sibling Sweepの名目で現在の論理変更へ戻さない。

## Finding Classification and Review Convergence

finding分類、risk acceptance、review回数、完了条件は`AGENTS.md`の「Validation and Review Completion Gates」を正本とする。このSkillは、changed invariant、到達可能な反例、兄弟経路、executable contract、未確認cellをevidenceとして返し、分類を提案するところまでを担当する。

targeted review、specialist finding対応、targeted closure、holistic complete-diff reviewの開始条件と合流順序は`AGENTS.md`に従う。holistic complete-diff reviewは一つの論理変更につき一度だけとし、そのfinding修正後はcomplete diffを新規探索しない。

## Independent Closure Review

契約が複数入口・複数subsystemへ波及する、複合不変条件を変更する、または失敗がpublic contract、永続化、migration、外部副作用、認可、owner / scope、並行処理、resource limitへ重大な影響を与える場合は、実装とtargeted checkの後、完了前に実装者から独立したreviewを行う。

- researcherは根拠収集、validatorは機械的確認、reviewerは反例探索を担当する。researchやgreen testをreviewの代用にしない。
- reviewerを起動する前に、root sessionがCandidate preflightとReview Briefのローカル検証を完了する。reviewerへはreview kindに対応するReview Briefだけを渡し、実装者の結論を確定事実として渡さない。
- targeted、specialist、またはtargeted closureのIndependent Closure Reviewでは、Review BriefにCandidate Definition、必要な現行Evidence Ledger、rootがtask-localに割り当てたReview Entry IDまたは未割当である事実、goal、accepted contract、canonical anchors、実行済みcheck、review kind固有のscopeを含める。
- specialist reviewerは割り当てられたlensとmatrix cellへ集中し、確認したcell、未確認cell、finding、hardening候補、validation gapを分けて返す。rootは複数lensのfindingを不変条件familyへ統合する。
- specialist finding対応後の再検証とreview合流順序は`AGENTS.md`に従い、Candidateとevidenceの変更はこのSkillのCandidate Transitionに従って記録する。
- holistic complete-diff reviewでは、利用可能なら`fork_turns="none"`を使い、Review BriefにCandidate Definition、rootがtask-localに割り当てたReview Entry IDまたは未割当である事実、現行Candidateに対する実行済みcheck、goalとaccepted contract、更新後raw diff、canonical anchorsだけを含める。過去finding、specialist reviewの結論、claimed resolution、実装者の結論、既存Closure Mapを渡さず、reviewerが不変条件と反例を再構築する。
- holistic reviewの`current-scope repair`は、direct checkとfinding family / resulting deltaに限定したtargeted closureで閉じる。targeted closure reviewerはcomplete diffを新規探索しない。同じ`blocking` familyが閉じない場合はreviewを反復せず、要求、設計、責務境界、accepted contract、またはユーザー判断へ戻る。
- targeted closure中にauth bypass、secretまたはpersonal dataの露出、現実的なinjection、不可逆なdata lossを偶発的に確認した場合は、Review Briefのscope外でも報告する。rootがFinding Promotionを適用する前にsource scopeを自動拡張しない。
- reviewerは割り当て済みのreview Entry IDがあればその値をechoし、未割当なら`unassigned`と返して自分で生成しない。reviewerはimmutableなreview resultだけを返し、Evidence Ledger statusを選択または更新しない。rootがresultを受け取った後にentryとstatusをLedgerへ記録する。
- reviewerはfinding-firstで、反例、同じ契約を持つ兄弟経路、failure timing、owner / scope、欠けたexecutable contractを根拠付きで返し、各findingの分類を提案する。
- rootはfindingへFinding Promotionを適用し、source、accepted contract、executable contract、supported scopeと照合して最終分類する。`current-scope repair`だけを同じ不変条件familyへ展開して修正・再検証し、`boundary prerequisite`は独立した先行論理変更へ戻す。
- reviewerを利用できない場合は、実装時の推論を引き継がないfresh-context second passを行い、独立review未実施を残リスクとして報告する。

pure refactorや局所的な機械変更へ独立reviewを義務化しない。変更規模ではなく、契約の非局所性と失敗時の影響で判定する。

## Knowledge Placement

- 現在の挙動と構造はsourceへ置く。
- 期待動作、不変条件、validation、regression expectationはtest / type / schema / static checkへ置く。
- 一箇所の近くで必要な理由はcode commentへ置く。
- 後戻り困難な選択理由はADRへ置く。
- プロジェクト固有の契約や生のreview commentをMemoryだけへ置かない。
- Memoryには、将来も有用な非ファイル文脈、確定した判断、正本へのpointerだけを置く。raw finding、log、diff、未確認の一般化は保存しない。
- 複数projectで繰り返す一般的な観点は、このSkillの改善候補として報告する。repository作業中に無断でglobal Skillを変更しない。

## Completion Gate

- 同じ不変条件を持つ兄弟入口と兄弟operationを確認した。
- 複合不変条件をfieldごとの妥当性だけで済ませず、許可・不許可の組合せとatomic update単位を確認した。
- 正常系だけでなく、主要なsequenceとfailure timingを確認した。
- per-item制約をaggregate / concurrent / process scopeと混同していない。
- owner変更がread、write、auth、projection、audit、cleanupへ必要な範囲で伝播した。
- public responseとerrorは内部型の流用ではなく、許可した情報だけを投影した。
- 既存データや旧schemaを扱う場合、populated stateと途中失敗を確認した。
- findingから得た一般則を、対象箇所以外へ適用した結果を報告できる。
- 非局所的または高リスクな変更ではIndependent Closure Reviewを実施した。未実施なら理由と代替確認を報告した。
- 未解決の`blocking` findingがなく、その他のfindingを根拠付きで分類した。
- accepted riskがある場合は、発生条件、影響、検知、復旧、follow-upの要否を報告した。
- full-diff reviewが一つの論理変更につき0回または1回であることを報告した。
- Candidate preflight、Review Briefのdeadline、deadline超過、review再試行の有無と理由を区別して報告した。
- frozen Candidateを使った場合、Candidate DefinitionとEvidence Ledgerを分け、reviewとcheckのEntry ID、実行Candidate、確認entryのoriginを区別し、変更後のCandidateへ元entryを移動または再関連付けしていない。
- holistic findingでCandidateが変わった場合、旧Candidateのholistic discovery entryをreview-cycle recordとして保持し、最終Candidateのcurrent direct check、targeted closure、影響するspecialist cellをFinal Candidate closure chainへ揃えた。旧holistic entryを最終Candidateのcompletion evidenceとして扱っていない。
- specialist reviewを使った場合、triggerされたlens、review済みcell、未確認cell、hardening候補を区別し、必要なtargeted closure後に`Full-review gate=run`の場合だけholistic complete-diff reviewを一度実施した。

pure refactorや局所的な機械変更では、無関係なclosure軸を儀式的に展開しない。
