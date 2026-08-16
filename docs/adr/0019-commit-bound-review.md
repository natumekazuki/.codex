# ADR-0019: 独立reviewをGit commitへ固定する

- Status: accepted
- Date: 2026-08-16
- Supersedes: ADR-0006, ADR-0008
- Partially supersedes: ADR-0007, ADR-0011, ADR-0012, ADR-0013, ADR-0018
- Related: ADR-0016

## Context

独立reviewのsourceを固定するため、Candidate snapshotとReview Briefを生成していた。この仕組みは未commitのtracked / untracked content、file mode、digest、review scopeを独自schemaへ写し、Git commitが既に提供する不変なcontent identityを再実装していた。生成、再検証、artifact搬送の手順が実装とreviewより重く、実装branchをreview中に進めにくかった。

reviewの独立性にはexact sourceとcheckの実行対象を固定する必要がある。一方、非Gitまたは未commitのsourceまで同じ保証を提供する要件はない。

## Decision

- exact source stateを必要とする独立reviewは、Git管理されたrepositoryのcommit済みsourceだけを対象とする。非Gitまたは未commitのfallbackは作らない。review必須ならvalidation gapとして停止し、任意ならdirect checkだけで閉じてreview未実施を報告する。
- source identityをimmutableな`baseCommitOid`と`reviewCommitOid`で表す。rootまたはruntimeは`reviewCommitOid`をcheckoutしたcleanなdetached worktreeを`reviewTarget`として用意する。実装branchはreview中も進めてよい。
- `reviewTarget`のrootは、利用可能かつfilesystem authority内のSessionFolderを第一候補とし、`<SessionFolder>/review-worktrees/<repositoryId>/<reviewCommitOid>`へ固定する。SessionFolderがない場合だけ、repository内でgitignore済みの`.agent-worktrees/reviews/<reviewCommitOid>`へfallbackする。Codex設定ディレクトリやOSのTEMPへ暗黙にfallbackしない。
- reviewerは明示された`reviewTarget`だけを読み、substantive review前にHEAD一致、tracked / untrackedのcleanliness、commit objectの存在、base ancestryをread-onlyで検証する。
- review contextはrootのtask messageで渡す。必須情報はreview targetと両OID、included / excluded scope、accepted contractとInvariant、`executedOnCommitOid`付きcheck、review triggerまたはlens、有限のdeadlineとする。
- check evidenceを`executedOnCommitOid`へ固定し、別commitへ付け替えない。commit Aのholistic resultはAへ固定する。finding修正commit BはB上のdirect checkとA..Bのfinding family / resulting deltaに限定したtargeted closureで閉じ、holistic reviewを再実行しない。
- 別semantic ownerの後続変更は別の論理変更へ分ける。
- Candidate snapshot、Review Brief builderとそのexecutable contractを削除する。`contract-closure`はaccepted contract、Invariant、Closure Map、Sibling Sweep、Finding Promotion、review triggerとclosureだけを所有する。
- `consolidate-structure` Skillを削除する。semantic ownerの分散、独立責務の混在、canonical boundaryの迂回、decisionの重複、test couplingは標準実装workflowで必要な場合だけ扱う。
- review kind別の`reviewer`、`targeted_reviewer`、`slice_reviewer`は維持し、commit-bound inputとread-only preflightをrole contractへ含める。
- review用branchは作らない。全reviewerの終了後、rootまたはruntimeは正規化済みpath、HEAD、tracked / untrackedのcleanlinessを検証し、一致したworktreeだけを`git worktree remove`で削除する。不一致またはdirty stateを`--force`で削除せずvalidation gapとして報告し、実装branchとreview対象commitは削除しない。
- change / build / fix依頼はtask / feature branchへの通常の追加commitを許可する。default / main / protected branchへのcommit、amend / rebase / resetなどの履歴改変、pushには明示確認を要求する。commit前にstatusと対象diffを確認し、対象pathまたはhunkだけをstageして既存のstaged変更を保護する。

## Alternatives

- Candidate snapshotとReview Briefを残す: 非commit sourceも固定できるが、独自identity、schema、artifact搬送の保守負担が残るため採用しない。
- 非Git向けsnapshot backendだけ残す: 対応範囲は広がるが、利用要件のない別identity実装を維持することになるため採用しない。
- shared worktreeまたはbranch tipをreviewする: 実装継続でsourceが変わり、file readとdiffの対象がずれるため採用しない。
- OSのTEMPまたはCodex設定ディレクトリへ暗黙に作る: Session境界とfilesystem authorityが不明瞭になり、残存worktreeを安全に識別しにくいため採用しない。
- commitごとに明示確認を求める: authority境界は狭いが、review sourceを作るたびに作業を停止するため採用しない。

## Consequences

- Positive: Git objectがsource identityを所有し、独自snapshotとschemaを保守しなくてよい。
- Positive: detached review worktreeと実装branchを分離し、review中も次のcommitへ進める。
- Positive: review worktreeのrootと終了時cleanupが決定的になり、SessionFolder利用時はrepository外の一時資源として分離できる。
- Positive: check、holistic result、repair closureの対象commitが追跡できる。
- Negative: Git未管理または未commitのsourceではexact-source reviewを完了できない。
- Negative: rootまたはruntimeがdetached worktreeの安全なpath解決、作成、全終了経路での後始末を担う。
- Negative: review lifecycleとpreflightは自然言語policyであり、runtimeによる機械的な強制はない。

## Policy Anchors

- Standard workflow, review lifecycle, and authority: `AGENTS.md`
- Contract reasoning and finding promotion: `skills/contract-closure/SKILL.md`
- Review role contracts: `agents/reviewer.toml`、`agents/targeted_reviewer.toml`、`agents/slice_reviewer.toml`
- Workspace boundary: `docs/architecture/subagent-workspace.md`
