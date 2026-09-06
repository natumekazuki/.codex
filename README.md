# Codex 個人設定

Astraを親に使い、一般の仕事の進め方はモデルへ任せる。追加の共通ルールは過剰実装の抑制と必須のtest価値審査を中心にする。ユーザー変更の保護、操作範囲、承認条件、必要な安全動作は維持する。

このcheckoutは変更候補であり、ソース整理とlive導入は別の状態である。必須審査のworker・全体gate・実runtimeの確認が揃うまで、軽量化した構成をliveへ部分配布しない。現在の不足は[有効化runbook](docs/runbooks/activate-test-value-review.md)を参照する。

## 構成

| 正本 | 内容 |
| --- | --- |
| `AGENTS.md` | 短い抑制、操作境界、個人設定、必須審査とWithMateへの入口 |
| `agents/` | 汎用2＋専門2のカスタムrole |
| `skills/` | 必須1＋任意5の管理Skill |
| `hooks/implementation-restraint.ps1`、`hooks.json` | 共通ルールの短い再通知 |
| `config.example.toml`、`config/` | 共有できる設定例。実configと認証は端末local |
| `docs/runbooks/` | 必要時の運用・導入手順 |
| `docs/adr/`、完了済みplan | 過去の判断履歴。現行の工程を義務付けない |

## modelとrole

| 用途 | model | effort |
| --- | --- | --- |
| 通常の親 | `gpt-6-astra` | medium、Standard速度 |
| 一般childの既定 | `gpt-5.6-sol` | medium |
| `general_sol` | `gpt-5.6-sol` | medium |
| `general_luna` | `gpt-5.6-luna` | medium |
| `test_value_luna` | `gpt-5.6-luna` | medium |
| `test_value_sol` | `gpt-5.6-sol` | xhigh |

汎用2roleは調査・設計・実装・review・検証に使え、必要な仕事は起動時の依頼で表す。Solは判断を伴う仕事、Lunaは期待結果が明確な仕事の目安であり、固定handoff表や段階的な昇格規則ではない。標準`default`／`worker`／`explorer`はカスタム4種とは別である。

設定例はCLI `0.153.4`を対象にする。汎用roleの権限は親から継承し、調査依頼のread-only境界が必要な場合はruntimeで制限する。専門審査の入力隔離は[review-test-value](skills/review-test-value/SKILL.md)が所有し、汎用roleや親の自己評価で代行しない。

親をSolへ明示切替する場合は、有効な`CODEX_HOME`直下へ配置した`gpt56.config.toml`を使う。

```powershell
codex --profile gpt56
codex --profile astra
```

どちらも同じ4role・短い共通ルール・必須審査を使う。model配置は運用方針、mediumは初期値であり、性能の最適値や週リミット消費の解消を保証しない。設定例の値と新規sessionの実効値を区別する。

## Skill

| Skill | 起動用途 |
| --- | --- |
| `review-test-value` | Python／TypeScript／C#のtest新規追加・意味変更で必須。削除・移設の解消も扱う |
| `design-ui-information` | 明示的なUI設計方針の指定・見直し |
| `japanese-tech-writing-review` | 明示的な技術文書の推敲・論証・表記確認 |
| `natural-japanese` | 明示的な自然さの推敲・採点・文体調整 |
| `audit-codex-work-quality` | 日次・固定期間の作業監査 |
| `relaygraph` | 採用済みrepositoryの関係調査・変更・検証。新規導入は明示依頼時 |

UIと二つの文書Skillは`agents/openai.yaml`の`policy.allow_implicit_invocation: false`で明示呼出し中心にする。通常のREADME編集、commit、短報告へ自動の校正工程を付けない。明示された文書modeの必要工程は保つ。必須`review-test-value`にはこの無効化を適用しない。

Skillはruntimeが通知する実pathから読む。本repositoryの`skills/`は配布元であり、全hostの探索先が同じとは仮定しない。新規sessionの一覧で発見と重複を確認する。`withmate-glossary`はWithMateが配布する別枠のmanaged Skillであり、コピー・forkしない。

`natural-japanese`のupstreamは[coji/natural-japanese](https://github.com/coji/natural-japanese)。同期commitとlicenseは同Skillの`NOTICE`／`LICENSE`に記録する。

```powershell
pwsh ./scripts/sync-natural-japanese.ps1 -Check
pwsh ./scripts/sync-natural-japanese.ps1
```

同期scriptはlocal adaptationと明示起動policyを再現し、同Skillに未コミット変更があれば拒否する。通常の作業中に無関係な同期を行う必要はない。

## 配置と検証

端末への適用時は既存`config.toml`へ設定例の必要sectionだけを反映する。MCP binding、認証、private path、無関係な設定を共有例へ持ち込まず、live全体を上書きしない。`agents/`とregistry例、選択profileを同じCodex homeへ配置する。

hookは有効な`CODEX_HOME`（未指定ならユーザーhomeの`.codex`）から解決する。`/hooks`でtrustと到達を確認し、inline hooks等との重複を避ける。新規session、一般child、再開・compactionで短い抑制を届ける。専門workerには一般hookを注入しない。旧routingのlocal stateを一括削除する必要はない。

WithMateのMemory／Characterは[固有runbook](docs/runbooks/withmate-character-context.md)、Glossaryは[導入説明](docs/runbooks/withmate-repository-glossary.md)とruntime-managed Skillを必要時に参照する。通常の許可と対象・revision・個別承認条件を維持する。生成済みruntimeやplugin状態、実config、認証はGit管理しない。

CIは既存の抽出・packet・validator・routing・resolution・監査機能と抑制hookを確認する。offlineの成功を実モデル審査や新規sessionの成功と同一視しない。候補の必須審査が完了してから、[小さな比較と導入手順](docs/runbooks/compare-subagent-roles.md)で確認・切替する。公開CIへ有料モデル実行やsecretを追加しない。
