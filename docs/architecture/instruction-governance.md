# Instruction Governance

共通ルールの正本は`AGENTS.md`。過剰実装の抑制、操作範囲、個人設定と必要時の入口を置き、一般開発の工程は固定しない。

| 情報 | 正本 |
| --- | --- |
| 親・一般子の既定modelと設定例 | `config.example.toml`、`config/agents.example.toml` |
| 汎用2roleと単一review専用roleのmodel・指示 | `agents/*.toml` |
| test価値審査の対象選定・入力構築・実行・完了条件 | `skills/review-test-value/SKILL.md` |
| 単一reviewの観点と結果の意味 | `skills/review-test-value/references/review-contract-v3.md` |
| flat schema、ordinal検証、identity付与、host gate | 対応scriptとcontract test |
| 任意のUI・文書・監査・RelayGraph操作 | 対応する`skills/*/SKILL.md` |
| WithMate Memory／Characterの許可と運用 | `docs/runbooks/withmate-character-context.md` |
| Repository Glossaryの操作契約 | runtime-managed `withmate-glossary` Skill。継続的な許可とdeleteの個別承認は`AGENTS.md` |

`hooks/implementation-restraint.ps1`は共通ルールの短い再通知であり、別のworkflowやrole選択を所有しない。専門workerには一般hookや親履歴を注入しない。

過去ADR・完了済みplanは判断履歴であり、現行の起動義務ではない。旧多段reviewの契約も同様に扱う。候補版とlive版の配置・有効化状態、実モデルE2Eは[審査の有効化runbook](../runbooks/activate-test-value-review.md)で区別する。
