# ADR-0022: テスト価値の設計、本文整合、保持先を段階別に審査する

- Status: accepted
- Date: 2026-08-31
- Supersedes: none
- Amends: ADR-0020, ADR-0021

## Context

- ADR-0020で導入した審査は、metadataとtest sourceを一度にAIへ渡す。そのため、metadata単体では検証価値を説明できなくても、AIがtest本文から意味を補完して`ACCEPT`できる。
- attribute、annotation、route、DI登録などのdeclarationだけを観測するtestが、runtime behaviorやconsumer impactまでclaimし、永続的なbehavior testとして残る場合がある。
- 現行の`ACCEPT`には、metadataの自己完結性、test本文との整合、保持先、現在の変更を完了扱いにできるかという別々の判断が含まれている。
- 全recordを高コストなreviewerへ渡さず、反復可能な審査はLunaで処理し、曖昧、高リスク、監査対象のrecordだけをSolへ限定して渡したい。
- metadata formatを拡張するときも、ADR-0020の決定論的な抽出とADR-0021のGit差分選択を維持し、変更していないv1 recordの一括移行を要求しない。
- custom agentの定義追加と新しい完了gateの有効化を同時に行うと、必要なagentをまだ起動できないsessionが新しいgateを満たせないbootstrap循環が生じる。

## Decision

### 一つのSkill実行を二つのLuna phaseへ分ける

- `review-test-value`の外部interfaceは一回のSkill実行として維持する。
- syntactically validな全recordを、`test_value_luna`による次の二phaseへ必ず渡す。
  - Phase 1はmetadataだけを読み、自己完結した検証上の主張になっているかを審査する。
  - Phase 2は固定済みのPhase 1結果、同じmetadata、test sourceを読み、actual observableとobservation boundaryを照合する。
- Phase 1 packetへtest source、source line、assertion summary、production source、oracle本文、実行証拠を含めない。
- Phase 1が`REDESIGN`でもPhase 2を省略しない。Phase 2でactual observableと保持先候補を特定し、修正後の行き先を判断できるようにする。
- 同じLuna child sessionを二turnで使う。runtimeがfollow-upをサポートしない場合は二つのLuna child runを使えるが、二phaseを一promptへ統合しない。
- 親agentはPhase 1結果をPhase 2開始前に固定し、Phase 2による変更を受け付けない。

### Solは追加contextを必要とするrecordだけを審査する

- Phase 1が`NEEDS_CONTEXT`、Phase 2が`RECHECK`、observation boundaryに複数の妥当な解釈がある、helper、fixture、mock、oracle、SUTを読まなければ判定できない、high-risk、またはdeterministic audit対象であるrecordを`test_value_sol`へ昇格する。
- SolにはLunaと同じ入力を再送するだけでなく、必要なoracle、SUT、helper、fixture、mock、関連test metadata、実行証拠を含むbounded packetを渡す。
- Solはpacket外をrepository-wideに探索せず、packetだけで閉じられない場合は必要なsourceを指定して`NEEDS_CONTEXT`を返す。
- `test_value_sol`はSkill固有のadjudicationを所有し、`reviewer`、`targeted_reviewer`、`slice_reviewer`による通常のcode reviewを代替しない。

### high-risk routingはmetadataだけに依存させない

- metadata v2は、次の値から成るoptionalな`risk_tags`を持てる。
  - `security`
  - `authentication`
  - `authorization`
  - `billing`
  - `irreversible-data-loss`
  - `privacy`
- 親workflowはaccepted contract、Closure Map、変更scopeからrecord locatorに対応するrisk tagを追加できる。
- `kind = "security"`、metadataの`risk_tags`が空でない、または親workflowがrisk tagを付けたrecordはSolへ昇格する。
- 親workflowとmetadataのrisk tagは和集合にする。metadataは親workflowが付けたrisk tagを解除できない。
- 未知のrisk tag、型不一致、親入力とrecord locatorまたはhashが一致しないpacketはAI審査前に拒否する。

### status、disposition、gateを独立して決める

- `status`はmetadataとtest sourceの審査結果を表す。
  - `ACCEPT`: metadataが自己完結しているか、明示された追加contextでPhase 1の不確定事項が解消され、test sourceと整合し、必要なdeep reviewが通過した。
  - `REDESIGN`: metadata、test source、または両者の対応に具体的な欠陥がある。
  - `NEEDS_CONTEXT`: 必要なsource、agent、revision、または依存がなく判定を閉じられない。
- `disposition`は現在のtest artifactの保持先を表す。
  - `KEEP_PERMANENT`
  - `KEEP_TEMPORARY`
  - `MOVE_TO_POLICY_CHECK`
  - `DROP`
- `gate`は現在のSkill実行を完了扱いにできるかを表す。
  - `PASS`
  - `CHANGES_REQUIRED`
  - `BLOCKED`
- `status = REDESIGN`でも、Phase 2がactual boundaryを確定できた場合はdispositionを返す。actual boundaryまたは保持根拠を確定できない場合だけ`disposition = null`とする。
- `status = REDESIGN`は常に`CHANGES_REQUIRED`、`status = NEEDS_CONTEXT`は常に`BLOCKED`とする。
- `status = ACCEPT`でも、test artifactとdispositionが一致しない場合は`CHANGES_REQUIRED`とする。

statusはPhase結果とSol結果を次の優先順で決める。上の行に一致した場合は下の行を評価しない。

| 優先 | Phase 1 | Phase 2 | Sol | status |
| ---: | --- | --- | --- | --- |
| 1 | 未完了またはschema不正 | any | any | `NEEDS_CONTEXT` |
| 2 | any | 未完了またはschema不正 | any | `NEEDS_CONTEXT` |
| 3 | any | any | requiredだがunavailable、schema不正、または`NEEDS_CONTEXT` | `NEEDS_CONTEXT` |
| 4 | `REDESIGN` | any | not requiredまたは任意の完了verdict | `REDESIGN` |
| 5 | any | `MISMATCH` | not requiredまたは任意の完了verdict | `REDESIGN` |
| 6 | `VALID`または`NEEDS_CONTEXT` | `ALIGNED`または`RECHECK` | `REDESIGN` | `REDESIGN` |
| 7 | `VALID` | `ALIGNED` | not required、またはrequiredかつ`APPROVE` | `ACCEPT` |
| 8 | `VALID` | `RECHECK` | requiredかつ`APPROVE` | `ACCEPT` |
| 9 | `NEEDS_CONTEXT` | `ALIGNED`または`RECHECK` | requiredかつ`APPROVE` | `ACCEPT` |
| 10 | その他 | その他 | その他 | invalid combinationとして`NEEDS_CONTEXT` |

- Phase 1 `NEEDS_CONTEXT`またはPhase 2 `RECHECK`は必ずSolをrequiredにする。Solが追加contextで不確定事項を解消して`APPROVE`した場合だけ`ACCEPT`へ進める。
- high-riskまたはaudit対象はPhase 1、Phase 2のverdictにかかわらずSolをrequiredにする。Solはfrozen Phase 1 verdictとPhase 2 verdictを変更できない。Solが完了verdictを返した場合、Phase 1 `REDESIGN`またはPhase 2 `MISMATCH`のfinal statusは`REDESIGN`のままとする。Solがunavailable、schema不正、または`NEEDS_CONTEXT`なら上位のfail-closed規則を適用する。
- Phase 1 `REDESIGN`またはPhase 2 `MISMATCH`でhigh-riskでもaudit対象でもないrecordは、明白な欠陥としてSolへ送らない。
- requiredでないSol verdict、requiredなのにSolを実行していないresult、またはPhase 1 `NEEDS_CONTEXT` / Phase 2 `RECHECK`でSolがrequiredでないresultはinvalid combinationとして拒否する。

dispositionを決める前に、declaration自体がconsumerへ配布される正式artifactならactual boundaryを`public-boundary`へ再分類する。その後、actual boundary、lifecycle、保持根拠から次の表で決める。

| actual boundary | 条件 | disposition |
| --- | --- | --- |
| `declaration` | any | `MOVE_TO_POLICY_CHECK` |
| `implementation` | characterizationの期限・見直し条件、またはephemeralの削除条件を満たす | `KEEP_TEMPORARY` |
| `implementation` | `permanent`、またはtemporary条件が不正・不足 | `DROP` |
| `consumer`、`public-boundary`、`component-behavior` | `permanent`かつ保持根拠あり | `KEEP_PERMANENT` |
| 同上 | `permanent`かつ保持根拠なし | `DROP` |
| 同上 | characterizationの期限・見直し条件、またはephemeralの削除条件を満たす | `KEEP_TEMPORARY` |
| 同上 | temporary条件が不正・不足 | `DROP` |
| 未確定 | additional contextで確定できる可能性がある | `null` |

- 保持根拠はaccepted contract、security / safety property、compatibility、incident regression、reference modelのいずれかとする。packetだけでは保持根拠を確定できない場合は`disposition = null`、`status = NEEDS_CONTEXT`、`gate = BLOCKED`とする。
- schema上不正なlifecycle条件はPhase 1前にextractor errorとして停止する。AI outputに不正なlifecycle tupleが現れた場合はinvalid combinationとして`BLOCKED`にする。

record gateとSkill実行全体のaggregate gateは次の優先順で決める。

| 優先 | status | disposition / artifact / resolution | gate |
| ---: | --- | --- | --- |
| 1 | `NEEDS_CONTEXT` | any | `BLOCKED` |
| 2 | `REDESIGN` | any | `CHANGES_REQUIRED` |
| 3 | `ACCEPT` | `disposition = null`または不可能なartifact state | `BLOCKED` |
| 4 | `ACCEPT` | `KEEP_PERMANENT`かつpermanent testとして存在 | `PASS` |
| 5 | `ACCEPT` | `KEEP_TEMPORARY`かつ必要な期限・条件を持つtestとして存在 | `PASS` |
| 6 | `ACCEPT` | `MOVE_TO_POLICY_CHECK`または`DROP`で元testが残存、またはresolution未完了 | `CHANGES_REQUIRED` |
| 7 | `ACCEPT` | `MOVE_TO_POLICY_CHECK`または`DROP`で元testが消え、対応resolutionが`RESOLVED` | resolution entryがrecord gateを置き換えて`PASS` |

- aggregate gateは、`BLOCKED`が一件でもあれば`BLOCKED`、それ以外で`CHANGES_REQUIRED`または未解決resolutionが一件でもあれば`CHANGES_REQUIRED`、それ以外は`PASS`とする。
- recordもresolution entryも存在しない空のGit selectionは、以前にrequired resolutionがなかった場合だけ`PASS`にできる。以前のreviewでrequired resolutionが作られたSkill実行では、そのledgerを失った空selectionを`PASS`にしない。

### MOVEとDROPをSkill実行全体のgateで閉じる

- ADR-0021に従い、test declaration全体の削除はGit modeのsurviving recordへ含めない。
- `MOVE_TO_POLICY_CHECK`または`DROP`を返したrecordは、同じSkill実行中の一時的なresolution ledgerで追跡する。
- ledger entryは元のrecord locatorとmetadata hash、実行したaction、移行先artifact、direct check、resolution verdictを持つ。
- `MOVE_TO_POLICY_CHECK`は、元testの除去、移行先artifactの存在、そのartifactが宣言上のfailure modeを直接検出するcheckの成功を確認して`RESOLVED`にする。
- `DROP`は、元testの除去と、代替checkが不要または既存canonical ownerが同じfailure modeを検出する根拠を確認して`RESOLVED`にする。
- resolution ledgerはSkill実行中の派生物であり、repositoryの正本として保存しない。
- Skill実行全体のaggregate gateは、surviving recordがすべて`PASS`、必要なresolutionがすべて`RESOLVED`、`BLOCKED`がない場合だけ`PASS`とする。

### metadata v2とv1互換を分ける

- `@test-value v2`はv1の`failure_mode`を次のfieldへ分ける。
  - `fault`: assertionを失敗させるべき具体的な欠陥。
  - `observable`: assertionが直接読む値、状態、event、artifact。
  - `impact`: downstreamのconsumerまたはbusiness影響。optionalであり、直接検出した証拠として扱わない。
  - `observation_boundary`: metadata作成者が意図する観測境界。
- v2はoptionalな`risk_tags`と、`lifecycle = "ephemeral"`で必須となる`remove_when`を持つ。
- `characterization`は`expires_on`または`review_when`を一つ以上必須とする。`ephemeral`は`remove_when`を必須とする。`permanent`では三fieldを禁止する。
- extractor output schemaをv2へ上げ、errorの`diagnostics`とnon-blockingな`warnings`を分ける。
- path指定modeでv1を抽出した場合は`TEST_VALUE_V1_DEPRECATED` warningを返し、他にerrorがなければexit `0`とする。
- Git modeで新規または意味変更されたv1 recordは`TEST_VALUE_V2_REQUIRED` errorを返し、exit `1`とする。
- 未変更のv1 recordはADR-0021に従って選択しない。v1の`failure_mode`を機械的にv2 fieldへ分割しない。

### required agentはfail closedにする

- `test_value_luna`は`gpt-5.6-luna`、reasoning effort `medium`、read-onlyとする。
- `test_value_sol`は`gpt-5.6-sol`、reasoning effort `xhigh`、read-onlyとする。
- model、reasoning effort、sandbox、role contractは`agents/*.toml`を正本とし、Skill UI metadataやrouting hookへ複製しない。
- required agentを起動できない場合、親agentは同一sessionで代行せず、`status = NEEDS_CONTEXT`、`gate = BLOCKED`を返す。
- agent unavailableを別modelへのsilent fallbackで解消しない。

### bootstrapを二段階に分ける

- 最初のbootstrap changeでagent定義、review contract、packet builder、result validator、routing policy、v1を使う回帰checkを追加する。この時点では`AGENTS.md`の完了条件を新gateへ切り替えない。
- bootstrap changeを現行`review-test-value`契約で検証した後、live configへcustom agentを登録し、新しいsessionで起動確認する。live configの変更はrepository changeに含めず、明示的なauthorityを得て行う。
- 次のactivation changeでmetadata v2、warning、risk routing、resolution ledger、aggregate gateを実装し、`AGENTS.md`の完了条件を`gate = PASS`へ切り替える。
- activation changeは新しい二phase workflowで審査する。
- review result cacheとmodel effortの引き下げは初期activationの完了条件に含めず、運用証拠を得た後に別判断とする。

## Alternatives

- metadataとtest sourceを同じpromptで審査し続ける: metadata単体の不足をtest本文から補完でき、自己完結性を独立して判定できないため採用しない。
- Phase 1とPhase 2を一つのLuna promptへまとめる: 実行回数は減るが、metadata-only isolationを検証できないため採用しない。
- 全recordをSolへ渡す: 判断品質を揃えやすいが、明白なschema矛盾やdeclaration checkまで高コストな審査へ送るため採用しない。
- high-riskをmetadataの自己申告だけで決める: 作者がrisk tagを省略するとSol routingを迂回できるため採用しない。
- v1 deprecationをerror diagnosticとして返す: path指定modeでv1 recordを読みながら移行する経路まで停止するため採用しない。
- testを削除した後は空のGit selectionを自動的に`PASS`とする: 移行先policy checkや削除根拠を確認できないため採用しない。
- agent定義と新gateを同時に有効化する: 現在のsessionが新agentを起動できず、変更自身の完了条件を満たせないため採用しない。

## Consequences

- Positive: metadataの自己完結性とtest本文の整合を独立して審査できる。
- Positive: declaration checkを永続behavior testから分離しつつ、policy checkとしての価値は保持できる。
- Positive: high-risk recordはmetadataの申告漏れだけでSol審査を迂回できない。
- Positive: `ACCEPT`、保持先、完了gateの意味を分離できる。
- Positive: v1を読み取り可能なまま、新規・意味変更testへv2を強制できる。
- Negative: 一つのSkill実行に複数のagent turnとschema validationが必要になる。
- Negative: MOVEとDROPの完了には、record単位のreview resultに加えて一時的なresolution ledgerが必要になる。
- Negative: custom agent登録後の新sessionでmanual smokeを行うまでactivation changeへ進めない。
- Follow-up: deterministic auditの結果からLunaとSolのdisagreement、latency、token量を比較し、cacheまたはreasoning effort変更を別契約として判断する。

## Executable Anchors

現時点の正本は次のartifactである。

- Skill workflow: `skills/review-test-value/SKILL.md`
- Metadata format: `skills/review-test-value/references/comment-format-v1.md`
- Review contract and output: `skills/review-test-value/references/review-contract.md`、`skills/review-test-value/references/output-v1.md`
- Source: `skills/review-test-value/scripts/extract_test_values.py`
- Tests: `skills/review-test-value/scripts/test_extract_test_values.py`、`skills/review-test-value/scripts/test_extract_test_values_multilang.py`

bootstrap changeで次のartifactを追加し、実装とdirect checkが揃った時点で正本にする。

- Review contracts: `skills/review-test-value/references/metadata-review-contract.md`、`skills/review-test-value/references/alignment-review-contract.md`、`skills/review-test-value/references/deep-review-contract.md`
- Routing: `skills/review-test-value/references/routing-policy.md`
- Source: `skills/review-test-value/scripts/build_review_packets.py`、`skills/review-test-value/scripts/validate_review_result.py`
- Agents: `agents/test_value_luna.toml`、`agents/test_value_sol.toml`
- Tests: `skills/review-test-value/scripts/test_review_packets.py`、`skills/review-test-value/scripts/test_review_result_schema.py`、`skills/review-test-value/scripts/test_review_routing.py`

activation changeで次のartifactを追加または更新し、実装とdirect checkが揃った時点で正本にする。

- Metadata format: `skills/review-test-value/references/comment-format-v2.md`
- Output: `skills/review-test-value/references/output-v2.md`
- Source: `skills/review-test-value/scripts/extract_test_values.py`
- Tests: `skills/review-test-value/scripts/test_extract_test_values.py`、`skills/review-test-value/scripts/test_extract_test_values_multilang.py`
