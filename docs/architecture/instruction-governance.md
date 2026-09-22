# Instruction Governance

共通ルールの入口は`AGENTS.md`。常時必要な抑制・操作境界と、作業別の詳細を読む条件・参照先を置く。AGENTS.mdとhookの共通文書参照は`~/.codex/...`で明示し、`~`を実行環境のユーザーhomeへ解決する。作業対象repositoryのcwd、配布元checkout、`CODEX_HOME`による別配置へ参照先を切り替えない。本書等の通常の相対リンクは参照元文書を基準とし、共通文書の利用時の配置先とは区別する。reviewの固定回数や専用の進行管理基盤は設けない。

| 情報 | 正本 |
| --- | --- |
| 統合・後追い修正・公開の判断基準 | [開発・review・統合](../guides/development.md)。バグ管理先と互換性境界は各プロジェクトの規約文書（AGENTS.md、README、またはそこから明示された文書） |
| 親・一般子の既定modelと設定例 | `config.example.toml`、`config/agents.example.toml` |
| 汎用roleのmodel・指示 | `agents/*.toml` |
| test価値の抽出、review観点、審査の完了条件 | `skills/review-test-value/`。発見後の修正時期・統合可否は共通基準に従う |
| UI変更の必須基準と専門判断 | [UI基準](../guides/ui.md)とruntimeの`design-ui-information` Skill |
| 文書・監査・RelayGraph操作 | 適用条件に該当する`skills/*/SKILL.md` |
| 委譲・履歴を継承しない子への入力 | [委譲](subagent-workspace.md) |
| WithMate Memory／Characterの利用契機と許可 | [WithMate利用方針](../guides/withmate.md)。AGENTS.mdは提供情報に基づく読込条件、MCPは呼出契約、runbookは接続設定・障害調査を担う |
| Repository Glossaryの操作契約 | runtime-managed `withmate-glossary` Skill。利用契機・継続的な許可とdeleteの個別承認は[WithMate利用方針](../guides/withmate.md) |

`hooks/implementation-restraint.ps1`は共通ルールの短い再通知であり、別のworkflowを設けない。既存のモデル選択を再提示するが、分割先本文は注入しない。

過去ADR・完了済みplanは判断履歴であり、現行の起動義務ではない。2026-09-23のmodel運用刷新では、明示依頼により旧model配分専用ADRと廃止routingの記述を現行treeから削除した。削除前の定義はGit履歴で参照し、互換運用として復活させない。system promptの不変スナップショットや取得元のmodel名は運用定義ではなく、変更しない。
