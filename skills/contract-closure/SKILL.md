---
name: contract-closure
description: 境界、public API、永続化、migration、外部副作用、認可、並行処理、resource limit、owner / scope、複合不変条件を変更・修正・reviewするとき、accepted contractと不変条件を兄弟入口、状態遷移、failure timing、aggregate scopeへ展開し、直接検証と独立した反証reviewで閉じる。review findingを同じ不変条件familyへ限定して修正し、再発を防ぐときにも使う。
---

# Contract Closure

局所修正だけでは閉じない契約変更に使う。標準workflow、authority、role routing、reportingは`AGENTS.md`を正本とし、このSkillでは再定義しない。

## Trigger

次のいずれかを変更、修正、reviewする場合に使う。

- public API、protocol、schema、永続化、migration
- 外部副作用、認可、security、並行処理、resource limit
- owner / scope、複数fieldで成り立つ不変条件
- 同じfailure modeが複数入口、状態遷移、subsystemへ波及する変更

pure refactor、局所的な機械変更、文言変更、targeted checkがaccepted contractを直接検証できる単一責務の変更には使わない。

## Pre-Implementation Closure Plan

sourceまたはexecutable contractを編集する前に、task-localに次を固定する。

```markdown
Invariant ID: <stable task-local id>
Accepted contract / exact anchor: <requirement, API, schema, ADR, external consumer, executable contract>
Scope / semantic owner: <owned boundary and supported siblings>
Failure mode / consumer impact: <observable violation>
State transitions / failure timing: <relevant phases>
Direct verification: <check that observes the failure>
Independent review trigger: <specific high-risk or unverified interaction, or none>
Gate: ready / unresolved
```

- exact anchorはfileの存在ではなく、契約上の意味まで記す。
- 現在のsourceやtestがあることだけをaccepted contractの根拠にしない。
- 契約根拠が不足または競合し、選択がconsumerの結果を変える場合は`unresolved`として編集を止める。根拠、選択肢、影響、推奨案を示してユーザーへ確認する。
- 情報が揃う場合は承認待ちにせず`ready`まで整理する。
- 実装中にcontract、scope、owner、consumer、failure modeが変わった場合は同じInvariant IDで再判定する。新しい契約軸をreviewだけへ追加しない。

## Closure Map

`references/trigger-matrices.md`から変更に該当する節だけを選び、一般チェックリストではなく反証可能な問いへ変換する。

最低限、次のchannelを必要な範囲で展開する。

- entry point: public、raw、internal、batch、retry、recovery
- state transition: create、load、update、delete、abort、restart
- failure timing: validation前、side effect前、commit後、response loss、cleanup
- scope: item、batch、owner、session、process、storage全体
- projection: public response、summary、audit、error、generated client
- coupled value: owner / permission、provider / revision / model、status / run stateなど

```markdown
## Closure Map
- Invariant ID: <id>
- Accepted anchor and meaning: <anchor>
- Canonical owner: <boundary>
- Siblings in scope: <entries, transitions, projections, aggregate scopes>
- Excluded siblings and reason: <not in supported scope>
- Failure points: <timing and observable impact>
- Direct checks: <check per material failure mode>
- Independent review lens: <only when triggered>
```

兄弟channelを除外する場合は「今回は触っていない」ではなく、同じInvariant familyまたはsupported scopeに属さない理由を書く。

## Executable Contract and Direct Check

- failure mode、consumer影響、契約を所有する最小の安定境界を決める。
- 費用対効果が合う場合はtest、type、schema、static checkを先に追加または更新する。現在実装の表現を固定するだけのtestは作らない。
- bug fixは修正前の失敗と修正後の解消を最も直接的な方法で確認する。
- 永続化や副作用では、validation前、commit直前、commit後、response loss、retry、recoveryを区別する。
- 複合値は各field単独ではなくtupleとして検証し、create、load、update、clone、migration、fallback、public projectionへ同じ規則が届くか確認する。

## Sibling Sweep

実装後、同じInvariant familyとsemantic ownerに属する兄弟入口を検索する。

- caller側の個別回避より、共有境界で直すべきかを先に判断する。
- source、test、type、schema、validator、migration、projection、error mappingのうち、同じ契約を持つchannelだけを対象にする。
- 別ownerまたは別subsystemへ自動展開しない。必要ならFinding Promotionの`boundary prerequisite`として分ける。
- 検索語、確認した兄弟、除外理由、追加checkをtask-localに残す。

## Independent Closure Review

独立reviewは、高リスク境界、複数入口やsubsystemへの波及、またはtargeted checkで直接検証できない具体的なinteractionがある場合だけ行う。

- `AGENTS.md`が選んだ独立reviewerへ、Invariant ID、accepted anchor、included / excluded scope、Closure Map、実行済みcheck、割り当てるlens、有限deadlineを渡す。
- 1から3個の独立lensが必要な場合は、同じsource stateに対して1 lensにつき1 reviewerを割り当てる。同じlensへ複数reviewerを重ねない。
- localで単一責務かつdirect checkが契約を直接検証する変更にはreviewを追加しない。
- runtimeがagent間のartifact transport、deadline、partial result回収を提供しない場合、ユーザーへ手動搬送を要求せずvalidation gapとして扱う。

### Exact source state helper

high-riskまたはnon-localな同一review cycleでexact source stateの固定が必要な場合だけ、次のhelperを使う。

```powershell
python skills/contract-closure/scripts/candidate_snapshot.py create --candidate-id <id> --target <repo> --base-ref <ref> --include . --mode manifest-digest --artifact-dir <artifact-dir> --output <candidate.json>
python skills/contract-closure/scripts/candidate_snapshot.py verify --candidate <candidate.json>
python skills/contract-closure/scripts/review_brief.py --input <brief-input.json> --output <review-brief.json>
```

- Candidate snapshotとReview Briefのschema、digest、path encoding、read-only verification recipe、必須fieldはscriptsとtestsを唯一の正本とする。自然言語でfieldを再構築または補完しない。
- Candidateはsource stateだけを識別する一時artifactであり、review cycle、session expiry、review contract freshnessを証明しない。runtimeがcycle bindingを提供しない環境では、その不足をvalidation gapとして扱い、session handoff、作業再開、commit後、別branch、merge後の正本やcurrent review evidenceにしない。commit後のidentityはcommit OIDまたはtree OIDが所有する。
- helperは通常のGit indexを変更しない。reviewerはCandidateをread-onlyで検証し、`verified`の場合だけsubstantive reviewへ進む。
- sourceまたはreview contractが変わった場合はcurrent stateから再生成する。旧review resultを新Candidateのcurrent evidenceとして移し替えない。
- checkとreview結果はtask-localな実行記録として扱い、恒久的なEvidence Ledgerやuser-facing field一覧を要求しない。

## Finding Promotion

review findingをseverityだけで処理せず、sourceを広げる前に次を判定する。

1. accepted contractまたは明示された安全境界との関係
2. supported scopeでの現実的な到達条件
3. consumerへの具体的な影響
4. 同じInvariant familyとsemantic ownerに属する修正範囲

Disposition:

- `investigation-pending`: 契約関係または到達性の証拠が不足している。追加調査まで最終分類を保留する。
- `accepted risk`: 到達可能な契約違反だが、`AGENTS.md`のrisk acceptance条件を満たす。source scopeを広げない。
- `current-scope repair`: 同じInvariant family、supported scope、semantic ownerに属する。必要な兄弟channelへ限定して修正する。
- `boundary prerequisite`: 別ownerまたは別subsystemの先行変更が必要。独立した論理変更へ分ける。
- `hardening follow-up`: 現在のaccepted contract違反ではないが、反証可能な将来仮説と再調査条件がある。current sourceへ混ぜない。
- `dismissed`: source、contract、到達証拠に照らして成立しない。

`current-scope repair`は、元のdirect check、finding familyとresulting deltaに限定したtargeted closure、影響する兄弟channelの再確認で閉じる。同じscopeの探索reviewまたはcomplete-diff reviewを再開しない。

## Completion

次を満たしたときだけclosure完了とする。

- Pre-Implementation Closure Planが`ready`で、Invariant IDとfailure modeが実装、check、reviewへ同じ意味で引き継がれた。
- accepted contract、source、executable contractが整合している。
- materialな兄弟入口、状態遷移、failure timing、aggregate scope、projectionを確認した。
- direct checkが現行差分に対して成功している。
- triggerされた独立reviewが完了し、未解決blocking findingがない。
- validation gap、accepted risk、未確認channel、残リスクが区別されている。

Skill自体の更新後は、少なくとも次を実行する。

```powershell
python skills/contract-closure/scripts/test_candidate_snapshot.py
python skills/contract-closure/scripts/test_review_brief.py
python skills/contract-closure/scripts/candidate_snapshot.py verify --candidate <candidate.json>
python -X utf8 <skill-creator>/scripts/quick_validate.py skills/contract-closure
```
