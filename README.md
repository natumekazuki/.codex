# Codex Clean Room v1

このディレクトリは、Codex の現在のユーザー設定と運用ルールの正本です。

## 目的

- token消費を抑えることより成果物品質を優先し、品質を落とさず省ける処理だけを効率化する
- 通常タスクは root session で進めつつ、独立した調査、計画、実装、検証、レビューで品質または速度が上がる場合は subagent を使う
- subagent は standing authorization として許可し、毎回の明示依頼を必須にしない
- plan と workspace は必要な場合だけ作り、作業再開は現在のgitと正本から組み立てる。恒久設計文書は ADR と、複数 subsystem / process / repo / 外部 service に波及して code と executable contract から復元できない非局所情報に限定する
- Codex で利用する専門 Skill は含めるが、他ツールの global 設定や運用規則は含めない

## 構成

- `AGENTS.md`: Codex home から読み込む個人向け global 共通ルール
- `agents/`: 必要時だけ呼ぶ child agent 定義
- `skills/`: 軽量な定型作業と、明示実行向けの専門 workflow skill
- `templates/`: ADR、例外的なfile plan、review、非局所architecture文書の汎用テンプレート
- `docs/adr/`: 長期的または後戻り困難な設計判断とその理由
- `docs/architecture/`: 複数 subsystem / process / repo / 外部 service に波及し、code と executable contract から復元できない非局所設計
- `docs/runbooks/`: 端末ごとに実行する共有運用手順
- `hooks/`: implementation restraint と subagent routing などの Codex hook
- `config/agents.example.toml`: agent registry へ登録する場合の例
- `config.example.toml`: 別端末へ移す共有設定の例

## Skill 一覧

| Skill | 区分 | 役割 |
| --- | --- | --- |
| `commit-note` | 軽量 | commit message と commit 前後の短い記録を整える |
| `contract-closure` | 専門 | 高リスクな契約変更の不変条件を兄弟入口、状態遷移、failure timing、scopeへ展開し、直接検証と反証reviewで閉じる |
| `withmate-memory` | runtime管理 | WithMateが自動配置し、injected Character context、MCP優先のCharacter Memory / affect / semantic Memoryの運用契約を提供する |
| `relaygraph` | 専門 | RelayGraph の関係グラフ調査、検証、ルール作成を行う |
| `japanese-tech-writing-review` | 専門 | 日本語の技術文書を論証、読み手の負荷、用語、Markdown表記の観点で推敲する |
| `natural-japanese` | 専門 | ビジネス文書や一般記事を自然さ、読みやすさ、AI臭の観点で作成・推敲・診断する |

## 別端末への反映

- Git 管理する正本は `AGENTS.md`、`README.md`、`agents/`、`docs/adr/`、`docs/architecture/`、`docs/runbooks/`、`hooks/`、`hooks.json`、`skills/`（`skills/withmate-memory/`を除く）、`templates/`、`config.example.toml`、`config/agents.example.toml` とする
- `config.toml` は端末固有の local file として Git 管理しない。`projects.*`、`hooks.state`、runtime/plugin の `source`、MCP server の `command` / `env`、通知コマンド、Chrome native host 設定は端末ごとに生成または調整する
- 新しい端末ではこの repo を `$HOME/.codex` に配置し、既存の `config.toml` に `config.example.toml` と `config/agents.example.toml` の必要 section だけを移す
- hook は `hooks.json` から `$HOME/.codex/hooks/implementation-restraint.ps1` と `$HOME/.codex/hooks/subagent-routing.ps1` を呼び出す。Windows では `commandWindows` が `%USERPROFILE%\.codex` を使う
- Spark routing の現在 mode は `hooks/subagent-routing.local.json` に保存される。このファイルは端末ごとの一時状態なので Git 管理しない
- WithMateを使う端末では、起動後に`skills/withmate-memory/`が自動配置され、managed markerの`bundleVersion`とSkill一覧への認識を確認する
- Character context MCPを使う端末では、`config.example.toml`の`withmate-character-context`設定をlocal `config.toml`へ反映し、WithMate起動後の新しいCodex sessionで`codex mcp list`と公開toolを確認する。詳細は`docs/runbooks/withmate-character-context.md`を参照する
- `browser/`、`computer-use/`、`process_manager/`、`chrome-native-hosts.json` は plugin/runtime の生成状態として扱い、別端末では Codex が再生成する

## 設計判断

- root workflow 専用の巨大 instruction は置かない
- child agent は常時 orchestration の構成要素ではなく、限定目的の補助役にする
- file plan は例外扱いにし、通常は会話と差分で完了させる
- plan は作業手順、design は実装前後を通じた判断活動として分け、設計したこと自体を文書作成理由にしない
- goal、scope、done、riskの整理と、変更・検証・未実行・残リスクの報告は標準workflowに含め、独立Skillや常設artifactにしない
- 現在の実装と構造は source、実行可能な期待動作と不変条件は test / type / schema / static check、局所理由は code comment に置く
- ADR に該当する決定は必ず残し、それ以外の恒久設計文書は複数 subsystem / process / repo / 外部 service に波及し、code と executable contract から復元できない非局所情報だけに限定する
- task-local な設計メモを repo 設計書へ同期する workflow は採用しない
- 汎用templatesはADR、例外的なfile plan、review、非局所architecture文書の最小骨格に留め、Skill固有templateは各Skill内を正本とする
- 通常の実装に専用作業領域や分離作業ツリーを要求しない
- exact source stateを必要とする独立reviewはGit commitへ固定し、cleanなdetached worktreeで実行する。Git未管理または未commitのsourceにはsnapshot fallbackを設けない
- review worktreeはSessionFolder配下を第一候補、gitignore済みの`.agent-worktrees/reviews/`をfallbackとし、review用branchを作らず全reviewer終了後に安全確認して削除する

## Model and Routing

- role の選択基準と risk gate は `AGENTS.md` を正本とする
- 各 role の model、reasoning effort、sandbox、静的契約は `agents/*.toml` を正本とする
- Spark の利用状態は `hooks/set-spark-routing.ps1` で切り替え、操作方法は `hooks/subagent-routing-modes.md` を参照する
- model変更の比較方法は `docs/runbooks/compare-subagent-roles.md` を参照し、単一runのtoken差だけで既定roleを置き換えない

## Hook 方針

- `hooks/implementation-restraint.ps1` は `UserPromptSubmit` と `SubagentStart` で、要求に根拠のない後方互換性、fallback、回帰test、抽象化を追加しないための短い実装制約を追加する
- `agents/*.toml` は静的な role 責務、禁止事項、出力契約、model、sandbox の正本とする
- `hooks/subagent-routing.ps1` は `UserPromptSubmit` と `SubagentStart` で、現在の Spark mode と quota fallback など実行時差分だけを追加する
- hook の切替状態は ignored な `hooks/subagent-routing.local.json` に保存する。環境変数 `CODEX_SUBAGENT_SPARK_MODE` がある場合はそれを優先する
- mode は `balanced`、`spark-first`、`standard-only` を使う。既定は `balanced`
- standing authorization、role 選択、risk gate、成果返却、統合責務は `AGENTS.md` を正本とし、hook へ複製しない
- JSONを解釈するhookの検証は PowerShell pipeline ではなく、子 `pwsh -File` に JSON stdin を渡して本番の `Console.In` に近い形で行う。固定文面だけを返すhookは、子 `pwsh -File` の標準出力を直接確認する
