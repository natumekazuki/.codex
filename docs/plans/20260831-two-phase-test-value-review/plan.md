# テスト価値の二段階審査と保持先判定

## 2026-09-05の継続作業

この計画のbaseと完了チェックは2026-08-31のbootstrap履歴である。#42〜#45の作業baseは`f7ba58ae47263c2a6a46d006c92c1d69ec29f704`であり、下記の旧baseを流用しない。

runtime activationの同一child二turn、follow-up fallback、native registry登録を前提とする未完了手順は、#42〜#45とADR-0022の独立`codex exec`方式に置き換えた。Phase 1、Phase 2、必要なSolは各新規runとし、強制隔離と実効設定を確認する。過去のチェック済み項目は、この新しいtransportの成功証拠ではない。

標準Skillと完了gateは旧方式を維持する。隔離smoke、実モデルE2E、固定した候補自身の新方式審査、新規sessionからの候補読込が揃うまで標準切替を保留する。

## Goal

- metadataだけで検証上の主張が成立することをLuna Phase 1で確認する。
- syntactically validな全recordについて、metadataとtest sourceの整合をLuna Phase 2で確認する。
- 曖昧、高リスク、deterministic audit対象のrecordだけを、追加context付きでSolへ昇格する。
- `status`、`disposition`、record gate、Skill実行全体のaggregate gateを決定的なruleで確定する。
- declaration checkをpolicy checkへ移し、runtime behaviorを守るtestは実際のobservation boundaryを観測させる。
- v1の読み取り互換性を維持しながら、新規・意味変更testへmetadata v2を要求する。
- custom agent導入と新gateの有効化を分け、変更自身を審査できないbootstrap循環を避ける。

## Task Boundary

- Task base commit: `f3672ad13d4829e9eb61dc15fc16743f493f4b9b`
- Accepted decision: `docs/adr/0022-two-phase-test-value-review.md`
- Canonical owner:
  - 抽出、schema validation、packet構築、output validation、deterministic aggregationは`skills/review-test-value/scripts/`が所有する。
  - Phaseごとの意味論は`skills/review-test-value/references/`が所有する。
  - model、reasoning effort、role固有の禁止事項は`agents/*.toml`が所有する。独立workerの限定read権限はrunnerが所有し、旧sandbox設定を重ねない。
  - Skillの呼び出し順とfail-closed workflowは`skills/review-test-value/SKILL.md`が所有する。
  - task共通の完了条件は、activation時に`AGENTS.md`へ反映する。
- Authority:
  - task branchのrepository変更、直接検証、通常commitを行う。
  - live `config.toml`の変更、Codex再起動、pushは別のexternal actionとし、実行前に明示確認を得る。

## Accepted Contract

### RTV-201: Phase 1はmetadata以外から意味を補完しない

- Accepted anchor: ADR-0022の「一つのSkill実行を二つのLuna phaseへ分ける」。
- Scope / owner: Phase 1 packet builder、metadata review contract、`test_value_luna` Phase 1。
- Siblings in scope: v1、v2、Git mode、path指定mode、単一record、複数record。
- Failure mode / consumer impact: test sourceやassertion summaryがPhase 1へ漏れ、自己完結していないmetadataが`VALID`になる。
- State transitions / failure timing: extractor成功後、Phase 1 agent起動前のpacket構築時に拒否する。
- Direct verification: Phase 1 packetに`source_text`、source line、assertion summary、oracle本文を混入させるfixtureを拒否し、agent outputのsource evidenceもschema違反にする。
- Independent review trigger: activation前に新規の独立`codex exec`でmetadata-only隔離と実効設定を確認する。
- Gate: ready。

### RTV-202: Phase 1結果を固定したまま全recordのPhase 2を完了する

- Accepted anchor: ADR-0022のPhase 2必須化とfrozen result契約。
- Scope / owner: Phase 2 packet builder、alignment review contract、review result validator。
- Siblings in scope: Phase 1の`VALID`、`REDESIGN`、`NEEDS_CONTEXT`、各phaseの新規独立workerとその失敗経路。
- Failure mode / consumer impact: Phase 1の不合格が本文閲覧後に書き換えられる、または明白なPhase 1不合格を理由にPhase 2が省略され、actual boundaryと保持先を判断できない。
- State transitions / failure timing: Phase 1 validation完了時にhash付きresultを固定し、Phase 2 output validation時に同一性を確認する。
- Direct verification: 全Phase 1 verdictでPhase 2 packetが生成されること、改変したPhase 1 resultとrecord集合、locator、hashの不一致が拒否されることを検証する。
- Independent review trigger: RTV-201と同じsmokeで、独立したPhase 2へのfrozen結果の明示入力と改変拒否を確認する。
- Gate: ready。

### RTV-203: routingはriskの申告漏れでdowngradeされない

- Accepted anchor: ADR-0022のhigh-risk routing契約。
- Scope / owner: metadata v2 validator、親risk context packet、routing policy、deterministic audit selector。
- Siblings in scope: `kind = "security"`、metadata `risk_tags`、親workflowのrisk tags、Luna `NEEDS_CONTEXT / RECHECK`、audit選択。
- Failure mode / consumer impact: authorization、billing、不可逆data lossなどのrecordがmetadataのtag省略だけでSol reviewを迂回する。
- State transitions / failure timing: metadataと親risk contextを検証した後、和集合を作り、Sol起動前にroutingを確定する。
- Direct verification: metadataのみ、親入力のみ、両方、重複、未知tag、locator / hash不一致、空集合を含むtruth tableを検証する。
- Independent review trigger: high-risk routingとfail-closedの契約が複数のagent経路へ波及するため、activation commitをcommit-bound reviewする。
- Gate: ready。

### RTV-204: status、disposition、gateを別々の根拠で決める

- Accepted anchor: ADR-0022の判定分離とdisposition table。
- Scope / owner: result validator、routing policy、deterministic aggregation。
- Siblings in scope: metadata verdict、alignment verdict、deep verdict、actual boundary、lifecycle、artifact state、agent unavailable。
- Failure mode / consumer impact: `ACCEPT`したdeclaration testをそのまま永続testとして完了扱いにする、または`REDESIGN`を理由に保持先が不明なままになる。
- State transitions / failure timing: Phase 1、Phase 2、必要なSol reviewの完了後にstatusとdispositionを決め、artifact stateとresolutionを確認してgateを決める。
- Direct verification: ADR-0022のstatus table、disposition table、record / aggregate gate tableをfixtureへ一対一で投影し、優先順位とinvalid combinationを検証する。
- Independent review trigger: RTV-203と同じactivation reviewで確認する。
- Gate: ready。

### RTV-205: MOVEとDROPは元record消失後もclosureできる

- Accepted anchor: ADR-0021の削除除外とADR-0022のresolution ledger契約。
- Scope / owner: Skill実行中のresolution ledger、aggregate gate validator。
- Siblings in scope: `MOVE_TO_POLICY_CHECK`、`DROP`、surviving record、元test削除、移行先artifact、代替check不要の根拠。
- Failure mode / consumer impact: 元testを消しただけで空のGit selectionを`PASS`とみなし、policy checkへの移行や削除妥当性を検証しない。
- State transitions / failure timing: 初回review結果からrequired resolutionを作り、修正後のGit selectionとdirect check evidenceを対応付け、全resolution完了後にaggregate gateを評価する。
- Direct verification: 元record不在だけでは未解決、移行先だけでは未解決、direct check成功を含む`MOVED`、根拠付き`DROPPED`、hash不一致、未解決entryを検証する。
- Independent review trigger: RTV-203と同じactivation reviewで確認する。
- Gate: ready。

### RTV-206: v1互換とv2強制をexit statusで区別する

- Accepted anchor: ADR-0022のmetadata v2とv1互換契約。
- Scope / owner: marker scanning、metadata schema、output projection、Git selection integration。
- Siblings in scope: path指定modeのv1、Git modeで選択されたv1、未変更v1、v2、v1 / v2混在source、Python、TypeScript、C#。
- Failure mode / consumer impact: deprecation warningだけでpath指定modeがexit `1`になりmigrationできない、または変更v1がwarningだけで新gateを通過する。
- State transitions / failure timing: record binding後にmetadata versionとselection reasonを評価し、warningとerrorを別projectionへ出す。
- Direct verification: 各modeと各言語で`warnings`、`diagnostics`、exit `0 / 1 / 2`、canonical metadata hashを検証する。
- Independent review trigger: RTV-203と同じactivation reviewで確認する。
- Gate: ready。

### RTV-207: required agentを利用できないとき親agentが代行しない

- Accepted anchor: ADR-0022のfail-closedとbootstrap契約。
- Scope / owner: agent TOML、独立worker runner、result validator、明示承認された認証と設定の導入手順。
- Siblings in scope: Luna unavailable、Sol不要、Sol requiredかつunavailable、未検証runtime、親のrouting modeが異なる構成。
- Failure mode / consumer impact: required modelを起動できない環境で別modelまたは親agentが審査し、同じ品質契約を満たしたように報告する。
- State transitions / failure timing: required agentの起動失敗時に`NEEDS_CONTEXT / BLOCKED`へ確定し、review packetを別roleへ送らない。
- Direct verification: unavailable fixture、roleのmodel/effortとworkerの実効権限の照合、各親構成の独立worker smokeを行う。
- Independent review trigger: bootstrap changeとactivation changeをそれぞれcommit-bound reviewする。
- Gate: ready。

## Scope

- `agents/test_value_luna.toml`
- `agents/test_value_sol.toml`
- `config/agents.example.toml`
- `skills/review-test-value/SKILL.md`
- `skills/review-test-value/agents/openai.yaml`
- `skills/review-test-value/references/`のv2 comment format、phase contract、routing、output、review case
- `skills/review-test-value/scripts/`のextractor、packet builder、result validator、routing、対応test
- `AGENTS.md`
- `README.md`
- 必要な場合だけ、role-specific contractを複製せずruntime deltaを保つためのhook smoke test

## Out of Scope

- runtime test collectionと動的生成caseの展開
- 新しいtest frameworkまたは言語adapter
- stable ID、sidecar metadata、repository全体の一括migration
- custom agent以外の`reviewer`、`targeted_reviewer`、`slice_reviewer`の責務変更
- Solによるrepository-wide code review
- merge policyまたはrepository全体のCI gate
- review result cache
- 単一runの結果だけを根拠にしたmodelまたはreasoning effort変更
- live `config.toml`の無断変更、Codex再起動、push

## Implementation Stages

### Bootstrap change

- [x] `test_value_luna`と`test_value_sol`のagent TOMLを追加する。
- [x] metadata、alignment、deep review contractを追加する。
- [x] v1 recordからPhase 1 / Phase 2 packetを作るbuilderを追加する。
- [x] frozen result、agent output、status / disposition / gateを検証するvalidatorを追加する。
- [x] risk context、Sol escalation、disposition、gateのtruth tableを追加する。
- [x] agent unavailableを`NEEDS_CONTEXT / BLOCKED`へ閉じる。
- [x] v1で再現例と二phase regression caseを追加する。
- [x] `config/agents.example.toml`とREADMEへroleを追加する。
- [x] 現行の`review-test-value`契約で変更testを審査する。
- [x] bootstrap commitを固定し、direct checkとcommit-bound reviewを完了する。
- [x] `AGENTS.md`の完了条件はまだ変更しない。

### Runtime activation

- [ ] 同じ独立worker実行に結合された実効model/effort、toolとcontextの検証経路を用意する。
- [ ] 必要な認証やlive設定の変更だけを明示承認後に適用し、結果をread-backする。native registry登録を必須にしない。
- [ ] 新規の独立`codex exec`を各Luna phaseとSolに使い、隔離とfrozen結果の照合をsmoke testする。
- [ ] Sol不要recordでSolを起動しないことを確認する。
- [ ] `RECHECK`、high-risk、audit recordでSolを起動することを確認する。
- [ ] required agent unavailable時に親agentが代行しないことを確認する。
- [ ] activation smokeが失敗した場合はmetadata v2と新gateの有効化へ進まない。

### Bootstrap review follow-up

- [x] 親workflowのrisk tagとaudit率をrouting manifestとは独立したworkflow contextへ固定し、deep packet builderとfinal aggregatorの両方で照合する。
- [x] final aggregatorをrecord集合単位へ変更し、複数recordのalignment、routing、Sol artifactを分割せず集約する。
- [x] required Solが未実行または`NEEDS_CONTEXT`の場合はdisposition計算前に`NEEDS_CONTEXT / null / BLOCKED`へ短絡する。
- [x] 3件の反例を回帰testへ追加し、Git modeの抽出をexit `0`で完了する。
- [x] 修正commitを固定し、元finding familyに限定したcommit-bound reviewを完了する。

### Bootstrap isolation follow-up

- [x] v1 metadataを完全なschemaで検証し、未知fieldをPhase 1 packet生成前に拒否する。
- [x] Phase 1 evidenceをmetadata fieldと定義済みfindingだけを参照する構造へ変更し、source由来の自由文を拒否する。
- [x] 固定済みPhase 1 result全体のhashをalignment packetへ保持し、deep packetとfinal aggregationで元artifactへ照合する。
- [x] canonical deep packet全体のhashへSol resultを結合し、別のPhase 1 resultまたはbounded contextで得た結果の再利用を拒否する。
- [x] source locatorとmetadata hashから`record_id`を再計算し、canonical alignment recordとsource schemaを後段でも検証する。
- [x] runtime activationとmetadata-only isolation smokeが完了するまで、`SKILL.md`とREADMEの実行経路を現行workflowへ戻す。
- [x] 修正commitを固定し、RTV-201、RTV-202、RTV-207のfinding familyに限定したcommit-bound reviewを完了する。

### Metadata v2 and gate activation

- [ ] `@test-value v2`と`fault`、`observable`、optional `impact`、`observation_boundary`を追加する。
- [ ] optional `risk_tags`とephemeral用`remove_when`を追加する。
- [ ] output schema v2で`diagnostics`と`warnings`を分離する。
- [ ] path指定modeのv1をwarning、Git modeで選択されたv1をerrorにする。
- [ ] Python、TypeScript、C#でv1とv2を同じrunへ投影する。
- [ ] MOVE / DROP resolution ledgerとaggregate gateを追加する。
- [ ] 必須回帰caseとdeterministic auditを追加する。
- [ ] `SKILL.md`、`AGENTS.md`、README、Skill UI metadataを新workflowへ更新する。
- [ ] `AGENTS.md`の完了条件を、選択されたtestの`ACCEPT`からSkill実行全体の`gate = PASS`へ変更する。
- [ ] 新しい二phase workflowで変更testを審査する。
- [ ] activation commitを固定し、direct checkとcommit-bound reviewを完了する。

### Operational evaluation

- [ ] Phase 1 `REDESIGN`率、Phase 2 `MISMATCH`率、Sol escalation率、audit disagreement率を複数のrepresentative runで収集する。
- [ ] recordあたりのinput token、latency、agent unavailable率、各disposition率を比較する。
- [ ] cacheまたはSol effort変更が必要な場合は、観測結果と再評価条件を別のADRまたはIssueへ置く。

## Required Regression Cases

- attribute declarationからruntime到達までclaimするrecordは`VALID / MISMATCH / declaration / MOVE_TO_POLICY_CHECK / CHANGES_REQUIRED`になる。
- claimをattribute declarationへ限定すると`VALID / ALIGNED / declaration / MOVE_TO_POLICY_CHECK / CHANGES_REQUIRED`になる。
- 実際のHTTP Host boundaryを実行するrecordは`public-boundary / KEEP_PERMANENT / PASS`候補になる。
- private methodのcall countだけを固定するrecordは`implementation / DROP / CHANGES_REQUIRED`になる。
- `[Authorize]` declarationだけを見るrecordは`MOVE_TO_POLICY_CHECK`になり、未認証requestの拒否までclaimすると`MISMATCH`になる。
- 未認証requestを実際に送り拒否を観測するrecordはSolへ昇格し、`public-boundary / KEEP_PERMANENT`候補になる。
- accepted contractを持たない現在出力のsnapshotは`DROP`になる。
- consumerへ配布されるschema artifactは`public-boundary`、source annotationだけの検査は`declaration`になる。
- characterizationは期限または見直し条件、ephemeralは削除条件がなければ`REDESIGN`になる。
- incident regressionの修正前失敗証拠がない場合は`unverified`へ残し、final判断に必要ならSolへ昇格する。
- Phase 1で本文を必要とするmetadataをPhase 2が救済しない。
- Phase 1 packetへのtest source、source line、assertion summary、oracle本文の混入を拒否する。
- required Lunaまたはrequired Solを起動できない場合は`NEEDS_CONTEXT / BLOCKED`になる。
- 同じcanonical locator bytesとreview contract versionは同じaudit選択結果を返す。
- metadataにrisk tagがなくても、親risk contextのtagでSolへ昇格する。
- `MOVE_TO_POLICY_CHECK`と`DROP`は元recordが消えただけではaggregate `PASS`にならない。
- path指定modeのv1はwarningでexit `0`、Git modeで選択されたv1はerrorでexit `1`になる。

## Validation

Bootstrap changeで次を実行する。

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_packets.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_result_schema.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/build_review_packets.py
python -X utf8 -m py_compile skills/review-test-value/scripts/review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/validate_review_result.py
python -X utf8 <skill-creator>/scripts/quick_validate.py skills/review-test-value
```

Metadata v2 activationでは既存checkと新規checkを実行する。

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values_multilang.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_packets.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_result_schema.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/extract_test_values.py
python -X utf8 -m py_compile skills/review-test-value/scripts/git_diff_selection.py
python -X utf8 -m py_compile skills/review-test-value/scripts/build_review_packets.py
python -X utf8 -m py_compile skills/review-test-value/scripts/review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/validate_review_result.py
python -X utf8 <skill-creator>/scripts/quick_validate.py skills/review-test-value
```

Runtime activationでは次をmanual smokeする。

- `test_value_luna`のPhase 1がmetadata-only schemaを返す。
- frozen Phase 1 resultを別の新規独立workerへ明示入力したPhase 2がalignment schemaを返す。
- Phase 1にはtest source、親履歴、他phaseのartifactを渡さず、直接読取要求も強制拒否する。
- `NEEDS_CONTEXT`、`RECHECK`、high-risk、audit対象、またはbounded contextが必要なrecordだけが`test_value_sol`へ昇格する。
- balanced、spark-first、standard-onlyの各modeでagent TOMLのmodelが維持される。
- required agent unavailable時に親agentが代行せず`BLOCKED`になる。

## Review

- Bootstrap changeとactivation changeは別のcommitとして固定する。
- 各commitについて、immutableなbase commitとreview commitを明示したclean detached worktreeをSessionFolderへ作る。
- Bootstrap reviewはagent contract、packet isolation、frozen result、fail-closedを重点確認する。
- Activation reviewはv1 / v2 migration、risk routing、status / disposition / gate、resolution ledger、aggregate gateを重点確認する。
- finding修正は同じInvariant familyに限定し、修正commit上のdirect checkと元review commitからのresulting deltaに対するtargeted closureで閉じる。complete-diff reviewは再実行しない。

## Risks

- Luna Phase 1のrepository参照は、agent instructionや`read-only` sandboxでは防止できない。履歴非継承とrepository read denyをruntimeで強制し、新session smokeで確認できるまで二段階workflowを有効化しない。
- 同じLuna threadがPhase 2でPhase 1を補正する可能性がある。親側でresultを固定し、Phase 2 schemaへPhase 1 verdictの再出力を持たせない。
- Solがself-containedでないmetadataを追加contextから救済する可能性がある。high-riskまたはaudit対象のPhase 1 `REDESIGN`はSolへ送るが、frozen verdictを変更させずfinal `REDESIGN / CHANGES_REQUIRED`を維持する。それ以外の明白なPhase 1 `REDESIGN`はSolへ送らない。
- declaration checkの移行先が存在しない場合がある。`MOVE_TO_POLICY_CHECK`を`PASS`にせず、移行先とdirect checkをresolution ledgerで要求する。
- 現在のreadiness実装にはworker起動経路がない。bootstrapとactivationを分け、実効境界の検証経路とworkerを実装した後、新規sessionでsmokeを完了する。
- metadataだけではhigh-riskを完全に分類できない。親workflowのrisk contextを和集合にし、metadataからdowngradeできないようにする。
