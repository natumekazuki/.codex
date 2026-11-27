# Codex 個人設定

`natumekazuki/.codex` は、Codexに配置する共通指示・Skill・設定例の配布元である。作業時の入口は [AGENTS.md](AGENTS.md)。本書は配布物の導入・検証と、このrepository自身の保守を扱う。他のrepositoryの課題管理先や公開手順を定めるものではない。

## 構成

| 探したいもの | 場所 |
| --- | --- |
| 作業中の判断・必須参照 | [共通入口](AGENTS.md)、[用途別guide](docs/guides/)、[委譲と作業領域](docs/architecture/subagent-workspace.md) |
| 専門手順・実行資産 | [配布するSkill](skills/)、[native role](agents/)、[hook登録](hooks.json)と[スクリプト](hooks/) |
| 親・子の設定、profile | [共有config例](config.example.toml)、[registryとprofile](config/) |
| 任意で組込み指示を置き換える場合 | [WithMate用英語版](.codex/model-instructions-withmate.md)・[日本語版](.codex/model-instructions-withmate.ja.md)、[取得版・訳](docs/system-prompt/)、[保守手順](docs/runbooks/system-prompt-maintenance.md) |
| 導入・診断、記入例 | [用途別runbook](docs/runbooks/)、[ADR・review記録の記入例](templates/)（任意） |
| 過去の判断と公開版 | [ADR](docs/adr/)、[版別リリースノート](docs/releases/README.md) |

## このrepositoryの管理先とリリース境界

バグ・後追い残件の管理先は [natumekazuki/.codex のGitHub Issues](https://github.com/natumekazuki/.codex/issues)。Issueの登録・更新・closeは外部writeとして、共通入口の承認範囲に従う。

### 本repositoryの開発・リリース境界

- `vMAJOR.MINOR.PATCH` タグが指すcommitを配布版とする。タグのないcommitやbranch上の途中状態は互換保証の対象としない。
- 維持するのは各タグのリリースノートで明示した利用者向け契約であり、実装全体ではない。
- 破壊的な契約変更はmajor、互換な変更はminorまたはpatchを上げて新しいタグへ記録する。リリースごとに [一覧](docs/releases/README.md) と `docs/releases/vMAJOR.MINOR.PATCH.md` を更新し、変更・互換性・検証結果を残す。

### Codex／Claude／OpenCode間の変更反映

共通ルール・自主管理Skill・設定例・通知方針はCodexを基本の正本とし、通常の保守では目的・制約・完了条件を揃えて同じ作業で3者に反映する。各配布元（`.codex`、`.claude`、`~/.config/opencode`）は相互importや共有リンクに依存せず独立して使える構成とする。Claude・OpenCode起点の共通改善はCodexにも戻す。

model・tool・設定形式など製品固有の機構は各製品に合わせる。対象製品を限定した依頼を他の配布元への書込権限としない。認証、実config、Session URL・token、Memory・履歴・cache、外部managed Skillは同期しない。

## 配置と検証

共通文書の読取先は実行ユーザーのhome直下の `~/.codex/`。直接checkoutするか、別checkoutから次の配布物を同じ相対配置にコピー・linkする。配布元を編集しても、別の端末配置は更新されない。

- `AGENTS.md`、`docs/guides/` 全体、`docs/architecture/subagent-workspace.md`、[Glossaryの接続・障害調査runbook](docs/runbooks/withmate-repository-glossary.md) を揃える。別repositoryのrootと下位ディレクトリから、実際に読んだ共通入口・詳細と、そのrepository固有の管理先・互換性定義を確認する。参照が欠けたら配置を修復し、cwdや別の `CODEX_HOME` の同名文書で埋めない。
- `config.toml` は既存設定へ[設定例](config.example.toml)の必要なsectionだけを取り込む。実config・認証・私有path・生成済みruntimeはGit管理しない。`model_instructions_file` は追記でなく組込み指示の置換なので、採用する場合だけ配置した本文を指定する。
- native設定・hookは有効な `CODEX_HOME`（未指定なら `~/.codex`）に配置する。roleを使う場合は `agents/`、registry、使うprofileを同じhomeへ揃える。`/hooks` でtrustと到達を確認し、inline hookとの二重実行を避ける。
- Skillは対象ホストの探索先へ配置し、新規Sessionでの発見・重複とruntimeが通知する実pathを確認する。[共通指示の探索](https://developers.openai.com/codex/guides/agents-md/)と[Skillの発見](https://developers.openai.com/codex/skills/)は別経路であり、READMEの一覧やMarkdownリンクから本文が注入されるわけではない。
- WithMateのGlossary／Session Graph／SessionのHTTP接続とmanaged `withmate-glossary` SkillはWithMateが供給する。通常の導入で手動登録・forkや短命tokenの永続化はしない。Glossaryの手動STDIOはrunbookの開発・診断用途に限る。通常子の選定・配送は[協同guide](docs/guides/withmate-collaboration.md)、Worktreeの配置先決定と実体の確認は[作業領域guide](docs/architecture/subagent-workspace.md#git-worktreeの配置)に従う。端末固有の方針ファイルは配布・自動移行しない。

## modelとrole

次の表はnative設定例の開始値である。一般作業はSol、手順と期待結果が決まった作業はLuna、明確な入力・完了条件のある視覚・文章・局所修正はTerra、契約間の難しい判断はAstraに任せるのが配布設定の狙いであり、速度・消費枠の実測順位ではない。[委譲guide](docs/architecture/subagent-workspace.md)が選定を、config・role・hookが実行時の設定と制御を担う。WithMate通常子の選定にはこの表を使わない。

| 設定 | model | effort |
| --- | --- | --- |
| 通常の親・`sol` profile | `gpt-6.2-sol` | medium（Standard速度） |
| 手動切替の `astra` profile | `gpt-6.2-astra` | low（Standard速度） |
| 一般childの既定・`general_sol` | `gpt-6.2-sol` | medium |
| `general_luna` | `gpt-6-luna` | high |
| `general_terra` | `gpt-6.1-terra` | medium |
| `general_astra` | `gpt-6.2-astra` | medium |

profileは `codex --profile sol` または `codex --profile astra` で選ぶ。Terraの導入条件（Codex CLI 0.159.0以降）、実際の提供状態、role・hookの適用と構成比較は[比較・導入手順](docs/runbooks/compare-subagent-roles.md)で確認する。モデル名の掲載やAPI単価から、利用可能性や作業当たりの費用を推定しない。

## Skillの配布

このrepositoryで保守するのは、変更testの [review-test-value](skills/review-test-value/)、UIの [design-ui-information](skills/design-ui-information/)、Crewの共有記録を扱う [session-graph](skills/session-graph/)、採用済みrepositoryを扱う [relaygraph](skills/relaygraph/)、期間を指定した [作業監査](skills/audit-codex-work-quality/)、明示的な文章推敲用の [japanese-tech-writing-review](skills/japanese-tech-writing-review/) と [natural-japanese](skills/natural-japanese/) である。導入時はSkill本文とUI表示・起動案内用のmetadataを揃える。

`natural-japanese` の[同期元](https://github.com/coji/natural-japanese)・commit・licenseは [NOTICE](skills/natural-japanese/NOTICE) と [LICENSE](skills/natural-japanese/LICENSE) を参照。同期には `pwsh ./scripts/sync-natural-japanese.ps1 -Check`（確認）と、更新時の `pwsh ./scripts/sync-natural-japanese.ps1` を使う。scriptはlocal adaptationと明示起動方針を再現し、このSkillに未コミット変更があれば更新を拒否する。

コードとtestのコメントは[共通コメント規約](docs/guides/code-comments.md)に従い、新規・変更箇所から整える。testの価値審査は[変更testの審査と保持](docs/guides/test-changes.md)を参照する。コメントの機械検査は[利用先での導入手順](docs/guides/code-comments.md#利用先での機械検査の導入)に従う。

## 配布時の確認

変更が影響する契約を確認する。配布元の文書を確認しただけなら、端末での適用や実動作まで確認したとは扱わない。出力比較が依頼された場合は、[比較手順](docs/runbooks/compare-subagent-roles.md#役割指示を比較する時)を参照する。

[CI](.github/workflows/ci.yml) は監査スクリプト・Windows hookの回帰を検査する。利用先のコメント規約の強制は、このCIの成功とは別に確認する。モデル実行やsecretを公開CIへ追加しない。確認した対象・条件・結果と判断に響く未確認は既存の[review記録](docs/guides/development.md#sessionfolderのreview記録と対応管理)等に残し、文書の一致を実動作の証拠にしない。
