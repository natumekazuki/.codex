# Codex 個人設定

Astraを親に使い、一般の仕事の進め方はモデルへ任せる。追加の共通ルールは過剰実装の抑制と、変更testの価値確認を中心にする。ユーザー変更の保護、操作範囲、承認条件、必要な安全動作は維持する。

このcheckoutの`review-test-value`は、Git差分から変更testを抽出し、通常のread-onlyサブエージェントへreviewを委譲するSkillである。抽出器の成功、全recordのreview、指摘への対応を現在の変更状態と合わせて確認する。

## 構成

| 正本 | 内容 |
| --- | --- |
| `AGENTS.md` | 短い抑制、操作境界、個人設定、変更testのreview条件とWithMateへの入口 |
| `agents/` | 汎用のカスタムrole |
| `skills/` | `review-test-value`と任意の管理Skill |
| `hooks/`、`hooks.json` | 共通ルールの短い再通知、サブエージェント起動時の履歴継承既定値 |
| `config.example.toml`、`config/` | 共有できる設定例。実configと認証は端末local |
| `docs/runbooks/` | 必要時の運用・導入手順 |
| `docs/adr/`、完了済みplan | 過去の判断履歴。現行の工程を義務付けない |

## modelとrole

| 用途 | model | effort |
| --- | --- | --- |
| 通常の親 | `gpt-6-astra` | medium、Standard速度 |
| 一般childの既定 | `gpt-5.6-luna` | max |
| `general_astra` | `gpt-6-astra` | medium |
| `general_sol` | `gpt-5.6-sol` | medium |
| `general_luna` | `gpt-5.6-luna` | max |

汎用roleは調査・設計・実装・review・検証に使え、必要な仕事は起動時の依頼で表す。モデル選択方針は`hooks/implementation-restraint.ps1`から毎回注入する。標準`default`／`worker`／`explorer`はカスタムroleとは別である。

設定例はCLI `0.153.4`を対象にする。汎用roleの権限は親から継承し、調査依頼のread-only境界が必要な場合はruntimeで制限する。`review-test-value`のreviewは、抽出record、repository root、対象scopeを起動時のpromptで`general_luna`へ渡す。親はreview結果を読んで追加contextや別reviewerの要否を判断する。

`PreToolUse` hookは`spawn_agent`の`fork_turns`を明示値も含め常に`none`へ置き換え、他の引数は保持する。Astra親からの`general_astra`とAstraの直接model指定は拒否する。必要な文脈は起動時の依頼へ含める。設定例の`features.multi_agent_v2`は待機timeoutの最小値と既定値を120000 msにする。実環境への配置後、hookのtrust・到達と新規sessionの実効設定を確認する。

親をSolへ明示切替する場合は、有効な`CODEX_HOME`直下へ配置した`gpt56.config.toml`を使う。

```powershell
codex --profile gpt56
codex --profile astra
```

どちらも同じ汎用role・短い共通ルールを使う。model配置とreasoning effortは運用上の設定値であり、性能の最適値や週リミット消費の解消を保証しない。設定例の値と新規sessionの実効値を区別する。

## Skill

| Skill | 起動用途 |
| --- | --- |
| `review-test-value` | Python／TypeScript／C#のtest新規追加・意味変更・削除・移設をGit差分から抽出し、通常のread-only reviewへ渡す |
| `design-ui-information` | 明示的なUI設計方針の指定・見直し |
| `japanese-tech-writing-review` | 明示的な技術文書の推敲・論証・表記確認 |
| `natural-japanese` | 明示的な自然さの推敲・採点・文体調整 |
| `audit-codex-work-quality` | 日次・固定期間の作業監査 |
| `relaygraph` | 採用済みrepositoryの関係調査・変更・検証。新規導入は明示依頼時 |

UIと二つの文書Skillは各Skillの`agents/openai.yaml`にある明示呼出し設定に従う。`review-test-value`は通常のSkillとして利用する。通常のREADME編集、commit、短報告へ自動の校正工程を付けない。明示された文書modeの必要工程は保つ。

Skillはruntimeが通知する実pathから読む。本repositoryの`skills/`は配布元であり、全hostの探索先が同じとは仮定しない。新規sessionの一覧で発見と重複を確認する。`withmate-glossary`はWithMateが配布する別枠のmanaged Skillであり、コピー・forkしない。

`natural-japanese`のupstreamは[coji/natural-japanese](https://github.com/coji/natural-japanese)。同期commitとlicenseは同Skillの`NOTICE`／`LICENSE`に記録する。

```powershell
pwsh ./scripts/sync-natural-japanese.ps1 -Check
pwsh ./scripts/sync-natural-japanese.ps1
```

同期scriptはlocal adaptationと明示起動policyを再現し、同Skillに未コミット変更があれば拒否する。通常の作業中に無関係な同期を行う必要はない。

## 配置と検証

端末への適用時は既存`config.toml`へ設定例の必要sectionだけを反映する。MCP binding、認証、private path、無関係な設定を共有例へ持ち込まず、live全体を上書きしない。`agents/`とregistry例、選択profileを同じCodex homeへ配置する。

hookは有効な`CODEX_HOME`（未指定ならユーザーhomeの`.codex`）から解決する。`/hooks`でtrustと到達を確認し、inline hooks等との重複を避ける。新規session、一般child、再開・compactionで短い抑制を届ける。read-only reviewの境界は起動時の依頼で明示する。

WithMateのMemory／Character操作はMCP toolの説明とschemaに従い、[runbook](docs/runbooks/withmate-character-context.md)はセットアップ・障害調査時に参照する。Glossaryは[導入説明](docs/runbooks/withmate-repository-glossary.md)とruntime-managed Skillを必要時に参照する。通常の許可と対象・revision・個別承認条件を維持する。生成済みruntimeやplugin状態、実config、認証はGit管理しない。

CIは決定論的な抽出器、parser、Git差分選択、adapterの回帰checkを確認する。LLM reviewは親が通常のread-onlyサブエージェントへ委譲し、モデル実行やsecretを公開CIへ追加しない。
