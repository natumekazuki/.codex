# ADR-0012: holistic reviewを一度に限定しfindingをtargeted closureで閉じる

- Status: accepted, amended by ADR-0013, partially superseded by ADR-0018
- Date: 2026-08-03
- Amends: ADR-0004, ADR-0007, ADR-0011
- Related: ADR-0008, ADR-0010
- Amended by: ADR-0013 (2026-08-03)

## Amendment

ADR-0013は、ここで分離したholistic discoveryとtargeted closureを静的roleにも反映し、`agents/reviewer.toml`をholistic専用、`agents/targeted_reviewer.toml`をtargeted review、specialist review、targeted closure専用とする。review回数、Candidate、Review Brief、deadline、完了条件は変更しない。

## Context

ADR-0004は、統合後のcomplete-diff reviewで`blocking` findingを修正した場合にfresh-context full-diff closure reviewを要求し、条件付きで一つの論理変更につき3回までfull-diff reviewを認めた。ADR-0007はspecialist reviewの証拠を同じCandidateへ揃えた後にholistic complete-diff reviewを要求し、ADR-0011はcomplete-diff reviewの必要性を`Full-review gate`で判定した。

fresh-context reviewerは修正確認に限定されず、更新後diff全体から新しい反例を探索する。このため、一つのfull-diff reviewで見つかったfindingを閉じた後も、次のfull-diff reviewが別familyのfindingを発見し、Candidate更新とreviewが連鎖する。回数上限は無限反復を止めるが、複数回の全量探索を通常の収束経路として利用できる。

complete-diff reviewには、統合後のinteractionとcross-cutting contractから未知の問題を発見する役割を持たせる。発見済みfindingの修正確認は、対象familyと修正deltaへ限定したreviewへ分離する必要がある。

## Decision

- `Full-review gate`の既定値は`skip`のまま維持する。`run`の場合も、holistic complete-diff reviewは一つの論理変更につき一度だけ行う。
- holistic reviewは、slice間interaction、cross-cutting contract、specialist lensで未確認の組合せを対象とする最終的な発見フェーズとする。holistic review後に更新後diff全体を新規探索するfresh-context full-diff closure reviewは行わない。
- holistic review entryは実行したCandidateに紐づくimmutableなreview resultとして保持し、同じ論理変更で発見フェーズを実施済みであることをreview-cycle stateへ記録する。source修正後のCandidateへ`current` evidenceとして再関連付けせず、最終Candidate全体の正しさを示すcompletion evidenceにも使わない。
- reviewable sliceのtargeted reviewは、後続sliceの前提、高リスク境界、または独立した反例探索の具体的な便益がある場合だけ一度行う。`blocking` findingを修正した場合は、同じfinding familyとresulting deltaに限定したtargeted closureを一度行う。
- holistic reviewのfindingにはFinding Promotionを適用する。`current-scope repair`だけを同じfamilyへ必要な範囲で修正し、direct checkと対象family、resulting deltaのtargeted closureで閉じる。targeted closure reviewerはcomplete diffを新規探索しない。
- source修正後の最終Candidateは、現行sourceを対象とするdirect check、対象family / resulting deltaのtargeted closure、影響を受けるspecialist cellの現行証拠をFinal Candidate closure chainへ揃えて閉じる。旧holistic entryのreview-cycle recordと最終Candidateのclosure evidenceを分けて報告する。
- targeted closureでも同じ`blocking` familyが閉じない場合はreviewを反復せず、要求、設計、責務境界、accepted contract、またはユーザー判断へ戻る。
- `boundary prerequisite`は別のaccepted contractを持つ論理変更へ分ける。holistic findingの修正が新しいpublic contract、semantic owner、subsystem、永続化、認可、外部副作用、並行処理へscopeを拡張する場合も、現在の論理変更で二度目のfull-diff reviewへ進まない。
- auth bypass、secretまたはpersonal dataの露出、現実的なinjection、不可逆なdata lossを偶発的に確認した場合は、targeted closureのscope外でも報告する。root sessionがFinding Promotionを適用する前にsource scopeを自動拡張せず、review回数を理由に完了扱いしない。
- reviewerへ渡す入力一式を`Review Brief`と呼ぶ。旧称はSession Handoffと混同しやすいため、active policyでは使用しない。
- root sessionはreviewer起動前にCandidate Definition、source identity、review contract、確認recipeを決定的なローカルcheckで検証し、`Candidate preflight`として記録する。`Candidate preflight=verified`の場合だけReview Briefを発行できる。
- `Candidate preflight`と、reviewerがread-only verification recipeを独立に実行して返す`Candidate verification result`を区別する。rootの事前検証を理由にreviewerの独立検証を省略しない。
- source identityまたはreview contractを変更した場合は新Candidateを発行する。deadline、Review Entry ID、transport指定などReview Briefのenvelopeだけを修正した場合はCandidateを維持し、Review Briefだけを再検証する。
- Review Briefには有限のdeadlineを必須とする。deadlineを超えたreviewerは一度interruptし、同じreviewを別reviewerへ自動再投入しない。取得済みの部分結果は採用可能なevidenceとvalidation gapへ分け、完了条件を満たさなければユーザー判断へ戻る。
- reviewの再試行は、toolまたはtransport failureによってreview evidenceを取得できず、同じCandidateとreview contractを維持できる場合に限る。finding数、deadline超過、または「念のため」を再試行理由にしない。
- 完了には、現行sourceを対象とするcheck、未解決の`blocking` findingがないこと、`current-scope repair`のdirect checkとtargeted closure、その他のfindingとvalidation gapの分類を要求する。review回数を使い切ったことを完了理由にしない。

## Alternatives

- blocking修正後にfresh-context full-diff reviewを行う: 修正外の新しい反例を探索できるが、finding closureと新規発見が同じreviewへ混ざり、review cycleが再び開くため採用しない。
- full-diff reviewを複数回許可し、回数上限だけを下げる: 実行時間は減るが、残り回数がreview予算として働く構造を解消しないため採用しない。
- holistic findingをroot sessionのdirect checkだけで閉じる: 実行コストは低いが、高リスクなfinding familyの修正deltaに対する独立した反証を失うため採用しない。
- reviewerのCandidate検証をrootの事前検証で置き換える: reviewerが異なるsource stateやReview Briefを受け取った場合の検出境界を失うため採用しない。
- reviewを常に省略する: slice間interactionとcross-cutting contractを独立に確認できないため採用しない。

## Consequences

- Positive: complete-diff reviewを新規発見、targeted closureを修正確認へ分離し、一つの論理変更で全量探索が連鎖しない。
- Positive: finding familyとresulting deltaだけを再確認するため、確認済みscopeがmodel varianceで繰り返し開かれにくい。
- Positive: Candidate形式の不備をreviewerとの往復前に検出し、reviewerは反例探索へ集中できる。
- Positive: deadline超過を追加reviewの契機にせず、validation gapまたはユーザー判断として停止できる。
- Negative: holistic review後に修正外の未知のfindingを追加探索する機会は減る。
- Negative: root sessionはReview Briefのscope、Candidate preflight、deadline、再試行理由を明示的に管理する必要がある。
- Negative: 現在のreview lifecycleは自然言語policyであり、deadlineやreview回数を機械的に強制するruntimeは持たない。
- Follow-up: reviewer roleの分割、routing、config登録、deadlineの共通既定値、review cycleを機械制御するruntimeは、実運用の必要性を確認した後に別の論理変更で扱う。

## Policy Anchors

- Lifecycle and completion gates: `AGENTS.md`
- Candidate Definition, Candidate preflight, Evidence Ledger, Review Brief, targeted closure: `skills/contract-closure/SKILL.md`
- Reviewer input and output contract: `agents/reviewer.toml`, `agents/targeted_reviewer.toml`
- Current reporting policy: `AGENTS.md`
- Runtime executable contract: なし。review cycleを機械制御するruntimeを導入する場合は、その状態遷移を別のexecutable contractとして追加する。
