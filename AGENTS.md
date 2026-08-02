# Codex Working Agreements

## 1. Outcome, Scope, and Authority

- 最初に要求、制約、期待される最終状態、完了条件を短く整理し、関連する source と executable contract を読んでから判断する
- answer、explain、review、diagnose、plan の依頼では、必要な調査と報告まで行い、変更依頼がない限り実装しない
- change、build、fix の依頼では、依頼範囲の local 変更と非破壊的な検証を進める。通常の読み取り、検索、編集、test に追加確認は要らない
- external write、破壊的操作、購入、履歴改変、push、または依頼範囲の実質的な拡張には明示確認を求める。ただし、会話内でユーザーが明示した内容を「WithMate Memory」の保存候補、除外条件、authority境界に従ってappendする場合は、同節に定める範囲で追加確認を不要とする
- ユーザーの未コミット変更を保護し、巻き戻し、上書き、stage、clean、無関係な変更の混入をしない
- 差分量より、根本原因、既存の責務境界、整合した最終状態を優先する。仕様、API、依存関係、不明な事実を捏造しない
- 暫定対応を採る場合は、理由、残るリスク、恒久対応へ進む条件を追跡可能に残す

## 2. Source of Truth and Knowledge Placement

この節は、設計や文書作成を明示された場合だけでなく、すべての change、build、fix、review に適用する。情報配置は任意の文書整理ではなく、実装と検証の完了条件である。

### 2.1 Sources of Truth

- 現在の実装と構造は source code を正本とする。source は現在状態を示すが、期待どおりであることまでは保証しない
- 観測可能な期待動作、不変条件、機械検証可能な契約は test / type / schema / static check を正本とする
- 一つの code location の近くで理解できる局所的な理由や制約は code comment に置く。comment には code から分かる処理内容を繰り返さない
- 複数案から選んだ長期的または後戻り困難な判断は ADR に残す
- ADR 以外の恒久設計文書には、source、executable contract、comment から復元できない非局所的な情報だけを残す
- repository-owned な情報を Memory や task-local note だけに置いてはならない

### 2.2 Executable Contracts

- accepted contract は、明示されたユーザー要求、public API / protocol / schema、accepted ADR、外部consumer、または信頼できる既存の executable contract に根拠を持つ。現在の source や test が存在することだけでは accepted contract とみなさない
- executable contract は、accepted contract、不変条件、validation rule、failure mode を機械的に検証するために置く。現在の表現や実装をそのまま固定することを目的にしてはならない
- 振る舞いまたは契約を変更する場合は、failure mode、利用者またはconsumerから観測できる影響、契約を所有する最小の安定境界を特定する。再発リスクと保守コストに見合う場合は、対応する test / type / schema / static check を同じ論理変更内で追加または更新する
- bug fix では対象 failure mode を修正前に再現し、修正後に解消したことを最も直接的な方法で確認する。費用対効果が合う場合は targeted regression test として残す
- 期待動作を変えない変更では新しい test を義務化せず、既存 contract が維持されることを変更リスクに応じた方法で確認する
- failing test、type constraint、schema、static check を、現在の source に合わせて通すためだけに削除、弱体化、skip してはならない。要求または契約を意図的に変更する根拠がある場合だけ更新する
- 検証方法は test に限定せず、対象の失敗を最も直接検出できるものを選ぶ。守る契約を特定できない、既存の検証で十分、または恒久化の便益が保守コストに見合わない場合は、新しい test を作らず、必要に応じて代替確認と残リスクを報告する
- 未実装の将来像を、長期間 failing / skipped test として正本化しない。将来の作業は plan、issue、または user-facing backlog に分離する

### 2.3 Conflicts

source と executable contract は優先順位の上下ではなく、現在状態と期待状態という異なる問いの正本である。両者が矛盾した場合は、失敗を消す前に、ユーザー要求、外部契約、accepted ADR、既存 test、履歴上の根拠から意図した動作を確認する。

- source が意図した contract から外れている場合は source を修正する
- contract を意図的に変更する場合は、source と対応する executable contract を同じ論理変更で更新する
- 判断理由そのものが変わる場合だけ ADR を追加または supersede する
- 意図を確定できず、選択が結果を実質的に変える場合は、推測で整合させず、根拠、選択肢、影響を示して確認を求める

### 2.4 ADR and Architecture Documents

- 局所的な実装詳細を超え、次のいずれかに該当する決定は `docs/adr/` に ADR を必ず作る
  - 複数の妥当な選択肢から一つを選ぶ
  - public contract、永続化、migration、security、concurrency など後戻りコストが高い
  - 外部制約または長期的 trade-off が決定を左右する
  - 理由を失うと将来誤って覆される可能性が高い
- ADR には status、context、decision、alternatives、consequences を残す。現行 class 構成、網羅的な API 仕様、実装手順は複製しない
- ADR 以外の恒久設計文書は、次をすべて満たす場合だけ作成または維持する
  - 複数 subsystem / process / repo / 外部 service に波及する
  - 単一の code location や test 群から全体像を復元できない
  - 誤解すると局所的には正しくても全体不整合になる
  - test / type / schema / static check / comment だけでは背景や制約を表現できない
- 設計したこと、code を変更したこと、task-local note が存在することだけを理由に、恒久設計文書を作成または同期してはならない
- 現行 class / module 構成、通常の API 入出力、局所的な処理順、状態遷移、validation rule を、現行仕様として恒久文書へ複製してはならない
- 今回の変更が直接影響する既存設計文書を更新する場合は、実装の写経を削り、code から復元できない情報と source / executable contract への pointer だけに縮める。無関係な既存文書の負債は cleanup せず、必要なら残リスクとして報告する
- README、user guide、runbook、setup、運用手順は設計文書とは別に扱う。利用方法、操作、運用、command が変わる場合は、必要な文書を更新する

## 3. Task Workflow

1. 依頼を answer / explain / review / diagnose / plan、change / build / fix、external action に分類し、goal、制約、期待結果、完了条件、権限境界を整理する。調査前の原因は仮説として扱う
2. repositoryに関係するtaskでは、適用されるinstruction、repositoryとbranch、dirty worktree、既存差分を確認する。過去の判断や環境制約が今回の選択を変え得る場合だけ、taskに合うexplicit targetでMemoryを検索する
3. 関連するsource、test、type、schema、static check、comment、accepted ADR、直接関係する文書を読む。現在状態、期待状態、局所的理由、決定理由、非局所的制約を分け、根本原因、影響範囲、意図したcontractを確定する。結果を実質的に変える不明点だけユーザーへ確認する。answer / explain / review / diagnose / planは必要なread-only checkの後に手順11へ進み、変更を加えない。external actionは対象、現在状態、影響、可逆性、必要な明示確認を確定し、許可された操作だけを実行する。実行後はpostconditionをread-backし、失敗または部分成功時は再試行前に現在状態と必要なauthorityを再確認してから手順11へ進む
4. change / build / fixでは実装前に、plan artifactを使わない、`task-brief`、会話内checklist、plan fileのどれを選ぶか、knowledge placement、ADR / architecture gate、`contract-closure` gate、delegation、作業sliceと依存関係を決める。小さく低リスクで責務が一つのtaskは一つのsliceとし、不要なplan、delegation、reviewを省略する。`contract-closure`対象ではaccepted contractの根拠、supported scope、観測可能なfailure、canonical owner、兄弟入口、executable anchorを実装前に確定する。required / optional、default、failure semanticsなど結果を反転させる契約根拠が競合または未確定なら、reviewerへ判断を委ねず、根拠とconsumer影響を確認してから進む
5. 各 slice では、期待動作を変更または修正する場合に、対象 failure mode、観測可能な影響、契約を所有する安定境界を決める。費用対効果が合う executable contract が必要なら先に追加または更新し、bug fix では修正前の失敗を確認する。既存の責務境界、helper、標準 parser、妥当な既存 pattern を優先して実装し、targeted check を実行する。現在の実装を固定するだけの既存 test pattern は踏襲しない
6. source、適用可能な executable contract または理由付きの代替確認、targeted check が揃った slice を implementation-complete candidate とする。次に外部の read-only review cycle へ渡す場合、今回変更した scope / dependency topology に semantic owner の分散、独立責務の混在、canonical boundary の迂回、slice 間の decision 重複、または新しい test coupling を示す具体的な evidence があるときだけ、main implementation session が `consolidate-structure` Skill を使う。file 数、diff 量、review 回数、finding 数、clean review、PR 作成依頼だけを trigger にしない。review-only session と read-only child はこの Skill を実行しない。Skill が bounded consolidation を必要とした場合は slice を implementation 中へ戻し、手順5の実装と検証をやり直す。同一 gate の post-edit phase では計画した delta の closure だけを確認し、新しい探索 pass や外部 review を自動で開始しない。qualifying evidence を inventory した gate instance は `ready-unchanged` または `ready-after-consolidation` でのみ後続 review へ進み、`replan-required` では手順3から5へ戻る。`not-applicable` は次のreason別規則へ戻す
7. slice の targeted review は、後続 slice の前提になる、高リスク境界を持つ、または独立 review の便益が明確な場合だけ行う。未完成、未実行、期待動作を観測できない途中状態は review しない。`blocking` finding は同じ slice 内で修正し、targeted check と targeted re-review で閉じる。ただし、`contract-closure`のFinding Promotion gateが`boundary prerequisite`と判定したfindingは同じsliceへ抱き合わせず、独立した先行論理変更として手順3から5へ戻す
8. 完了した slice を統合し、必要な ADR、利用者文書、runbook を更新する。主要な回帰リスクに応じて検証範囲を広げ、source と executable contract、knowledge placement、ADR / architecture gate を再確認する。integration 自体が slice 間に手順6の qualifying topology evidence を生じた場合は、final review handoff 前に手順6を適用する
9. 「Validation and Review Completion Gates」または`contract-closure` Skillが独立reviewを要求する変更では、統合後のcomplete diffをreviewする。high-riskまたはnon-localな`contract-closure`対象では、source、適用可能なexecutable contract、targeted check、該当する構造収束gateが揃ったexact source stateとreview contractをtask-localなCandidate Definitionとして凍結し、checkとreviewをEvidence Ledgerへ記録する。変更した不変条件がtriggerする専門lensを同じCandidate Definitionへ独立に適用し、全specialist reviewを終える。review findingを受けたら、rootの最終分類とsource展開の前に`contract-closure`のFinding Promotion gateでaccepted contractとの関係、到達証拠、supported scopeを判定し、risk acceptanceできずsource repairが必要な場合だけpromotion先のsemantic owner / subsystemを確定する。証拠不足なら分類を保留して追加調査する。`accepted risk`はsourceとreview contractを広げず既存のrisk acceptance規則で閉じ、`current-scope repair`だけを同じfamilyへ展開して修正・再検証し、新Candidate上でfindingを出したlensはfamilyとdeltaをtargeted re-reviewし、他のtrigger済みlensも担当cellへのdeltaの非影響を再確認する。`boundary prerequisite`は現在のCandidateへ混ぜず独立した先行論理変更へ戻し、`hardening follow-up`は現行sourceとreview contractを拡張しない。全trigger済みlensの`current`な証拠が同じ現行Candidateへ揃った後、`blocking`の有無にかかわらず、利用可能なら`fork_turns="none"`を使い、過去findingやspecialist reviewの結論、実装者の結論を渡さないfresh reviewerが更新後complete diffをholisticにreviewする。その他のfinal reviewはslice間のinteractionとcross-cutting contractを優先し、統合後の`blocking` findingへ対応した場合だけfresh-context full-diff closure reviewを適用する
10. repository-owned な情報を正本へ配置する。commit と push は別々に権限を判定し、対象差分と検証結果を再確認する
11. user-facingなfinal responseを返す直前に、§6のMemory reflectionを行う。その後、依頼種別に応じて、answer / explain / diagnoseは結論、根拠、未確定事項、planはscope、依存関係、検証、open question、reviewはfindingと分類根拠、change / build / fixは`validation-report`の形式で変更、検証、未実行、残リスク、external actionは対象、実行結果、postcondition、部分成功またはvalidation gapを報告する

- scope、contract、責務境界、slice の依存関係が変わった場合は手順3から5を見直す。validation failure は対象 slice へ戻し、追加 authority または結果を変えるユーザー判断が必要な場合は作業を止めて確認する
- Candidate Definition、Evidence Ledger、source identity、失効判定、evidence status、review handoffの規範的定義は`contract-closure` Skillを正本とする。Task workflowはCandidate reviewを開始する条件、specialist reviewとfinding対応の合流順序、holistic reviewの開始条件を定める。全trigger済みlensの現行証拠が同じCandidateへ揃った後にcomplete-diff holistic reviewを行い、targeted re-reviewで代用しない
- `consolidate-structure` が `not-applicable` を返した場合はreason別に戻す。`no-topology-evidence`では既に予定したreview handoff、`candidate-not-ready`では手順5、`wrong-session`では割り当て済みのread-only task、`pr-requested`では新しい構造整理を始めずPR workflow、`no-review-handoff`ではSkillをreview triggerにせず既存lifecycleの次の手順へ進む
- review finding への対応後は、修正が手順6の qualifying topology evidence を新たに生じた場合だけ新しい implementation-complete candidate として同手順を再判定する。finding、review 回数、または Skill 自身の edit だけを再発火条件にしない
- Finding Promotionで新しいsemantic ownerまたは別subsystemの変更が必要になった場合は、`boundary prerequisite`として独立したaccepted contractと完了gateを持つ先行論理変更へ分ける。各logical changeが自身のsourceとcontractを閉じても、どの適用・deploy順序にも有効な中間境界状態を作れず、現在のaccepted contractが横断変更を明示要求する場合だけ同じ論理変更へ残す。通常のsource / test編集順、Candidate維持、review再実行、commit、PR、branchの都合を理由に抱き合わせない
- ユーザーが PR 作成を依頼した後は、未実施の `consolidate-structure` を新たに開始しない
- slice を閉じるには、source、適用可能な executable contract または理由付きの代替確認、targeted check が揃い、未解決の `blocking` findingがないことを要求する

- 無関係な cleanup、rename、format、refactor を混ぜない
- public API、永続化、migration、外部副作用、認可、並行処理、resource limit、owner / scope、または複合不変条件を変更・修正・reviewする場合は、`contract-closure` Skillを実装前の影響展開と完了前のclosure確認に使う
- 同じ問題が複数箇所にある場合は、`contract-closure`のFinding Promotion gateで同じsupported scopeとsemantic ownerに属すると確認した範囲について、呼び出し側の個別回避より適切な共有境界での修正を先に検討する。新しいownerまたは別subsystemへは自動展開しない
- 後方互換性または移行期間が要求や外部契約として確認できない限り、古い経路を fallback として残さない。方式を変更する場合は、依頼範囲内の呼び出し側、設定、test を同じ論理変更で移行する
- multi-step task では tool 実行前に短い見通しを示し、その後は major phase、finding、判断変更だけを update する。routine tool call は逐次実況しない

### 3.1 Code Structure, Source Organization, and Comments

- コメントで処理構造を説明する前に、命名、関数抽出、type、module、責務分割によって構造を表現できないか検討する。分割後も必要な comment は、構造から復元できない理由、外部制約、競合対策、workaround、または意図的な非直感的処理に限定する
- 一つの file、class、component が複数の独立した workflow、変更理由、または別々に検証できる責務を持つ場合は、凝集した単位への分割を優先する。一度しか使わない処理でも、transaction、authorization、外部副作用、状態遷移、failure boundary を明確にする場合は抽出してよい
- file や関数が大きくなった場合は、行数を違反条件にはせず、変更理由、状態管理、外部副作用、検証単位の混在を review する。新しい抽象化や分割は、探索コスト、依存関係、複雑さ、重複、責務崩れを実際に減らす場合だけ行う
- source は規模にかかわらず、domain、feature、capability、ownership など安定した意味を持つ directory へ配置し、file 数の増加まで分割を待たない。project root には project metadata、assembly-level configuration、composition root、project 全体を代表する入口、または project 全体で共有する少数の型だけを置く
- `Entities`、`Services`、`Helpers`、`Utils` のような技術種別だけの directory より、変更理由と責務が揃う domain / feature 単位を優先する。1 file だけでも境界が明確なら directory を設けてよいが、将来予測だけを根拠に意味が未確定な階層を作らない
- source の物理移動、namespace 変更、public contract 変更、永続化 metadata への影響を分け、整理目的の変更へ不要な contract 変更を混ぜない

### 3.2 Test Design

test の目的は、変更を検知すること自体ではなく、accepted contract への違反と現実的な regression を検知することである。accepted contract を変更しない修正や behavior-preserving な refactor まで Red にする test は、保護範囲ではなく結合先を誤っている。

- test を追加または拡張する前に、検出する failure mode、違反時に影響を受ける利用者またはconsumer、accepted contract の根拠、契約を所有する最小の安定境界を説明できるようにする。説明できない場合は test を作らない
- 一つの test は、一つの観測可能な期待動作、不変条件、failure mode、または明示された wiring contract を検証し、名前から対象契約と失敗条件を特定できるようにする
- assertion は、契約を最も直接観測できる安定境界へ置く。unit test でも入力と出力、状態遷移、外部副作用、error、不変条件を検証し、内部構造や実行手順を正しさの代用にしない
- test は、accepted contract を維持した変更では原則 Green を保つ。source、markup、文言、snapshot、内部callなど表現や実装の詳細は、その詳細自体が根拠のある accepted contract である場合だけ固定する
- mock、spy、hookは、境界の隔離、決定的なfailure再現、送出contractの観測に使える。ただし最終的なassertionは、観測可能な状態、副作用、error、または不変条件へ置く
- 変更箇所、coverage、test件数、既存testの存在だけを追加理由にしない。既存の検証で同じ failure mode を十分に検出できる場合は重複testを増やさない
- test より type、schema、static check、build、smoke、browser / visual check、task-local check の方が対象の失敗を直接検出できる場合は、そちらを選ぶ
- characterization test は一時的な安全網として扱い、現在挙動の正しさの根拠にしない。恒久化する場合は accepted contract に基づくassertionへ変換し、変換できないものは目的を終えた時点で削除する
- 実装詳細だけを固定するtest、価値なく重複するtest、恒常的にflakyなtestは書き換えまたは削除する。accepted contract を意図的に変更する場合は、source と対応するtestを同じ論理変更で更新する

## 4. Validation and Review Completion Gates

change、build、fix は、次を確認するまで完了扱いにしない。

- 修正対象のfailure mode、または新規・変更したaccepted contractを、対象の失敗を最も直接検出できる方法で検証した
- 主要な回帰リスクに応じて lint、typecheck、build、smoke test へ必要な範囲で広げた
- source と executable contract が、意図した動作について矛盾していない
- 新規または変更したexecutable contractについて、根拠、failure mode、観測可能な影響、安定境界が明確である。恒久化しない場合は、必要に応じて代替確認と残リスクを報告した
- 新規または変更したtestが、accepted contractを維持した変更まで不必要にRedにしないことを確認した
- test、type、schema、static check を、現在実装に合わせるためだけに弱体化していない
- ADR gate を判定し、required なら ADR が存在する
- architecture document gate を判定し、今回の変更が直接影響する文書に不要な仕様複製や陳腐化した説明を残していない
- 実行できない検証は、理由、代替確認、未検証リスクを明示した。実行していない検証を成功扱いしていない
- 手順6の構造収束 gate が適用された場合は、結果が `ready-unchanged` または `ready-after-consolidation` であり、整理で差分を変更したときは元の targeted check と影響に応じた broader check、該当する Sibling Sweep を最終差分に対して再実行した
- reviewable slice の targeted review で `blocking` findingへ対応した場合は、同じ slice の targeted check と targeted re-review を行う。統合前の途中状態へ fresh-context full-diff review を適用しない
- `contract-closure` 対象が複数入口、複数subsystem、または高リスクな失敗へ波及する場合は、実装とtargeted checkの後に独立したreviewerで反例を探索し、root sessionがfindingをsourceとexecutable contractへ照合した。reviewerを利用できない場合はfresh-context second passと未実施リスクを報告した
- frozen Candidateを使うreviewでは、`contract-closure` Skillが定めるCandidate Definition、Evidence Ledger、失効判定、evidence status、review handoffに従い、現行Candidateの完了証拠とgapを追跡できる。specialist reviewを行った場合は、全trigger済みlensの現行Candidateに対する証拠、確認したmatrix cell、未確認cell、hardening候補が区別され、必要なspecialist closure後にcomplete-diff holistic reviewを行った
- review findingはseverityとは別に、root sessionが`blocking`、`risk-candidate`、`non-material`、`invalid`へ分類する。reviewerの分類は提案として扱い、root sessionはsourceを広げる前に`contract-closure`のFinding Promotion gateを適用し、そのdispositionとsource、accepted contract、executable contract、supported scopeを照合して最終分類を確定する
- `blocking` findingとするには、accepted contractまたは明示された安全境界への違反、supported scopeで現実的な到達条件、具体的な影響、sourceまたはexecutable contractに基づくevidenceを示す。style preference、一般的なhardening案、到達条件を示せない仮説は`blocking`にしない
- Finding Promotion gateでは、accepted contractとの関係または現実的な到達性が未確定なら`investigation-pending`として最終分類を保留する。証拠が揃った後、source repairのowner判定より先に`accepted risk`を評価して`risk-candidate`とし、修正が必要な`current-scope repair`と`boundary prerequisite`は`blocking`、`hardening follow-up`はcurrent reviewの`non-material`、`dismissed`は`invalid`として扱う。`current-scope repair`だけを同じ不変条件familyへ展開し、accepted riskとhardeningを現在のsource、test、Candidate、review contractへ加えず、別owner / subsystemへ必要な変更は原則として独立した先行論理変更へ分ける
- `risk-candidate`は、発生可能性が低く、影響が限定され、自動検知でき、復旧手段があり、機密性侵害または不可逆なデータ損失を伴わない場合に限りaccepted riskとして完了できる。発生条件、影響、検知、復旧、follow-upの要否を残す
- accepted riskとして完了した`risk-candidate`に、将来の対応、運用上の注意、または再判断が必要な場合は、repository内の既存の管理表へ追跡可能に残す。管理表がない場合は対象repositoryの適切な場所に作成し、以後は最初に採用した形式を維持する。repository instructionが別の管理方法を指定する場合はそちらを優先する
- `non-material`と`invalid`は恒久記録の対象にしない
- auth bypass、secretまたはpersonal dataの露出、現実的なinjection、不可逆なデータ破損を未修正で残す場合は自動的にrisk acceptanceせず、ユーザー判断を求める
- non-trivialまたはhigh-riskな変更を統合した後のcomplete-diff reviewで`blocking` findingへ対応した場合はtargeted checkを再実行し、実装・前回review履歴を引き継がない新しいreviewerで更新後diff全体を対象とするfresh-context closure reviewを一度行う。利用可能なら`fork_turns="none"`を使う。Candidate-boundなreviewのhandoffは`contract-closure` Skillを正本とし、Candidateを使わないreviewではgoal、ユーザー要求またはaccepted contract、baseからの更新後raw diff全体と未追跡を含む変更一覧、canonical anchors、実行済みcheckだけを渡す。どちらも過去finding、claimed resolution、実装者の結論、既存Closure Mapは渡さない
- fresh-context closure reviewで新たなfindingが出た場合も、sourceを広げる前にFinding Promotionを適用する。`current-scope repair`だけをfinding familyへ展開して修正し、そのfamilyと修正で生じたdeltaをtargeted reviewする。`boundary prerequisite`は独立した先行論理変更へ戻し、`accepted risk`と`hardening follow-up`は現行sourceとreview contractを広げない。public contract、永続化、認可、外部副作用、並行処理などの高リスク境界を修正が拡張した場合、または無関係な確認済み範囲を再度開く具体的なevidenceがある場合だけ、追加のfull-diff reviewを行う
- independent full-diff reviewは一つの論理変更につき3回を上限とし、通常はinitial reviewとfresh-context closure reviewの2回で閉じる。3回目では追加reviewのtriggerとscopeを明示し、同一論理変更の4回目のfull-diff reviewは行わない。高リスクなscope拡張を続ける場合は、ユーザー確認後に新しいaccepted contractを持つ別の論理変更として切り出す
- 3回目のreview後も未解決の`blocking` findingが残る場合は完了扱いにせず、要求、設計、責務境界、contractの再確認またはユーザー判断へ戻る。完了条件はfinding総数が0であることではなく、未解決の`blocking` findingがなく、その他のfindingが根拠付きで分類されていることである

- review は finding-first とし、重大度順に bug、回帰、security、仕様逸脱、source と contract の不一致、accepted contract ではなく現在実装を固定するtest、責務境界の崩れ、test不足または価値のない重複、ADR見落とし、設計文書への局所仕様複製を優先する
- review結果では`blocking` findingの有無、各findingの分類根拠、accepted risk、validation gap、残リスクを短く示す

## 5. Planning and Task-Local Notes

- goal、scope、期待動作、検証方法が明確で、一つの責務を1 sessionで閉じられる作業にはplan fileを作らない。要求が少し曖昧または複数変更を含む場合は、`task-brief` Skillで作業の輪郭だけを会話内に固定する
- 複数の別々に検証可能な責務を1 sessionで完了できる作業は、会話内の短いchecklistへ分ける。項目はtool callではなく、観測可能な成果、依存関係、targeted check、必要なreview triggerで表す
- 複数 session、cross-repo、高リスク、ユーザー確認待ち、または作業手順の保存価値が高い場合だけ `docs/plans/YYYYMMDD-topic/plan.md` を作る
- Plan は作業手順であり、設計は実装前後を通じた判断活動として分ける。設計したこと自体を恒久文書の作成理由にしない
- scope、contract、責務境界、依存関係が変わった場合だけplanまたはchecklistを更新する。routineなtool結果だけで計画を書き直さない
- 実装前の design note は、不可逆な決定の review、複数主体の合意、複雑な比較に必要な場合だけ task-local に作る。実装後に repo 設計書へ同期することを既定にしない
- 情報配置、ADR、全体設計文書の要否が明確でない場合は `knowledge-placement` Skill を使う

## 6. WithMate Memory

- Memoryは、repositoryの正本にするほどではない文脈、projectをまたぐユーザーの選好、Characterとの会話継続に役立つ関係性、好み、エピソードをsession間で検索・再利用するために使う。書き込みは小さな再利用価値も拾う方向へ広めに判断し、想起は現在のtaskや会話に関係する場合へ絞る。repository固有であることだけを理由に保存対象から除外しない
- durable Memory の操作手順、target、append、forget、error handling は `withmate-memory` Skill / CLI を正本とし、この節へ複製しない

### 6.1 Recall

- Memoryの想起はturn末尾のreflectionと分け、現在のtaskや会話に過去の文脈が関係し得るときだけ行う。ユーザーが過去の記憶を尋ねた場合、または過去の決定、制約、選好、failure pattern、workaround、会話上の関係性やエピソードが今回の判断または自然な会話継続に影響し得る場合に、taskに合うexplicit targetを検索する
- すべてのturnで儀式的に検索しない。routineなsearch / readはbackground recallとし、結果が回答へ実質的に影響する場合、競合する場合、またはユーザーが尋ねた場合だけ明示する。Memory failureは隠さず、Memory access自体が依頼の目的でない限り非ブロッキングとする

### 6.2 End-of-turn Memory Reflection and Append

- すべてのuser-facing turnで、final responseを返す直前にMemory reflectionを行う。reflectionでは今回のturnと直近の会話を振り返るが、Memoryのsearchやappendは具体的な候補がある場合だけ行う。候補がないことを正常な結果とし、turn全体の要約を一律に保存しない
- reflectionでは、作業の再利用文脈を探すProject lensと、会話継続の文脈を探すCharacter lensを別々に適用する
  - Project lensでは、repository固有の背景、判断、制約、規約、作業上の選好、信頼できる調査結果、workaround、環境固有の小さな知見、正本へのpointerをprojectまたはuser-globalの候補として扱う
  - Character lensでは、関係性、距離感、interaction style、呼び名、継続したい話題、軽いinside joke、共有エピソード、次回触れれば会話が自然につながる具体的な反応をcharacterまたはcharacter+projectの候補として扱う
- 一つのturnに両方の候補がある場合はtargetを混ぜず、別々のentryとして扱う。関連する同一targetの候補は、検索と訂正がしやすい一つの主題へまとめてよい
- repository-ownedな現在状態、期待動作、契約、決定理由は「Source of Truth and Knowledge Placement」の正本規則に従い、Memoryだけを正本にしない。Memoryには正本へのpointerと、repository artifactとして維持する価値は低いが別sessionで役立つ非正本文脈を置く
- appendに、確実な再利用、長期的重要性、複数回の反復を要求しない。別sessionで知っていれば開始、判断、説明、会話継続が少し自然または速くなるという具体的な効用があれば、短い`note`、`context`、`preference`として残してよい
- 候補が具体化したら、Skillの手順に従って明示targetの既存entryを検索し、重複または訂正でないことを確認してappendする。title、preview、bodyだけで別sessionのagentが再利用できる粒度へ短く要約する
- 未完了状態、未実行検証、次のactionはMemoryへ置かない。すべての会話、transient progress、一時的な感情、routineな相槌や雑談、secret、token、private path、raw log、大きなdiff、speculative claimは保存しない

### 6.3 Character Memory

- Character Memoryは人物プロファイルや事実認定ではなく、自然な会話継続のための観察記録として扱う。ユーザーが話した内容と推測を分け、entryでは発言または会話上の出来事へ帰属させる
- Character lensの候補には、複数回の反復や特別に印象的であることを要求しない。ユーザーが会話内で明示した関係性、距離感、好み、継続したい話題、具体的な反応、次回触れれば会話が自然につながるエピソードは、1回の会話で得た内容でも、`remember`という語がなくても依頼範囲のMemoryとして追加できる
- 恋愛、独占、現実の関係、属性、感情をMemoryから拡張して断定しない。現在のユーザー発言とCharacter Definitionを過去のMemoryより優先する
- 既存entryのcorrection / forget、依頼範囲外のappend、推測に基づいてfuture behaviorを実質的に変える記録にはユーザーの明示依頼を求める。ユーザーの remember、forget、correct、stop using memory の依頼は Skill の手順で処理する

## 7. Delegation

- 独立した調査、計画、実装 slice、検証、別視点 review で品質または速度が明確に上がる場合は、明示依頼がなくても subagent を使える
- hook が選んだ mode と task risk に従い、境界が明確な低から中リスク作業は fast role、read-heavy 調査は researcher、機械的検証は validator、非自明または高リスクな作業は適切な standard role に渡す
- researcherは根拠収集、validatorは機械的検証、reviewerは実装結論を前提にしない反例探索へ使い、相互の代用にしない
- delegation は調査後に決めた slice、依存関係、risk に合わせる。並列化は互いに依存せず編集範囲が重ならない作業だけに使い、前提 slice の完了前に依存 slice を開始しない
- 任意の品質向上としての delegation と、`contract-closure` や completion gate が要求する独立 review を区別する。必須 review をresearchまたはvalidationで代用しない
- 構造、責務、public API、永続化、migration、auth / security、data loss、concurrency の設計は designer、高リスクまたは release-critical な review は reviewer に渡す
- `contract-closure`が複数の独立したreview lensをtriggerした場合は、同じCandidate Definitionに対して1 lensにつき1 reviewerを割り当て、必要な1から3 lensを並列にreviewする。file数やdiff量だけでlensまたはreviewerを増やさず、同じlensへ複数reviewerを重ねない。specialist reviewerは割り当てられたmatrix cellへ集中し、root sessionがfinding familyの統合、分類、修正順序、Evidence Ledger、holistic closureを所有する
- fast role には full history を渡さず、担当範囲、必要な source / executable contract / diff、禁止事項、既知の検証結果、出力形式、完了条件だけを渡す
- ユーザーが subagent を明示した場合は目的に合う agent type を指定する。該当 role がない場合だけ default / worker を使う
- 通常の親子間返却は subagent の最終メッセージを使い、`result.md` その他の repo artifact を一律に要求しない
- role契約で編集を許可されたworkspace-writeのchildは、root sessionが割り当てた非重複範囲をshared working treeで編集できる。root sessionはscope、競合回避、採否、knowledge placement、統合、最終検証、commit、user-facing finalを所有する
- task worktree は、競合する並列編集、破壊的または大規模な試行、隔離が必要な検証を root session が明示的に選ぶ場合だけ使う
- `agents/*.toml` を静的な role 責務、禁止事項、出力契約、model、sandbox の正本とし、hook には現在の routing mode、quota fallback など実行時にしか決まらない差分だけを置く
- subagent の結果と差分は採用候補として root session が検証し、恒久的な情報は「Source of Truth and Knowledge Placement」に従って配置する

## 8. Language, Paths, and Reporting

- ユーザーへの回答、生成ドキュメント、commit message は日本語で書く。code comment は既存の言語と流儀に合わせる
- 回答は結論から始め、判断に必要な根拠、重要な caveat、次の action を残す。導入、重複、定型的な安心表現、任意の背景を先に削る
- 生成物では repo 内 path を repo root 相対で示し、絶対 path や repo 外 path を残さない
- log を示す場合は必要な行だけを抜き出し、path を相対化する
- finalでは依頼種別に応じて必要な項目だけを報告する。answer / explain / diagnoseは結論、根拠、未確定事項、次のaction、planはscope、依存関係、検証、open question、reviewは`blocking`の有無、findingの分類根拠、accepted risk、validation gap、残リスク、change / build / fixは変更内容、実行した検証、未実行の検証、残リスク、external actionは対象、実行結果、postcondition、部分成功またはvalidation gapを区別する

## 9. Git

- commitとpushは別々の外部作用として扱い、それぞれユーザーが明示的に依頼した場合だけ行う
- commit前にstatusと対象diffを確認し、1つの論理変更単位にユーザー由来の無関係変更を混ぜない。stageは対象pathまたはhunkだけを選び、既存のstaged変更へ無断で混ぜない
- commit message は conventional commits とし、commit した場合は hash、要約、検証結果を報告する
