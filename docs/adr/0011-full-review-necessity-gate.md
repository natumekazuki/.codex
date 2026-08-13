# ADR-0011: complete-diff reviewを具体的な必要性で発火する

- Status: accepted, amended by ADR-0012, partially superseded by ADR-0018
- Date: 2026-08-02
- Amends: ADR-0004, ADR-0005
- Related: ADR-0007, ADR-0008, ADR-0010
- Amended by: ADR-0012 (2026-08-03)

## Amendment

ADR-0012は、`Full-review gate=run`で開始するholistic complete-diff reviewを一つの論理変更につき一度に限定する。`skip`を既定とする本ADRのtrigger判定は最初のholistic reviewを開始する前にだけ適用し、holistic findingによるsource修正や旧Candidateのreview evidence失効を同じ論理変更の再`run` triggerにしない。

## Context

単一ownerかつ低リスクな変更では、通常ターン内のtargeted checkと必要に応じたtargeted reviewで、変更した契約に対する十分な証拠を得られる。一方、PR作成や差分量などを理由に追加のcomplete-diff reviewを常に行うと、同じ論理変更に対するfinding、修正、再reviewが自己目的化し、変更規模とユーザー誘導負荷を増やす。

ただし、high-riskまたはnon-localな境界、複数subsystemやslice間のinteraction、targeted checkでは直接検証できないcross-cutting contractには、独立したholistic reviewが必要な場合がある。追加reviewの必要性を、慣例や不安ではなく現在の変更証拠から判断する基準が必要である。

## Decision

- 独立したcomplete-diff reviewを開始する前に、root sessionが`Full-review gate`を判定する。既定値は`skip`とする。
- `AGENTS.md`または適用されるSkillが独立reviewを明示的に要求する場合、または現在の変更にhigh-risk / non-localな境界、未確認のsubsystem / slice間interaction、targeted checkで直接検証できないcross-cutting contractがある場合だけ`run`とする。
- PR作成依頼、file数、diff量、review回数、finding数、未使用のreviewer、過去に別sessionでfindingが出た事実、holistic findingによるsource修正、旧Candidateのcomplete-diff review evidence失効、または「念のため」は再`run`の根拠にしない。
- gateの判定だけを目的としてreviewerを起動しない。root sessionが`run`または`skip`、その根拠、`run`の場合は対象scopeを報告する。
- `run`と判定したreviewには、ADR-0012が定める単一holistic review、targeted closure、Review Brief、停止条件を適用する。本ADRはhigh-riskまたはnon-localな変更に必要な最初の発見フェーズを弱めない。

## Alternatives

### PR前に常にcomplete-diff reviewを行う

変更を広く確認できるが、既に十分な証拠がある変更にもreviewを重ね、収束しないloopを作りやすいため採用しない。

### complete-diff reviewを行わない

review costは最小になるが、複数境界にまたがるinteractionやhigh-risk contractの見落としを抑えられないため採用しない。

### 軽量なreviewerに追加reviewの必要性を判定させる

判定自体が新しいreview cycleとなり、finding探索を開始する誘因にもなるため採用しない。

### 差分量やfile数で一律に判定する

変更規模はriskやcontractの非局所性を直接表さないため採用しない。

## Consequences

### Positive

- review costを変更リスクと未確認範囲に比例させられる。
- PR作成を起点とする追加review loopを避けられる。
- ユーザーが毎回review要否を指定しなくても、root sessionが根拠付きで判断できる。

### Negative

- gateはroot sessionの判断を必要とし、完全には機械化されない。
- `skip`した変更では、別contextのmodel varianceによってのみ見つかる問題を拾えない可能性がある。

## Policy Anchors

- gateの判定条件と報告: `AGENTS.md`
- high-risk / non-localなCandidate reviewとReview Brief: `skills/contract-closure/SKILL.md`
- reviewerの責務: `agents/reviewer.toml`

本決定に固定文言を検査するexecutable contractは置かない。変更ごとのriskと未確認interactionを入力にする判断であり、静的な文言testは現在の表現を固定するだけになるためである。
