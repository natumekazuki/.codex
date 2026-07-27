---
name: contract-closure
description: 境界、public API、永続化、migration、外部副作用、認可、並行処理、resource limit、owner / scope変更を実装・修正・reviewするとき、変更した不変条件と複合値の組を兄弟入口、状態遷移、failure timing、aggregate scope、public projection、executable contractまで展開し、独立した反証reviewで閉じる。review findingやbug fixを局所修正で終わらせず、同じ不変条件familyの再発を防ぐときに使う。
---

# Contract Closure

変更行ではなく、変更した不変条件の到達範囲を確認する。green testや指摘箇所の修正だけで完了扱いにしない。

## Workflow

1. 変更またはfindingを、観測されたcaseと、その背後の不変条件へ分ける。
2. 関連するsource、test、type、schema、static check、accepted ADRを読み、accepted contractの根拠、supported scope、観測可能なfailure、canonical owner、兄弟入口、executable anchorを固定する。
3. capability、operation、owner、状態、resource scopeが同じ兄弟経路を検索する。
4. 単独では妥当でも組合せで不正になるfield、version、generation、owner / scopeを一つの複合不変条件として列挙する。
5. 該当triggerの展開軸を `references/trigger-matrices.md` から選ぶ。複数該当する場合は必要な節を組み合わせる。
6. task-localなClosure MapとInvariant Matrixを作り、反例を先に列挙する。
7. 各不変条件を最も強い実行可能な場所へ置く。type / schema / shared validation / static checkで強制できる契約をtestだけへ退避しない。
8. 実装または修正後、targeted checkに加えてSibling Sweepを行う。
9. 非局所的または高リスクな変更にはCandidate Definitionを凍結し、Evidence Ledgerへcheckとreviewを記録しながら、triggerされたreview lensでIndependent Closure Reviewを行う。
10. 未確認cell、意図的な例外、実行不能なcheckを残リスクとして報告する。

## Accepted Contract Gate

実装前に、契約の根拠と適用範囲を確定する。

- 根拠は、明示されたユーザー要求、public protocol / schema、accepted ADR、外部consumer、または根拠を確認できる既存のexecutable contractに置く。
- external schemaやprotocolへ依存する場合は、version、revision、checksum、JSON pointerなど、requiredness、default、enum、failure semanticsを再確認できるexact anchorを残す。
- 現在のsourceやtestが存在することだけをaccepted contractにしない。
- 根拠が競合し、required / optional、default、failure semantics、supported scopeなどの結論が変わる場合は、reviewerに選択させず、consumer影響と選択肢を確認して`unresolved`のまま停止する。

## Closure Map

会話またはtask-local noteへ、必要な項目だけ短く作る。恒久文書を既定にしない。

```text
Accepted contract / exact anchor:
Supported scope:
Invariant:
Coupled invariants / valid combinations:
Trigger:
Canonical anchors:
Sibling channels:
State / operation sequences:
Failure points:
Owner / scope / projections:
Resource scopes:
Counterexamples:
Executable contracts:
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

| Sibling channel | Coupled values | State / evidence order | Failure timing | Owner / effect certainty | Public projection | Executable anchor | Cell status |
```

`Cell status`は次のいずれかにする。

- `covered`: sourceとexecutable contractまたは理由付きの直接確認で閉じた
- `anchored-exception`: accepted contractの根拠を持つ意図的な例外
- `residual-risk`: 発生条件、影響、検知、復旧、follow-up要否を分類した
- `unresolved`: 契約または反例の確認が不足し、Candidateをreviewへ渡せない

観測されたcaseを閉じただけで同じInvariant IDの兄弟cellを未確認にしない。無関係なoperation、platform、既存負債へ無制限に広げず、同じcapability、owner、state、resource scope、public projectionを共有する範囲へ限定する。

## Candidate Definition and Evidence Ledger

high-risk / non-localな変更でIndependent Closure Reviewを行う場合は、source、適用可能なexecutable contract、targeted check、該当する構造収束gateが揃ったexact source stateをtask-localに凍結する。

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
Accepted contract anchors:
Accepted contract meaning:
Supported contract scope:
Review contract revision / recipe:
Invariant IDs / definitions / matrix cell definitions:
Triggered lens scope:

Evidence Ledger:
Candidate ID:
Evidence entries:
  Entry ID / kind / executed-on Candidate ID / origin entry ID and Candidate ID (confirmation only) / result / reviewed definition delta (confirmation only) / non-impact rationale (confirmation only) / evidence status:
Structural convergence gate / result:
Review entries:
  Entry ID / review kind / executed-on Candidate ID / origin entry ID and Candidate ID (confirmation only) / result / reviewed definition delta (confirmation only) / non-impact rationale (confirmation only) / lens / reviewed and unreviewed cells / evidence status:
Coverage status:
Validation gaps / hardening candidates / residual risks:
```

- Candidate Definitionはsource identityとreview contractを識別する不変の記録である。Candidate IDはEvidence Ledgerを結び付けるtask-localな識別子であり、hash algorithmを暗黙に表さない。作成側は作成recipeと必要なauthorityを、reviewer向けにはGit index、object database、worktreeを変更しないread-only verification recipeを別々に記録する。reviewerはID文字列ではなくread-only verification recipeを再実行してsource identityとreview contractを確認する。
- Evidence Ledgerは同じCandidateへ追加する可変の完了証拠である。check、review、coverage status、構造収束gate、gap、hardening candidate、residual riskの追加または更新だけではCandidate IDを変更しない。失敗したcheckは完了をblockするが、Candidate Definitionを変更しない。
- Candidate作成時にbase revision expressionを一つのquoted argumentとして`git rev-parse --verify "<base-ref-label>^{commit}"`へ渡し、commit OIDへ一度だけ解決する。そのcommitから`git rev-parse "<resolved-base-commit-oid>^{tree}"`でtree OIDを得て両方を記録する。各commandのexit code、出力が単一OIDであること、`git cat-file -t`で期待object typeであることを確認し、失敗時はCandidateをreview-readyにしない。PowerShellでは`git rev-parse --verify "$baseRefLabel^{commit}"`、POSIX shellでは`git rev-parse --verify "${base_ref_label}^{commit}"`のように、peel suffixを含むrevision expression全体をquoteする。base ref labelは由来を説明する情報であり、Candidate作成後の再解決結果をsource identity、再現、失効判定へ使わない。ref labelが移動しても、記録済みOIDが変わらない限りCandidateは変化しない。
- 標準のsource identity modeは`manifest-digest`とする。Git metadataへのwrite authorityを要求せず、記録済みbase OID、read-onlyなGit query、worktreeのreadだけで作成と再検証を完結させる。`git status`を使う場合は必ず`git --no-optional-locks status`とし、index refreshを含むoptional writeを無効化する。changed / untracked pathをNUL区切りなど曖昧でない形式で安定sortし、各recordへpath、追加・変更・削除、Git mode、object type、regular fileのexact byte digest、symlink target bytesのdigest、submodule OID、削除markerを該当分だけ含める。全体digestにはalgorithm、record framing、path encoding、入力byte列、filter適用の有無、改行を含む正規化規則を明記する。mode-only変更とuntracked contentをpath名だけで識別してはならない。
- `creator-tree` modeは、Candidate作成側に一時indexとGit object databaseへのwrite authorityが既にある場合だけ選べる。作成側は最初に通常indexのtree OIDと`git --no-optional-locks status`の結果を記録し、task-localで一意な一時indexへ`GIT_INDEX_FILE`を限定して、記録済みbase tree OIDから対象source stateを構築し、Candidate treeを生成する。Candidate Definitionへtree OIDを必ず記録し、manifestとraw diffは記録済みbase commit OIDとそのtree OIDから生成する。操作後は環境変数を解除して一時indexを削除し、同変数を継承しないfresh processで通常indexのtree OIDと`git --no-optional-locks status`の結果が作成前と一致することを確認する。write authority、cleanup、またはpostcondition確認のいずれかが満たせない場合は`creator-tree`を使わず、`manifest-digest`へ切り替える。
- reviewerはsource identity modeにかかわらず`read-tree`、`write-tree`、`hash-object -w`、`update-index`その他Git index、object database、worktreeへ書き込むcommandを実行しない。検証processのGit queryでは`git --no-optional-locks`または同等の`GIT_OPTIONAL_LOCKS=0`を使い、optional index refreshも禁止する。`manifest-digest`では宣言済みrecipeをread-onlyで再計算する。`creator-tree`では作成側が記録した既存tree OIDの存在とtypeを`cat-file`などで確認し、記録済みbase commit OIDとtree OIDからmanifestとraw diffを再生成する。tree objectが存在しない、読めない、またはidentityが一致しない場合は、reviewerが再作成せずCandidate mismatchまたはvalidation gapとして停止する。
- 通常のGit indexをCandidate作成のためだけに変更しない。既存indexを使えるのは、ユーザーがcommit用stageを明示的に許可し、staged scopeがCandidate Definitionの対象と一致すると確認できた場合に限る。
- Candidate失効はsource identityを先に判定する。source content、file mode、記録済みresolved base commit / tree OID、identity mode / value、manifest、作成recipe、read-only verification recipeのいずれかが変わった場合は新Candidateを発行する。Candidateを再作成するとき、同じbase ref labelが旧Candidateと異なるOIDへ解決された場合もsource identity変更である。既存Candidateのref labelを再解決した結果だけで、そのCandidateを失効させない。review contractも同時に変わった場合を含め、旧Candidateの全reviewとsource依存checkは必ず`superseded`として完了証拠から除外し、`unconfirmed`への移行や新Candidateへの再関連付けを認めない。
- Evidence entryはtask-localに一意なEntry ID、実行または作成されたCandidate ID、kind、resultを不変の出自として持つ。既存entryのCandidate IDを書き換えたり、新Candidateへ移動または再関連付けしたりしない。Ledger statusを更新する場合も、entryの出自は変えない。`definition-delta non-impact confirmation`は、元entryのEntry IDとCandidate IDに加え、reviewed definition deltaとnon-impact rationaleもentry固有の不変fieldとして持つ。
- source identityが変わらず、accepted anchorまたはその契約上の意味、supported contract scope、Invariant IDまたはその定義、matrix cell定義、lens scope、review contract revision / recipeのいずれかだけが変わった場合も新Candidateを発行する。旧entryは元Candidateに保持して新Candidateの完了証拠から除外し、影響するlens、check、holistic review対象の対応cellを新Candidate上で`unconfirmed`とする。holistic review対象はexact source stateとcomplete raw diffだけでなく、accepted anchor、そのanchorが定める契約の意味、Invariant、supported scopeを含む。
- review-contract-only変更の影響を受けないevidenceも自動継承しない。新Candidate上で定義差分が担当cellへ影響しないことを確認した場合は、元entryのEntry IDとCandidate ID、確認した定義差分、非影響の根拠を持つ独立した`definition-delta non-impact confirmation` entryを新CandidateのLedgerへ追加する。`current`にできるのはこの新しい確認entryであり、元entryは元Candidateの履歴として保持する。影響がある場合は新Candidate上でcheckまたはreviewを実行し、新しい実行entryを作る。
- source identity変更後に他のtrigger済みlensが担当cellへのdelta非影響を確認する場合、その確認は新Candidateを対象に新しく得たreview evidenceであり、旧Candidateのevidenceの再関連付けではない。
- Evidence Ledgerのreview entryは`current`、`superseded`、`unconfirmed`のいずれかとする。完了根拠には現行Candidateへ紐付く`current`のentryだけを使う。
- targeted re-reviewは新Candidateに対する対象familyとresulting deltaのclosureであり、complete-diff reviewを見た証拠にしない。
- Candidate DefinitionとEvidence Ledgerはtask-localに保持し、現行仕様として恒久設計文書へ複製しない。

## Review Lens Selection

Invariant Matrixからtriggerされた1から3個のlensを同じCandidate Definitionへ適用する。複数の独立したlensがtriggerされた場合は1 lensにつき1 reviewerで並列化し、同じlensへreviewerを重ねない。一つのlensだけなら一人のreviewerへ渡す。

- `contract-schema-projection`: public schema、required / optional、default、runtime validation、generated / raw consumer、success / error projection
- `lifecycle-effect-concurrency`: state transition、effect certainty、correlation owner、retry、delayed event、timeout、disconnect、crash
- `identity-security-ipc`: identity、authority confirmation、authorization、secret-bearing message、IPC peer / endpoint
- `resource-cleanup-platform`: aggregate limit、queue、cleanup owner、process lifetime、storage、platform parity

変更規模やfile数だけでlensを追加しない。一つのlensで閉じる変更へ複数reviewerを要求せず、triggerされたlensが4つある場合も相互依存の強い軸を一つのcomposite lensとして命名し、担当cellと未確認cellを明示して最大3名にする。specialist review後の修正とholistic reviewへの合流順序は`AGENTS.md`のTask Workflowを正本とし、このSkillで条件分岐を再定義しない。

## Finding Promotion

review findingやbugを受けたら、指摘されたcall pathだけを直さない。

1. 観測されたfailureを一文で固定する。
2. failureを許した不変条件の欠落を一文で表す。
3. 同じ入力源、operation family、owner、state transition、resource scopeを横断検索する。
4. 同型failureを起こす反例を追加し、まとめて修正する。
5. targeted regression testと、可能なら共有境界のtype / schema / validation / static checkを更新する。
6. 過去findingと同じfamilyなら、局所再発ではなくworkflow gapとして報告する。

Findingへのreply、thread resolve、対象testの追加だけをSibling Sweepの代わりにしない。

## Finding Classification and Review Convergence

finding分類、risk acceptance、review回数、完了条件は`AGENTS.md`の「Validation and Review Completion Gates」を正本とする。このSkillは、changed invariant、到達可能な反例、兄弟経路、executable contract、未確認cellをevidenceとして返し、分類を提案するところまでを担当する。

- sliceのtargeted reviewで見つかった`blocking`は、同じsliceのSibling Sweep、targeted check、targeted re-reviewで閉じる。
- fresh-context full-diff closure reviewは、統合後のcomplete-diff reviewで`blocking`へ対応した場合だけ適用する。未完成または未統合のtaskへ広げない。

## Independent Closure Review

契約が複数入口・複数subsystemへ波及する、複合不変条件を変更する、または失敗がpublic contract、永続化、migration、外部副作用、認可、owner / scope、並行処理、resource limitへ重大な影響を与える場合は、実装とtargeted checkの後、完了前に実装者から独立したreviewを行う。

- researcherは根拠収集、validatorは機械的確認、reviewerは反例探索を担当する。researchやgreen testをreviewの代用にしない。
- initial、specialist、またはtargetedなIndependent Closure Reviewでは、reviewerにreview kind、Candidate Definition、現行Evidence Ledger、割り当てたlens、goal、ユーザー要求または既存のaccepted contract、raw diff、canonical anchors、task-local Closure Map、対象matrix cell、実行済みcheckを渡す。実装者の結論を確定事実として渡さない。
- specialist reviewerは割り当てられたlensとmatrix cellへ集中し、確認したcell、未確認cell、finding、hardening候補、validation gapを分けて返す。rootは複数lensのfindingを不変条件familyへ統合する。
- specialist reviewの`blocking`を修正した場合はSibling Sweepとcheckを再実行する。新Candidate上でfindingを出したlensは対象familyとresulting deltaをtargeted re-reviewし、他のtrigger済みlensも担当cellへのdeltaの非影響を再確認する。全lensの証拠が同じ現行Candidateへ揃うまでholistic reviewへ進まず、その後の無条件合流は`AGENTS.md`に従う。
- holistic complete-diff reviewとblocking修正後のfresh-context full-diff closure reviewでは、利用可能なら`fork_turns="none"`を使い、Candidate Definition、現行Candidateに対する実行済みcheck、goalとaccepted contract、更新後raw diff、canonical anchorsだけを渡す。過去finding、specialist reviewの結論、claimed resolution、実装者の結論、既存Closure Mapを渡さず、reviewerが不変条件と反例を再構築する。
- reviewerはfinding-firstで、反例、同じ契約を持つ兄弟経路、failure timing、owner / scope、欠けたexecutable contractを根拠付きで返し、各findingの分類を提案する。
- rootはfindingをsourceとexecutable contractへ照合して分類を確定し、採用した`blocking` findingを同じ不変条件familyへ展開してから修正・再検証する。
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
- full-diff reviewの回数と、追加reviewを行った場合のtriggerとscopeを報告した。
- frozen Candidateを使った場合、Candidate DefinitionとEvidence Ledgerを分け、reviewとcheckのEntry ID、実行Candidate、確認entryのoriginを区別し、変更後のCandidateへ元entryを移動または再関連付けしていない。
- specialist reviewを使った場合、triggerされたlens、review済みcell、未確認cell、hardening候補を区別し、必要なtargeted closure後にholistic complete-diff reviewを実施した。

pure refactorや局所的な機械変更では、無関係なclosure軸を儀式的に展開しない。
