# Codex 個人設定

本書は`natumekazuki/.codex`の配布資産、保守、配置の案内である。各repositoryでCodexが従う共通ルールの入口は`AGENTS.md`、作業別の本文は`docs/guides/`等の明示された参照先に置く。本書の配布元固有の管理先・リリース境界・検証手順を、他repositoryの作業ルールとして適用しない。

Codex nativeの配布設定ではGPT-6.1 Solを基本に使い、手順・期待結果がほぼ決まっている作業はLuna、明確な入力・完了条件を持つ視覚・文章・局所修正はTerra、高度な判断が要求される作業はAstraを選ぶ。WithMate通常子の実行条件は下記の端末方針と実カタログから選ぶ。一般の仕事の進め方はモデルへ任せる。追加の共通ルールは責務に基づく既存実装の削減と過剰追加の抑制、統合優先・修正分離、変更testの価値確認、ユーザー向けUIの設計品質を中心にする。ユーザー変更の保護、操作範囲、承認条件、必要な安全動作は維持する。

このcheckoutの`review-test-value`は、Git差分から変更testを抽出し、通常のread-onlyサブエージェントへreviewを委譲するSkillである。抽出器の成功、全recordのreview、各指摘の採否・対応時期を確認する。review完了と全件修正は分け、後追いの基準を満たす残件だけを引き継ぐ。

## このrepositoryの管理先とリリース境界

このrepositoryはCodexの共通ルールをGit管理する配布元であり、`AGENTS.md`にはrepository固有の規約を置かない。この節は`natumekazuki/.codex`の開発・保守だけに適用し、共通ルールの適用先repositoryには適用しない。

- このrepositoryのバグと後追い残件は、`natumekazuki/.codex` のGitHub Issueで管理する。Issueへの登録・更新・closeは外部writeとして操作・対象・scopeへの承認を要し、承認済みの範囲は再確認しない。

### 本repositoryの開発・リリース境界

- Gitタグのないcommitとbranch上の変更は開発途中として扱い、途中状態との互換性を保証しない。
- `vMAJOR.MINOR.PATCH`形式のGitタグが指すcommitをリリース状態とし、配布版の識別に使う。互換維持の対象はそのタグのリリースノートに記載した利用者向け契約であり、実装全体ではない。契約の破壊的変更はmajor versionを上げ、互換修正はminorまたはpatch versionを上げて新しいタグへ記録する。
- 初回の維持対象は`v1.0.0`であり、`review-test-value`のCLI、構造化result、metadata v2、対応adapter、Git差分選択の契約を含む。各契約の詳細は既存のSkill referenceと`docs/releases/v1.0.0.md`で確認する。
- リリースごとに`docs/releases/README.md`の一覧と`docs/releases/vMAJOR.MINOR.PATCH.md`を更新し、変更、互換性、検証結果を記録する。

## 構成

共通ルール本文は`AGENTS.md`、`docs/guides/`、`docs/architecture/subagent-workspace.md`と各Skill・roleの指示に置く。`docs/runbooks/`は指定された導入・保守作業の手順である。`docs/system-prompt/`は編集元資産、`docs/adr/`と`docs/releases/`は本repositoryの記録であり、共通ルール本文の置き場ではない。

| 正本 | 内容 |
| --- | --- |
| `AGENTS.md` | 常時必要な原則・操作境界、条件付き参照 |
| `docs/guides/` | [開発・統合](docs/guides/development.md)、[設計・文書化](docs/guides/design-decisions.md)、[変更test](docs/guides/test-changes.md)、[UI](docs/guides/ui.md)、[WithMate利用](docs/guides/withmate.md)、[Session協同](docs/guides/withmate-collaboration.md)の判断基準 |
| `docs/architecture/subagent-workspace.md` | nativeとの委譲境界、model制限、作業領域。各Skillは固有手順、現在のMCP説明・schemaは呼出契約の正本 |
| `agents/` | 汎用のカスタムrole |
| `skills/` | 変更testのreview、UI設計、管理・文書向けのSkill |
| `hooks/`、`hooks.json` | 共通ルールの短い再通知、サブエージェント起動時の履歴継承既定値 |
| `config.example.toml`、`config/` | 共有できる設定例。実configと認証は端末local |
| `docs/runbooks/` | 必要時の運用・導入手順 |
| `docs/releases/` | Gitタグごとのリリースノートと互換性・検証結果 |
| `docs/system-prompt/`、`.codex/model-instructions-withmate.md` | Codex system promptの取得版、日本語訳、WithMate用編集元 |
| `docs/adr/` | 判断履歴。適用状態を明記し、置換・撤回後も本文を保持する |

## WithMate V7の協同と端末方針

Role・入力来歴、担当、相談・報告・再開、端末の選定方針・catalog・Worktree配置の判断は[Session間の協同](docs/guides/withmate-collaboration.md)に集約する。nativeとの境界とGit操作は[委譲guide](docs/architecture/subagent-workspace.md)、対話・Memory／Affect・folder共有は[WithMate利用guide](docs/guides/withmate.md)が担う。

協同guideは直接checkout・手動コピーとも配布対象とし、端末固有ファイルや候補表の転記を準備条件にしない。利用者の実ファイルは自動削除・移行せず、Git除外を維持する。恒久設定と今回限りの指定、native設定とWithMate通常子の選定を混同しない。

V7の実利用確認は、実配置した全体統括へAPI名・具体値を提示せず委譲可能な目的を渡し、方針・宛先候補・配置先の取得と通常子への実配送を観測する。通常依頼・単発指定で保存方針が変わらないことも確認する。静的照合やAPI単体の読取は、この実利用確認の成功とは分ける。

## Codex／Claude／OpenCode間の変更反映

この節は`.codex`、`.claude`、OpenCode設定の保守にのみ適用し、共通ルールの適用先repositoryには適用しない。Codexを基本の正本とし、ClaudeとOpenCode（`~/.config/opencode`）は独立して完結する構成を保つ。

- `.codex`、`.claude`、OpenCode設定は独立して完結させ、相互importやリンク共有に依存しない。
- 共通ルール、自分で保守するSkill、設定例、通知方針の変更は、目的・制約・完了条件を揃えて同じ作業で3者へ反映する。モデル、tool、設定形式等の製品固有部分は各製品に適した定義を維持する。
- ClaudeまたはOpenCode起点の共通改善はCodexへ逆反映する。製品固有の変更も他の2者への影響を確認し、反映しない場合は理由を作業報告に示す。
- 認証情報、実config、Session URL・token、Memory、履歴、cache、外部managed Skillは同期対象外とする。
- 3者の差分と必要な動作を確認し、反映・検証結果を報告する。

## 共通ルールの保守と検証

この節は本repositoryで指示を変更・配置する際の確認方法であり、適用先の毎タスクへ課すチェックリストではない。判断基準は[開発guide](docs/guides/development.md)・[設計guide](docs/guides/design-decisions.md)、読む条件は[AGENTS.md](AGENTS.md)、固有手順は各Skillを正本とする。

変更した判断境界の問題を再現する入力と、その制約を適用すべきでない対照入力を選び、期待する判断・操作が区別されることを確認する。範囲は変更の影響に合わせ、過去の全ケースを常設の必須一覧にしない。

入口・guide・Skill・metadata・hookの関係と参照を照合し、配布元の文言、実配置、新規／再開・compact後や履歴非継承の子で有効な指示、実際の行動を分けて確認する。出力方針は履歴・model・Character・tool条件を揃えて比較し、用件への適合、重要条件、検討の付加価値、受け手に残る再説明・選別・判断の負担を見る。文字数や条文の一致だけで改善とはしない。

実施条件・結果と判断に影響する未確認範囲は既存の[review記録](docs/guides/development.md#sessionfolderのreview記録と対応管理)等へ残す。[template](templates/review.md)は任意の骨格であり、指摘別対応の正本を増やさない。文書・生成応答・実動作の証拠を区別し、新しい恒久test・採点・台帳・同期基盤を設けない。

### Memory・Affect方針の検証

責務・能動的読取・Character表現・許可は[WithMate利用guide](docs/guides/withmate.md)、操作入力は現在のMCP／CLI契約と照合する。変更した責務に応じて、関連本文の利用、通常会話と背景の分担、表現と事実の境界、操作ごとの保存結果を確認する。実Memory・Affectへ架空の経験・情動を書き込まず、検証結果や進捗の写しをMemoryへ保存しない。

WithMateに保存済みの背景登録指示は配布物更新では変わらない。[公開仕様](https://github.com/natumekazuki/WithMate/blob/2b1fda1fb268708e849b8da270c74d752209fe3b/docs/releases/v6.5.0-preview.3.md)の標準指示へ切り替える際はSettingsの `Use Preset` と区別し、既存のカスタム指示を無断で置き換えない。

### 設計判断と文書の更新

現行文書・判断履歴・リリースノートの更新は設計guideに従う。入口とhookは検出条件と参照にとどめ、共通ルール本文を案内・履歴へ複製しない。

### 方針変更の検証

今回変更した停止・継続・承認の境界が、問題場面と対照場面で保たれるか確認する。必要な入力検証・データ保護・必須checkを短文化で免除せず、独立作業の継続と依存部分の保留を区別する。判断例だけで統合や後続開始の実動作まで確認済みとはしない。

### 課題・対応予定の運用ルールの検証

対象repositoryの管理先・維持境界・予定・完了条件へ到達し、既定運用と権限で判断・記録できるかを変更範囲で確認する。予定未指定・管理方法の未定義・参照失敗を区別し、未完了を隠す移動や一律停止へ変わっていないかを見る。本repository固有の運用を適用先へ流用しない。

## modelとrole

本repositoryのCodex native設定例・role定義は`gpt-6.1-sol`、`gpt-6-luna`、`gpt-6.1-terra`、`gpt-6-astra`で構成する。この節は配布設定と採用理由の説明であり、作業時の委譲基準は[委譲と作業領域](docs/architecture/subagent-workspace.md)が正本である。

### 公式情報と運用判断

OpenAI公式の[model選択](https://learn.chatgpt.com/docs/models#recommended-models)では、Solを複雑で長い作業、Lunaを明確で反復可能な作業、Terraを文章・視覚・computer use、Astraを最難関の作業に位置づける。[Terraの選択案内](https://learn.chatgpt.com/docs/model-selection#when-to-consider-gpt-61-terra)は、明確な入力・要求・検証方法を持つ局所的なcode修正も候補に含める。以下はこのrepositoryでの運用判断であり、各用途での優位を実測したものではない。

本repositoryは次の担当分けを採用する。taskの短さやtoken単価だけで決めず、必要な成果・判断と完了条件から直接選ぶ。

| model | このrepositoryでの担当 |
| --- | --- |
| GPT-6.1 Sol | 通常の親・一般childの既定。調査、設計、実装、debug、review。広い文脈や未解決の判断を含む一般作業 |
| GPT-6 Luna | 手順・期待結果がほぼ決まっている抽出、変換、照合、設計済みの実装 |
| GPT-6.1 Terra | 明確な入力・完了条件を持つ画像・画面の読解、描画確認、素材に基づく文章作成、検証方法が明確な局所修正 |
| GPT-6 Astra | 難しいtradeoff、契約間の矛盾、反例等の高度な判断。非Astra親から必要な問題を絞って委譲する |

Lunaで手順化できる作業をTerraへ一律に置き換えず、局所修正を必ずTerraへ渡す工程にもせず、一般既定のSolと必要に応じて使い分ける。上位modelを選ぶ前に下位modelを試す必要はない。Computer Use等の操作権限や、test価値審査・実描画等の必須確認はmodel選択で変わらない。

[API価格](https://developers.openai.com/api/docs/pricing)のtoken単価を、Codexの実消費枠や1タスクの費用比とは扱わない。担当分けの効果は実測済みではなく、再作業、推論token、cache、実行時間を含めて[比較手順](docs/runbooks/compare-subagent-roles.md)で確認する。

### 設定と委譲

| 用途 | model | effort |
| --- | --- | --- |
| 通常の親／`sol` profile | `gpt-6.1-sol` | medium、Standard速度 |
| 手動切替の`astra` profile | `gpt-6-astra` | low、Standard速度 |
| 一般childの既定／`general_sol` | `gpt-6.1-sol` | medium |
| `general_luna` | `gpt-6-luna` | high |
| `general_terra` | `gpt-6.1-terra` | medium |
| `general_astra` | `gpt-6-astra` | medium |

上記のeffortは配布設定の開始値であり、最適値を実証したものではない。Luna highと手動Astra lowは[Codexの開始推奨](https://learn.chatgpt.com/docs/models#pick-a-reasoning-effort)、Terra mediumは[公式guide](https://developers.openai.com/api/docs/guides/latest-model#gpt-61-terra)を参照する。Astra子は高度な判断を限定して渡すためmediumとする。taskの要求と確認結果に応じて、対応modelで利用可能なeffortを調整する。端末の実configやsessionで選択したeffortは配布設定とは区別する。

Terraの利用にはCodex CLI 0.159.0以降が必要であり、提供状態はplan・client・workspace設定等にも依存する。model一覧への掲載と、その環境での実起動成功は分けて確認する。

委譲基準の正本は[委譲と作業領域](docs/architecture/subagent-workspace.md)。hookはその要点を再通知する。標準`default`／`worker`／`explorer`はカスタムroleとは別であり、model省略時は設定例の一般child既定値を使う。汎用roleの権限は親から継承し、read-only依頼は起動時に明示し、利用可能なruntimeの制限も適用する。`review-test-value`も同じ委譲基準で担当を選び、抽出契約・全recordの審査・統合基準を維持する。

`PreToolUse` hookは上記4モデル以外の明示的な`model`指定を拒否する。Astra親からの`general_astra`とAstraの直接指定も拒否する。許可された`spawn_agent`／`Agent`の`fork_turns`は常に`none`へ置き換え、他の引数は保持する。roleの実modelやmodel未指定時の既定値はconfigと新規sessionで確認し、hookが任意の外部role定義まで検証すると扱わない。設定例の待機timeoutの最小値と既定値は120000 msを維持する。

profileを明示して親を選ぶ場合は、有効な`CODEX_HOME`直下へ配置した`sol.config.toml`または`astra.config.toml`を使う。

```powershell
codex --profile sol
codex --profile astra
```

どちらも同じ4つの汎用role・共通ルールを使う。指定modelがruntimeで利用できない場合は、許可された構成の親で可能な作業を続ける。配布元の設定とlive設定・実行結果を区別する。

### model選択の定義箇所

| 対象 | model選択を持つ箇所・扱い |
| --- | --- |
| 共有config・profile・registry | `config.example.toml`、`config/*.toml`。親、一般child、4 roleの登録を揃える |
| カスタムrole | `agents/general_{astra,sol,luna,terra}.toml`。model ID、effort、担当範囲を定義する |
| 委譲とhook | `docs/architecture/subagent-workspace.md`、`hooks/implementation-restraint.ps1`、`hooks/subagent-fork-default.ps1`、`hooks.json` |
| test価値審査 | `AGENTS.md`と`docs/guides/test-changes.md`がSkillへ導く。`skills/review-test-value/`は固有のmodel・role既定値を持たず、model IDと担当の選択基準はrole・委譲規約を参照する |
| WithMate通常子・端末の保存方針 | `docs/guides/withmate-collaboration.md`。WithMateの方針と宛先Workspaceの実カタログを照合し、上記native設定とは分ける |
| 指示ファイル・Skill・CI・script | `.codex/model-instructions-withmate*.md`を含め、native設定とWithMateの選定方針が混在しないことを確認する |

## Skill

| Skill | 起動用途 |
| --- | --- |
| `review-test-value` | Python／TypeScript／C#のtest新規追加・意味変更・削除・移設をGit差分から抽出し、通常のread-only reviewへ渡す |
| `design-ui-information` | 通常のユーザー向けUIの新設・変更・設計見直し。内容と体験に合う情報の採否、画面構成、視覚表現、一貫性、実描画の確認 |
| `japanese-tech-writing-review` | 明示的な技術文書の推敲・論証・表記確認 |
| `natural-japanese` | 明示的な自然さの推敲・採点・文体調整 |
| `audit-codex-work-quality` | 日次・固定期間の作業監査 |
| `relaygraph` | 採用済みrepositoryの関係調査・変更・検証。新規導入は明示依頼時 |
| `session-graph` | WithMateのSession Graph MCPへ指示を先行記録し、現在地・判断経緯の共有、訂正、再開・Compact後の復元を行う |

UIの新設・変更では`AGENTS.md`から`design-ui-information`の参照を求め、同Skillの`agents/openai.yaml`は暗黙呼出しを許可する。二つの文書Skillは各Skillの明示呼出し設定を維持する。`review-test-value`は通常のSkillとして利用する。通常のREADME編集、commit、短報告へ自動の校正工程を付けない。明示された文書modeの必要工程は保つ。

Skillはruntimeが通知する実pathから読む。本repositoryの`skills/`は配布元であり、全hostの探索先が同じとは仮定しない。新規sessionの一覧で発見と重複を確認する。`withmate-glossary`はWithMateが配布する別枠のmanaged Skillであり、コピー・forkしない。

`natural-japanese`のupstreamは[coji/natural-japanese](https://github.com/coji/natural-japanese)。同期commitとlicenseは同Skillの`NOTICE`／`LICENSE`に記録する。

```powershell
pwsh ./scripts/sync-natural-japanese.ps1 -Check
pwsh ./scripts/sync-natural-japanese.ps1
```

同期scriptはlocal adaptationと明示起動policyを再現し、同Skillに未コミット変更があれば拒否する。通常の作業中に無関係な同期を行う必要はない。

### Session Graphの配置と検証

Session Graphは同じCrewの起点・通常子孫Main・各MainのAuxiliaryの共有記録であり、保存・共有・表示はWithMateが担う。必須利用の入口と権限境界は共通AGENTS.md、現在のSessionへ提供されたMCPで何を読み、何をいつ記録するかは[`session-graph` Skill](skills/session-graph/SKILL.md)を正本とする。呼出契約はruntimeのMCP instructions・tool説明・schemaに従う。`skills/session-graph/`を既存のSkill配置方法で導入し、AGENTS.md・再通知hookと併せて確認する。

定義変更時は入口・Skill metadata・hook・関連guideの整合を確認し、変更範囲に応じて指示の先行記録、対象を絞った復元、必須本文の更新と任意属性の省略保持・null解除、競合・結果不明時の再取得を確認する。配布元編集、live配置、新規sessionでのSkill発見、MCP読書き、画面表示の確認を区別し、実施した確認と未確認の範囲を報告する。

### UI Skillの適用と検証

適用条件は[AGENTS.md](AGENTS.md)、必須契約は[UI基準](docs/guides/ui.md)、専門判断はruntimeの `design-ui-information` Skill、製品固有の方針・共通部品・基準画面は対象製品を正本とする。配布元の[Skill本文](skills/design-ui-information/SKILL.md)とmetadataはこの責務分担へ揃える。

更新・配置時は構文・参照・適用条件を照合し、新規Sessionで有効な指示とSkillの実path・発見・重複を確認する。`allow_implicit_invocation: true` は暗黙呼出しの許可であり、実際の適用証拠ではない。

通常のUI依頼ではSkill名を指定せず、変更した基準を再現する内容・体験の画面と対照条件を選ぶ。UI非関連の依頼へ不要な工程が付かないこと、軽微な変更の確認が影響範囲に限られることも、適用条件を変えた場合に確認する。利用可能な参照記録と実際の情報採否・構成・表現・実描画を照合し、自己申告だけで合格にしない。

確認はページ全体と代表的な閲覧・操作の流れを見て製品基準・関係画面と比べ、操作・motionの変更は静止画だけで済ませない。画像を実際に見て、起動・撮影・返答への画像提示まで変更に応じて確認する。test/build・DOM・accessibility検査は視覚品質の代替ではない。操作権限はAGENTS.md、機密保護と撮影・共有不能時の扱いはUI基準に従う。

配布元変更・live配置・Sessionでの適用・実際の出力品質を分け、実施結果と必要な後追いを既存review記録等へ残す。利用者調査をしていない場合、使いやすさや好みが実証されたとはしない。

## 配置と検証

共通ルールの利用時の配置先は、ユーザーhome直下の`~/.codex/`に固定する。このrepositoryを同ディレクトリへcheckoutする配置と、別checkoutから必要なファイルをコピー・linkする配置を区別する。共通指示を導入・更新する際は、`AGENTS.md`だけでなく、`docs/guides/`全体（通常の選定・配置判断を含む`withmate-collaboration.md`も対象）と`docs/architecture/subagent-workspace.md`を`~/.codex/`配下に同じ相対配置で揃える。接続・診断用の`docs/runbooks/withmate-character-context.md`と`docs/runbooks/withmate-repository-glossary.md`も揃える。選定方針・契約経路・Worktree配置はWithMateから読み、端末固有ファイルのコピーを導入条件にしない。AGENTS.mdとhookの共通文書参照は`~/.codex/...`というコード・path表記とし、`~`を実行環境のユーザーhomeへ解決する。作業対象repositoryのcwd、配布元checkout、`CODEX_HOME`による別配置へ参照先を切り替えない。symlink配置でも`~/.codex/`から各参照先へ到達できることを確認する。本README等の通常の相対リンクは配布元の文書閲覧用として残す。実環境の更新は配布元の編集と別の操作であり、無関係な設定を上書きしない。

[公式のAGENTS.md探索](https://developers.openai.com/codex/guides/agents-md/)はglobalとrepository rootからcwdまでの指示を組み合わせる。通常のMarkdownリンクはその本文の自動注入ではなく、配下すべてのAGENTS.mdを読む仕組みでもない。[Skill](https://developers.openai.com/codex/skills/)は名前・説明から選択した後に本文を読む別の仕組みである。履歴を継承しない子へは必要な条件・実path・権限を依頼に含める。

配置後は別repositoryのrootと下位ディレクトリから、読み込まれたAGENTS.mdの実path、`~/.codex/`配下の該当する詳細への到達、対象repositoryの管理先・互換性定義を確認する。`.codex`専用のIssue管理先・リリース契約を他repositoryへ適用しない。参照先が欠けた場合は配置を修復してから該当作業へ進み、同名のrepository内文書や本文のhook全注入で代用しない。

端末への適用時は既存`config.toml`へ設定例の必要sectionだけを反映する。MCP binding、認証、private path、無関係な設定を共有例へ持ち込まず、live全体を上書きしない。WithMateのMemory／Glossary／Session Graph MCPはWithMateがSessionへHTTP接続を自動供給するため、通常は手動登録せず、URL・短命tokenを永続化しない。Memory／Glossaryの手動STDIOは接続runbookの開発・診断用途に限る。`agents/`とregistry例、選択profileを同じCodex homeへ配置する。

hookは有効な`CODEX_HOME`（未指定ならユーザーhomeの`.codex`）から解決する。`/hooks`でtrustと到達を確認し、inline hooks等との重複を避ける。共通ルールの再通知は`SessionStart`のstartup・resume・compactと`SubagentStart`に限定し、`PreToolUse`の委譲制御は別に維持する。read-only reviewの境界は起動時の依頼で明示する。
[WithMate利用guide](docs/guides/withmate.md)の読込条件は`AGENTS.md`に従う。通常会話での能動的なMemory読取、背景実行との責務分担、Character Affectの反映、継続的な許可・保存範囲は同文書、利用可能な操作・探索例・呼出契約は現在提供されているMCP instructions・tool説明・schemaに従う。[runbook](docs/runbooks/withmate-character-context.md)はセットアップ・障害調査時に参照する。Glossaryは[導入説明](docs/runbooks/withmate-repository-glossary.md)とruntime-managed Skillを必要時に参照する。通常の許可と対象・revision・個別承認条件を維持する。生成済みruntimeやplugin状態、実config、認証はGit管理しない。

CIは決定論的な抽出器、parser、Git差分選択、adapterの回帰checkを確認する。LLM reviewは親が通常のread-onlyサブエージェントへ委譲し、モデル実行やsecretを公開CIへ追加しない。
