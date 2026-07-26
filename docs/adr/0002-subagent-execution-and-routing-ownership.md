# ADR-0002: subagent の実行境界と routing 所有権を分離する

- Status: accepted
- Date: 2026-07-13
- Supersedes: none

## Context

- 全 child に repo 内の `result.md` を要求する運用は、read-only role と両立せず、軽量な調査や検証でも task 文書を増やす
- root session だけが正本を編集する規則は、workspace-write の implementer が割り当て範囲を直接編集する実行モデルと矛盾する
- hook と `agents/*.toml` の両方が role の責務、禁止事項、出力契約を定義すると、変更時に drift が発生する
- shared working tree、task worktree、親子間メッセージには異なる利点があり、作業ごとに適切な境界を選ぶ必要がある

## Decision

- 通常の親子間返却には subagent の最終メッセージを使い、repo artifact を必須にしない
- workspace-write の child は、root session が割り当てた非重複範囲を shared working tree で編集できる
- root session は scope、競合回避、成果の採否、knowledge placement、統合、最終検証、commit、user-facing final を所有する
- task worktree は、競合する並列編集、破壊的または大規模な試行、隔離が必要な検証で root session が明示的に選ぶ escape hatch とする
- `agents/*.toml` を静的な role 契約の正本とし、hook は現在の Spark mode と quota fallback など runtime delta だけを注入する
- child の一時的な調査・設計結果は採用候補として扱い、恒久 artifact への配置は root session が ADR-0001 に従って判断する

## Alternatives

- 全 child に task workspace と `result.md` を要求する: read-only role と矛盾し、作業結果を恒久文書へ過剰保存するため採用しない
- すべての child を task worktree で隔離する: 競合回避には強いが、局所的な変更でも統合コストが増えるため採用しない
- root session だけが編集する: 実装 delegation の利点が失われ、workspace-write role の契約と一致しないため採用しない
- hook と agent 定義の両方に role 契約を置く: runtime 注入はできるが、二重管理と drift を避けられないため採用しない

## Consequences

- Positive: 軽量な delegation で不要な repo 文書が作られない
- Positive: shared working tree を使う実装 slice と、隔離が必要な試行を明確に使い分けられる
- Positive: role 契約と runtime routing の変更責任が分離される
- Negative: root session は並列編集の対象範囲が重ならないよう管理する必要がある
- Negative: subagent の最終メッセージを恒久保存すべきか、task ごとに判断する必要がある
- Follow-up: hook の role 契約複製を除去し、routing test で runtime delta と fail-open behavior を検証する

## Executable Anchors

- Source: `AGENTS.md`、`agents/*.toml`、`hooks/subagent-routing.ps1`
- Tests / types / schemas / static checks: `hooks/test-subagent-routing.ps1`
