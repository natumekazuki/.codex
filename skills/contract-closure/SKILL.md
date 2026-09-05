---
name: contract-closure
description: 境界、public API、永続化、migration、外部副作用、認可、並行処理、resource limit、owner / scope、複合不変条件を変更・修正・reviewするとき、accepted contractと不変条件を兄弟入口、状態遷移、failure timing、aggregate scopeへ展開し、直接検証と必要なcommit-bound反証reviewで閉じる。review findingを同じ不変条件familyへ限定して修正し、再発を防ぐときにも使う。
---

# Contract Closure

局所修正だけでは閉じない契約変更に使う。標準workflow、authority、role routing、reportingは`AGENTS.md`を正本とし、ここでは再定義しない。

## Closure Planを固定する

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

- exact anchorにはfile名だけでなく契約上の意味を含める。
- 現在のsourceやtestがあることだけをaccepted contractの根拠にしない。
- 契約根拠が不足または競合し、選択がconsumerの結果を変える場合は`unresolved`として編集を止める。根拠、選択肢、影響、推奨案を示してユーザーへ確認する。
- 実装中にcontract、scope、owner、consumer、failure modeが変わった場合は、同じInvariant IDで再判定する。新しい契約軸をreviewだけへ追加しない。

## Closure Mapを展開する

`references/trigger-matrices.md`から変更に該当する節だけを選び、反証可能な問いへ変換する。

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

必要な範囲でentry point、state transition、failure timing、aggregate scope、projection、coupled valueを展開する。兄弟channelを除外する場合は、同じInvariant familyまたはsupported scopeに属さない理由を書く。

## Direct Checkを設計する

- failure mode、consumer影響、契約を所有する最小の安定境界を決める。
- test、type、schema、static checkのうち、failureを最も直接観測する手段を選ぶ。
- 永続化や副作用では、validation前、commit直前、commit後、response loss、retry、recoveryを区別する。
- 複合値はfield単独ではなくtupleとして検証し、create、load、update、clone、migration、fallback、public projectionへ同じ規則を届かせる。

## Sibling Sweepを行う

実装後、同じInvariant familyとsemantic ownerに属する兄弟入口を検索する。

- caller側の個別回避より、共有境界で直すべきかを先に判断する。
- source、test、type、schema、validator、migration、projection、error mappingのうち、同じ契約を持つchannelだけを対象にする。
- 別ownerまたは別subsystemへ自動展開しない。必要ならFinding Promotionの`boundary prerequisite`として分ける。
- 検索語、確認した兄弟、除外理由、追加checkをtask-localに残す。

## 必要な独立reviewを閉じる

高リスク境界、複数入口やsubsystemへの波及、またはtargeted checkで直接検証できない具体的なinteractionがある場合だけ独立reviewを行う。localで単一責務かつdirect checkが契約を直接検証する変更には追加しない。

- exact source stateを必要とするreviewは、Git管理されたrepositoryのcommit済みsourceだけで行う。非Gitまたは未commitのsourceへsnapshot fallbackを作らない。review必須ならvalidation gap、任意ならdirect checkのみとして扱う。
- rootまたはruntimeに、immutableな`baseCommitOid`と`reviewCommitOid`を固定させ、`reviewCommitOid`をcheckoutしたcleanなdetached worktreeを`reviewTarget`として用意させる。実装branchはreview中も進めてよい。
- `reviewTarget`はfilesystem authority内の`<SessionFolder>/review-worktrees/<repositoryId>/<reviewCommitOid>`へ配置する。SessionFolderがない場合だけ、repository内でgitignore済みの`.agent-worktrees/reviews/<reviewCommitOid>`を使う。Codex設定directoryやOS TEMPへ代替review rootを作らない。どちらも使えなければvalidation gapとする。
- review用branchは作らない。rootまたはruntimeが作成と後始末を所有し、全reviewerがapprove、finding、validation gap、deadline、interruptのいずれかで終了してから、正規化済みpathが選択root配下にあり、HEADが`reviewCommitOid`、tracked / untrackedともcleanであることを確認して`git worktree remove`する。不一致では`--force`を使わず残存worktreeをvalidation gapとして報告する。実装branchとreview対象commitは削除しない。
- review task messageへ`reviewTarget`、両OID、included / excluded scope、accepted contractとInvariant、`executedOnCommitOid`付きの実行済みcheck、割り当てるlensまたはtrigger、有限のdeadlineを含める。
- reviewerに、明示されたtargetでHEAD一致、tracked / untrackedのcleanliness、commit objectの存在、base ancestryをread-onlyで確認させる。preflightが失敗した場合はsubstantive reviewを行わずvalidation gapを返させる。
- checkとreview結果を対象commitへ固定する。commit Aのholistic resultを修正commit Bへ付け替えない。B上のdirect checkとA..Bのfinding family / resulting deltaに限定したtargeted closureで閉じ、holistic reviewを再実行しない。
- 別semantic ownerまたは別subsystemの後続変更を同じreview済みscopeへ混ぜず、別の論理変更へ分ける。

## Findingの分類と受容

- findingはaccepted contract、到達条件、consumer影響、Invariant familyの根拠から`blocking`、`risk-candidate`、`non-material`、`invalid`へ分類する。証拠不足は`investigation-pending`とし、source scopeを先に広げない。
- `risk-candidate`は、発生可能性が低く、影響が限定され、自動検知と復旧ができ、機密性侵害または不可逆なdata lossを伴わない場合だけaccepted riskにできる。必要なfollow-upはrepositoryの既存管理表へ残す。
- auth bypass、secretやpersonal dataの露出、現実的なinjection、不可逆なdata lossを自動でrisk acceptanceしない。

## Finding Promotionを適用する

review findingをseverityだけで処理せず、sourceを広げる前に次を判定する。

1. accepted contractまたは明示された安全境界との関係
2. supported scopeでの現実的な到達条件
3. consumerへの具体的な影響
4. 同じInvariant familyとsemantic ownerに属する修正範囲

Disposition:

- `investigation-pending`: 契約関係または到達性の証拠が不足している。
- `accepted risk`: 到達可能な契約違反だが、上記のrisk acceptance条件を満たす。
- `current-scope repair`: 同じInvariant family、supported scope、semantic ownerに属する。
- `boundary prerequisite`: 別ownerまたは別subsystemの先行変更が必要である。
- `hardening follow-up`: 現在のaccepted contract違反ではないが、反証可能な将来仮説と再調査条件がある。
- `dismissed`: source、contract、到達証拠に照らして成立しない。

`current-scope repair`は、元のdirect check、finding familyとresulting deltaに限定したtargeted closure、影響する兄弟channelの再確認で閉じる。同じscopeの探索reviewまたはcomplete-diff reviewを再開しない。

## Completion

次を満たしたときだけclosure完了とする。

- Closure Planが`ready`で、Invariant IDとfailure modeが実装、check、reviewへ同じ意味で引き継がれている。
- accepted contract、source、executable contractが整合している。
- materialな兄弟入口、状態遷移、failure timing、aggregate scope、projectionを確認している。
- direct checkが現行sourceに対して成功している。独立reviewへ渡すcheck evidenceは、対象の`executedOnCommitOid`で成功している。
- triggerされた独立reviewが完了し、未解決blocking findingがない。
- validation gap、accepted risk、未確認channel、残リスクを区別している。

Skill自体を更新した場合は、次を実行する。

```powershell
python -X utf8 <skill-creator>/scripts/quick_validate.py skills/contract-closure
```
