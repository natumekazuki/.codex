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
- `scripts/`: 外部由来の Skill を取得・同期する保守スクリプト

## Skill 一覧

| Skill | 区分 | 役割 |
| --- | --- | --- |
| `audit-codex-work-quality` | 専門 | 日時を固定したCodex作業の品質を監査する。通常のcode reviewには使わない |
| `design-tests` | 専門 | testの追加・意味変更・削除や回帰check選定前に、契約とobservableから直接検証を選ぶ |
| `design-ui-information` | 専門 | UIの視覚階層、情報密度、primitiveとaccessibilityを設計・確認する |
| `commit-note` | 軽量 | commit message と commit 前後の短い記録を整える |
| `contract-closure` | 専門 | 高リスクな契約変更の不変条件を兄弟入口、状態遷移、failure timing、scopeへ展開し、直接検証と反証reviewで閉じる |
| `withmate-glossary` | runtime管理 | WithMateが自動配置し、Session-boundなRepository Glossaryの参照と安全な更新契約を提供する |
| `relaygraph` | 専門 | RelayGraph の関係グラフ調査、検証、ルール作成を行う |
| `present-review-results` | 軽量 | review findingのseverity、classification、必須項目、提示順を統一する |
| `review-test-value` | 専門 | 構造化された価値コメントとPython・TypeScript・C# test sourceを抽出し、コメントの検証価値と本文の整合を審査する |
| `japanese-tech-writing-review` | 専門 | 日本語の技術文書を論証、読み手の負荷、用語、Markdown表記の観点で推敲する |
| `natural-japanese` | 専門 | ビジネス文書や一般記事を自然さ、読みやすさ、AI臭の観点で作成・推敲・診断する |

`natural-japanese` の取得元は [coji/natural-japanese](https://github.com/coji/natural-japanese) である。同期済み commit とライセンスは `skills/natural-japanese/NOTICE` と `skills/natural-japanese/LICENSE` に記録する。同期時のlocal adaptationは`argument-hint`除去、技術文書との振分け、短いSkill入口と文書modeの調整を再現する。上流の `main` と差分があるか確認する場合は `pwsh ./scripts/sync-natural-japanese.ps1 -Check`、同期する場合は `pwsh ./scripts/sync-natural-japanese.ps1` を実行する。同期時は `skills/natural-japanese/` 全体が上流由来の内容に置き換わるため、同ディレクトリに未コミット変更がある場合は処理を拒否する。

## 別端末への反映

- Git 管理する正本は `AGENTS.md`、`README.md`、`agents/`、`docs/adr/`、`docs/architecture/`、`docs/runbooks/`、`hooks/`、`hooks.json`、runtime-managedな`skills/withmate-glossary/`を除く`skills/`、`templates/`、`config.example.toml`、`config/agents.example.toml` とする
- `config.toml` は端末固有の local file として Git 管理しない。`projects.*`、`hooks.state`、runtime/plugin の `source`、MCP server の `command` / `env`、通知コマンド、Chrome native host 設定は端末ごとに生成または調整する
- 新しい端末ではこの repo を `$HOME/.codex` に配置し、既存の `config.toml` に `config.example.toml` と `config/agents.example.toml` の必要 section だけを移す
- hook は `hooks.json` から `$HOME/.codex/hooks/implementation-restraint.ps1` と `$HOME/.codex/hooks/subagent-routing.ps1` を呼び出す。Windows では `commandWindows` が `%USERPROFILE%\.codex` を使う
- `CODEX_HOME`を別directoryへ変える端末では、上記hook commandの既定pathもその配置へ調整してからtrustと到達を確認する。profileだけを配置してhookの参照先も移動したとは扱わない
- Spark routing の現在 mode は `hooks/subagent-routing.local.json` に保存される。このファイルは端末ごとの一時状態なので Git 管理しない
- WithMateを使う端末では、起動後に`withmate-memory` commandと`skills/withmate-glossary/`が配置され、Glossary Skillのmanaged markerにある`bundleVersion`とSkill一覧への認識を確認する
- Character context MCPを使う端末では、`config.example.toml`の`withmate-character-context`設定をlocal `config.toml`へ反映し、WithMate起動後の新しいCodex sessionで`codex mcp list`と公開toolを確認する。詳細は`docs/runbooks/withmate-character-context.md`を参照する
- Repository Glossary MCPを使う端末では、`config.example.toml`の`withmate-glossary`設定をlocal `config.toml`へ反映し、新しいCodex sessionで公開toolとprimary checkoutへの束縛を確認する。詳細は`docs/runbooks/withmate-repository-glossary.md`を参照する
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

- role の選択基準と risk gate は `AGENTS.md` を正本とする。具体的な未解決設計がない小変更にdesignerのhandoffを加えず、必要な独立reviewの条件は維持する
- 各 role の明示model、reasoning effort、sandbox、静的契約は `agents/*.toml`、model未指定roleの選択差分は設定例とprofileを正本とする
- `review-test-value`の二段階審査artifactとcustom agent例はbootstrap中である。runtime activationと新session smokeが完了するまでは、現行の単一審査workflowを利用する
- Spark の利用状態は `hooks/set-spark-routing.ps1` で切り替え、操作方法は `hooks/subagent-routing-modes.md` を参照する
- model変更の比較方法は `docs/runbooks/compare-subagent-roles.md` を参照し、単一runのtoken差だけで既定roleを置き換えない

## Astra / GPT-5.6 profileの選択

例はCodex **0.134.0以降**の独立profile形式を対象とし、CLI 0.153.4と[現行schema](https://developers.openai.com/codex/config-schema.json)で確認する。`config.example.toml`のrootは具体的な`gpt-5.6-sol / medium`であり、Astraを既定に切り替える例ではない。旧`model_personality`は現行schemaのkeyではないため除き、`personality`を使う。

導入時は既存設定の必要sectionだけをmergeする。`config/agents.example.toml`のregistryと`agents/`を同じCodex homeへ配置し、`config/astra.config.toml`と`config/gpt56.config.toml`を、それぞれ有効な`CODEX_HOME`直下の`astra.config.toml`と`gpt56.config.toml`として配置する。private pathやMCP secretを共有例へ加えず、既存のconfig全体を上書きしない。この手順は端末変更の承認を得た導入時に実行する。

```powershell
codex --profile astra
codex --profile gpt56
```

[設定の優先順位](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles)はbase user config、選択profile、project config、CLI overrideの順に上書きされる（managed policyの制約は別途適用される）。旧`[profiles.<name>]`やtop-levelの`profile` selectorは使わない。`model_instructions_file`で組込み指示を置換する方法も使わない。

| 対象 | gpt56 / base | astra | effort | sandbox |
| --- | --- | --- | --- | --- |
| root | Sol | Astra | medium | 利用端末の設定。profileは変更しない |
| designer | Sol | Astra | xhigh | read-only |
| reviewer | Sol | Astra | xhigh | read-only |
| targeted_reviewer | Sol | Astra | xhigh | read-only |
| implementer | Sol | Sol | high | workspace-write |
| planner | Sol | Sol | high | read-only |
| focused_implementer | Luna | Luna | medium | workspace-write |
| researcher | Luna | Luna | medium | read-only |
| validator | Luna | Luna | medium | workspace-write |
| slice_reviewer | Luna | Luna | high | read-only |
| test_value_luna | Luna | Luna | medium | read-only |
| test_value_sol | Sol | Sol | xhigh | read-only |
| fast_* | 既存Spark | 既存Spark | 各role定義を維持 | 各role定義を維持 |

ここでAstraは`gpt-6-astra`、Solは`gpt-5.6-sol`、Lunaは`gpt-5.6-luna`を指す。3 roleだけmodel指定を外し、`[agents].default_subagent_model`をprofileで選ぶ。他の明示modelを持つroleはそのmodelを保つ。role全文をprofileごとに複製しない。

このdefaultは3 roleに限定されず、**model未指定のdefault childなどにも適用される**。意図しない無指定roleがないか導入時に確認する。明示spawn model、roleのmodel、`agents.default_subagent_model`、parentからの継承を区別する。rootへの`--model`だけでchildも切り替わるとは限らず、profile名や説明文を実効値の証拠にしない。

3 roleはまずSol/xhigh対Astra/xhighを個別に比較し、Astra/highやmediumは別系列にする。通常の実装・調査・検証はSol/Lunaを継続し、未解決の複雑な不整合は調査済みsource、失敗仮説、checkとともにrootへ返す。モデル強化をdesignerやreviewの起動回数を増やす理由にしない。

新規sessionと代表childでhost側のmodel、effort、sandbox、読込元を確認する。利用不可は明示的に未実行とし、別modelへ自動downgradeしない。全GPT-5.6構成への切戻しは`--profile gpt56`でrootと無指定childのSol選択をread-backし、3 roleのxhighと他roleの固定値を確認する。端末のproject/CLI overrideがある場合も同様に確認する。比較完了前の既定切替は保留する。

## Hook 方針

- `hooks/implementation-restraint.ps1` は `UserPromptSubmit` と `SubagentStart` で短い実装制約を追加し、`SessionStart(source=compact)` でcompaction後の継続へ再注入する
- `agents/*.toml` は静的な role 責務、禁止事項、出力契約、明示model、sandbox の正本とする
- `hooks/subagent-routing.ps1` は `UserPromptSubmit` と `SubagentStart` で、現在の Spark mode と 手動の優先方針など実行時差分だけを追加する
- hook の切替状態は ignored な `hooks/subagent-routing.local.json` に保存する。環境変数 `CODEX_SUBAGENT_SPARK_MODE` がある場合はそれを優先する
- mode は `balanced`、`spark-first`、`standard-only` を使う。既定は `balanced`
- standing authorization、role 選択、risk gate、成果返却、統合責務は `AGENTS.md` を正本とし、hook へ複製しない
- JSONを解釈するhookの検証は PowerShell pipeline ではなく、子 `pwsh -File` に JSON stdin を渡して本番の `Console.In` に近い形で行う。固定文面だけを返すhookは、子 `pwsh -File` の標準出力を直接確認する

restraintの詳細な注入文面は`hooks/implementation-restraint.ps1`を正本とし、共通の意味とauthorityは`AGENTS.md`、test設計の手順は`design-tests`が所有する。prompt、対象child、compact後の各登録は再注入経路であり、同一eventの二重登録とは区別する。今回の候補では経路を削除しない。別config layerやinline hooksと`hooks.json`の両方に同じcommandがある場合は導入前に重複を確認する。hookはadvisoryで、sandbox、tool permission、WithMate bindingを置き換えない。

## Skillの読込元と文書mode

一覧の10 Skillはchecked-inで、`withmate-glossary`だけはruntime管理である。Skillの説明は選択の入口であり、本文を使うときに通知されたpathから開く。`AGENTS.md`の条件付き参照から、該当するSkillと必要なreferenceだけを読む。

[公式の探索先](https://learn.chatgpt.com/docs/build-skills#where-to-save-skills)はuserの`$HOME/.agents/skills`とprojectの`.agents/skills`などで、symlink先も探索する。本repositoryの`skills/`は配布元であり、全hostが`$CODEX_HOME/skills`を同じ方法で探索すると仮定しない。2026-09-05のCLI 0.153.4の`codex debug prompt-input`では`.codex/skills`のSkillが一覧へ入ることを確認した。このsessionのruntime一覧も同じ配置を通知しているが、別端末・新profileでの発見は個別確認する。

端末へ反映するときは、まず新規sessionのSkill一覧と実pathを確認する。既存harness/runtimeが配布済みなら二重配置しない。未検出の場合は、そのhostが探索するuserまたはproject scopeへ必要なSkillだけをsymlinkまたは配布する方法を選び、同名重複を確認する。これは導入手順であり、共有設定例を編集しただけでは配置済みにならない。WithMateのmanaged Skillはコピー・forkしない。

短いchat、進捗、コマンド結果は共通の日本語報告規則で返す。技術文書の構成・論証・Markdownは`japanese-tech-writing-review`、一般文書の執筆・自然さの推敲・採点は`natural-japanese`を選ぶ。通常は一方を使い、両方必要なら観点を分ける。

`natural-japanese`はquickを既定とし、対象文書のlintと通読を行う。fullは明示依頼、具体的な失敗コスト、複数の独立した品質観点を根拠に選び、「ちゃんと」などの強調語や長さだけでは起動しない。必要な独立reviewを成果物に応じて選び、全fullに3人を固定しない。明示されたfullの工程や特定reviewを途中で省略せず、scoreは診断だけで無断rewriteしない。詳細はSkillのmode選択を正本とする。

## 検証と導入状態

必要check、適用されるCI、test価値審査、必要な独立reviewとblocking解消を完了条件にする。Skillの説明変更に無関係な全adapter restoreを加えず、script・選択・schema変更は`review-test-value`のValidation節から対応するcheckを選ぶ。成功済みcheckの反復条件は`AGENTS.md`を参照する。

テスト価値審査の二段階有効化は#42〜#45の別scopeである。この移行では既存gateと専用Luna/medium・Sol/xhighを維持するが、別作業で隔離・新規session・候補自身の審査などの条件を満たしたactivationを禁止しない。worktree分離だけをworkerの強制隔離の証拠にしない。

比較条件と切戻しは[比較runbook](docs/runbooks/compare-subagent-roles.md)を使う。portableな実装と構文検証の完了は、実モデル比較、child開始、手動・自動compaction後の適用完了と区別する。必要な再注入を未確認のまま削除せず、旧設定の選択経路を保つ。統括#41は必要な全体確認が残る間Openを維持する。
