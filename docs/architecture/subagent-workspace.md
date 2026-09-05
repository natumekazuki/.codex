# Subagent Execution Boundary

## 目的

root session と child agent が同じ task を扱うときの、成果返却、shared working tree、隔離 worktree、恒久 artifact の境界を定義する。

## Default Flow

1. root session が child に担当範囲、必要な artifact、禁止事項、完了条件を渡す
2. read-only child は調査結果を、workspace-write child は割り当て範囲の差分と検証結果を最終メッセージで返す
3. root session が結果と working tree を確認し、採否、統合、追加検証、情報配置を判断する

通常の親子間返却に repo 内の `result.md` や task workspace は要求しない。

## Execution Modes

| mode | 適用条件 | 境界 |
|---|---|---|
| read-only | 調査、計画、設計、review | repo を編集せず最終メッセージで返す |
| validation workspace-write | test、build、lint、typecheck、smoke check | validator は check 実行のため workspace-write sandbox を使うが source を意図的に編集せず、生成物や lockfile などの副作用を報告する |
| shared working tree | 対象ファイルが明確で、他の編集 slice と重ならない実装 | child は割り当て範囲だけ編集し、root が差分を統合する |
| task worktree | 競合する並列編集、破壊的または大規模な試行、隔離が必要な検証 | `.agent-worktrees/<task>/<agent-task>/` を root が明示的に選ぶ |
| detached review worktree | exact source stateを必要とする独立review | rootまたはruntimeがSessionFolder配下を第一候補、gitignore済みの`.agent-worktrees/reviews/`をfallbackとして、`reviewCommitOid`をdetached checkoutしたcleanな`reviewTarget`を用意する |

同じファイルを複数の write-capable child に同時に割り当てない。root は同じ生成物や lockfile に触れる validator と implementer を並行実行しない。shared working tree の既存変更はユーザーまたは他の slice の所有物として保護する。

detached review worktreeは固定したcommitを読む独立review専用であり、通常のshared working treeと分ける。配置、OID、preflight、全終了経路のcleanupは`contract-closure` Skillの「必要な独立reviewを閉じる」を正本とする。rootまたはruntimeが準備と後始末を所有する。

## Durable Artifacts

- child の最終メッセージは一時的な task result であり、repo の正本ではない
- 複数 session の引継ぎ、監査証跡、大きな比較結果など保存価値がある場合だけ task-local artifact を作る
- source、test、type、schema、static check、comment、ADR、architecture 文書への配置は root session が `AGENTS.md` に従って判断する
- child の design output や task-local note を恒久文書へ自動同期しない

## Decision Pointer

- `docs/adr/0002-subagent-execution-and-routing-ownership.md`
- `docs/adr/0019-commit-bound-review.md`
