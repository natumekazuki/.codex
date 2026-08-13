# Instruction Governance

## 目的

Codex の共通規則、role 契約、再利用手順、runtime delta を異なる正本へ分離し、一つの規則を複数箇所で維持しない。

## Ownership

| 情報 | 正本 | 境界 |
|---|---|---|
| 共通のtask lifecycle、authority、planning、knowledge placement、delegation、validation、Memory、Git規則 | `AGENTS.md` | taskやroleに依存しない恒久規則と適用順序 |
| 静的な role 責務、禁止事項、出力契約、model、sandbox | `agents/*.toml` | agent type ごとの契約 |
| 特定用途で明示的に呼び出す再利用手順 | `skills/*/SKILL.md` | Skill が対象とする workflow だけ |
| 現在の Spark mode、quota fallback など runtime delta | `hooks/subagent-routing.ps1` | 実行時にしか決まらない追加情報 |
| 責務を分離した理由と長期的 trade-off | `docs/adr/0002-subagent-execution-and-routing-ownership.md` | 現行 role 一覧や局所手順を複製しない |

## Resolution

- hook は `AGENTS.md` や `agents/*.toml` の静的規則を上書きまたは再定義しない
- Skill は対象 workflow の手順を定義するが、共通 authority や正本規則を再定義しない
- child output は採用候補であり、repo artifact へ自動同期しない
- 競合または不明確な指示を検出した場合、root session が上位 instruction と現在の repo artifact を確認して統合する

## Pointers

- subagent の実行境界: `docs/architecture/subagent-workspace.md`
- 設計情報の配置判断: `AGENTS.md`の「Sources of Truth and Knowledge Placement」
- routing mode の操作: `hooks/subagent-routing-modes.md`
