# ADR-0013: review kindごとにsubagent roleとrouting責務を分離する

- Status: accepted
- Date: 2026-08-03
- Amends: ADR-0004, ADR-0007, ADR-0012
- Related: ADR-0008, ADR-0011

## Context

ADR-0007は初期導入としてtargeted review、specialist review、holistic reviewを単一の`reviewer` roleへreview kind付きで渡し、観点混在や証拠誤帰属が実運用で確認された場合に専用roleを検討するとした。ADR-0012はholistic complete-diff reviewを一つの論理変更につき一度に限定し、finding修正後はfinding familyとresulting deltaのtargeted closureで閉じると決定した。

単一roleにはcomplete diffから新しいfinding familyを探索する責務と、指定slice、lens、finding familyだけを反証する責務が併存していた。Review Briefでscopeを限定しても、静的role契約がcomplete diff探索を許すため、targeted closureからholistic探索へ広がる余地が残った。plannerにも`non-trivial`または`final review`を理由に`reviewer`を選択する表現があり、root sessionの`Full-review gate`を迂回し得た。

一方、routing hookはSpark modeとquota fallbackのcontextだけを注入し、review kind、回数、deadline、finding closureを制御していない。role分割のためにreview lifecycleをhookへ移すと、repository policy、role契約、runtime routingの正本が分散する。

## Decision

- `agents/reviewer.toml`をholistic complete-diff review専用roleとする。root sessionが`Full-review gate=run`と判定した場合だけ、一つの論理変更につき一度選択できる。
- `agents/targeted_reviewer.toml`を追加し、完了sliceのtargeted review、指定lensとInvariant Matrix cellのspecialist review、finding familyとresulting deltaのtargeted closureを担当させる。
- `reviewer`と`targeted_reviewer`は共通のfinding分類契約に従う。`risk-candidate`を提案する場合は、root sessionがrisk acceptanceを判定できるよう、発生条件と可能性、影響、検知可能性、復旧可能性、follow-upの要否をfindingへ含める。
- `targeted_reviewer`はcomplete diff、無関係なfinding family、一般的なhardeningを再探索せず、holistic reviewを要求または自動開始しない。scope変更が必要ならroot sessionへ境界を返す。
- specialist reviewはlensごとの専用roleを増やさず、`targeted_reviewer`へ一つのlensと担当matrix cellを割り当てる。同じlensへ複数reviewerを重ねない。
- `fast_reviewer`は小規模、局所的、低リスクなsanity checkに限定し、`contract-closure`が要求する独立review、高リスクなtargeted review、specialist review、holistic reviewの代用にしない。
- plannerはreview kind、scope、具体的trigger、前提check、有限のdeadlineを計画へ含める。`Full-review gate=run`だけが`reviewer`を選択でき、targeted review、specialist review、targeted closureは`targeted_reviewer`を選択する。file数、diff量、finding数、`non-trivial`、`final review`、未使用のreviewer、または「念のため」を選択理由にしない。
- Candidate-bound reviewでは、root sessionが`Candidate preflight`を完了してからReview Briefを発行する。どちらのreview roleも、宣言済みread-only verification recipeによるsource identityの独立検証を省略しない。roleはCandidate形式を設計または修復しない。
- `targeted_reviewer`を端末固有の`config.toml`と配布用の`config/agents.example.toml`へstandard roleとして登録する。`standard-only` modeでは通常のstandard roleとして選択でき、`fast_reviewer`はユーザーがexact roleを明示した場合以外に自動選択しない。
- `hooks/subagent-routing.ps1`はruntime modeとSpark fallback contextだけを所有し、review kind、review回数、finding closure、deadline超過後の再投入を所有しない。新roleを阻害またはremapしないことをrouting testで検証できるため、hook本体は変更しない。
- review lifecycle、review回数、Candidate Definition、Review Brief、deadline、Finding Promotion、完了条件はADR-0012、`AGENTS.md`、`skills/contract-closure/SKILL.md`の既存契約を維持する。

## Alternatives

- 単一`reviewer`へreview kind別の条件分岐を追加する: role数は増えないが、complete diff探索と限定closureの相反する責務が同じ静的契約へ残るため採用しない。
- domainまたはlensごとにreviewer roleを追加する: 個別最適化できるが、lens数に応じてrole、config、routing、reviewer数が増え、同じlensへの重複reviewを招くため採用しない。
- review kindと回数をhookで機械制御する: runtimeで強制できるが、現在のhook責務を越えてreview lifecycleの正本を分散するため採用しない。
- `targeted_reviewer`のCandidate検証をrootのpreflightで置き換える: 異なるsource stateまたはReview Briefを受け取った場合の独立検出境界を失うため採用しない。

## Consequences

- Positive: holistic discoveryとtargeted closureのscopeが静的role契約でも分離され、targeted reviewからcomplete diff再探索へ広がりにくくなる。
- Positive: plannerとroot sessionが具体的なgateまたはtriggerからreview kindを選択し、`Full-review gate`を迂回しにくくなる。
- Positive: specialist lensは一つのtargeted roleへ集約したまま、担当cellと未確認cellをReview Briefで限定できる。
- Positive: hookはruntime routing、role定義は静的責務、`AGENTS.md`と`contract-closure`はreview lifecycleという正本境界を維持する。
- Negative: role登録変更は現在実行中のsessionへ反映されない場合があり、新しいsessionでのrole discovery確認が必要になる。
- Negative: role選択とReview Briefのscope指定は自然言語policyであり、review lifecycleを強制するruntimeは持たない。

## Policy Anchors

- Review lifecycle and role selection: `AGENTS.md`
- Candidate Definition, Candidate preflight, Evidence Ledger, Review Brief, and finding closure: `skills/contract-closure/SKILL.md`
- Holistic reviewer contract: `agents/reviewer.toml`
- Targeted, specialist, and closure reviewer contract: `agents/targeted_reviewer.toml`
- Low-risk sanity reviewer contract: `agents/fast_reviewer.toml`
- Planner routing contract: `agents/planner.toml`, `agents/fast_planner.toml`
- Role registration: `config/agents.example.toml`、端末固有の`config.toml`
- Runtime mode and Spark fallback: `hooks/subagent-routing.ps1`
- Routing executable contract: `hooks/test-subagent-routing.ps1`
