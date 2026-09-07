# Instruction Governance

共通ルールの正本は`AGENTS.md`。過剰実装の抑制、操作範囲、個人設定と必要時の入口を置き、一般開発の工程は固定しない。

| 情報 | 正本 |
| --- | --- |
| 親・一般子の既定modelと設定例 | `config.example.toml`、`config/agents.example.toml` |
| 汎用roleのmodel・指示 | `agents/*.toml` |
| test価値の抽出、review観点、完了条件 | `skills/review-test-value/` |
| 任意のUI・文書・監査・RelayGraph操作 | 対応する`skills/*/SKILL.md` |
| WithMate Memory／Characterの許可と運用 | `docs/runbooks/withmate-character-context.md` |
| Repository Glossaryの操作契約 | runtime-managed `withmate-glossary` Skill。継続的な許可とdeleteの個別承認は`AGENTS.md` |

`hooks/implementation-restraint.ps1`は共通ルールの短い再通知であり、別のworkflowやrole選択を所有しない。

過去ADR・完了済みplanは判断履歴であり、現行の起動義務ではない。
