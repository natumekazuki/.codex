# Codex 個人設定

Astraを親に使い、一般の仕事の進め方はモデルへ任せる。追加の共通ルールは過剰実装の抑制、変更testの価値確認、ユーザー向けUIの設計品質を中心にする。ユーザー変更の保護、操作範囲、承認条件、必要な安全動作は維持する。

このcheckoutの`review-test-value`は、Git差分から変更testを抽出し、通常のread-onlyサブエージェントへreviewを委譲するSkillである。抽出器の成功、全recordのreview、指摘への対応を現在の変更状態と合わせて確認する。

## 構成

| 正本 | 内容 |
| --- | --- |
| `AGENTS.md` | 短い抑制、UI必須基準、操作境界、個人設定、変更testのreview条件とWithMateへの入口 |
| `agents/` | 汎用のカスタムrole |
| `skills/` | 変更testのreview、UI設計、管理・文書向けのSkill |
| `hooks/`、`hooks.json` | 共通ルールの短い再通知、サブエージェント起動時の履歴継承既定値 |
| `config.example.toml`、`config/` | 共有できる設定例。実configと認証は端末local |
| `docs/runbooks/` | 必要時の運用・導入手順 |
| `docs/system-prompt/`、`.codex/model-instructions-withmate.md` | Codex system promptの取得版、日本語訳、WithMate用編集元 |
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
| `design-ui-information` | 通常のユーザー向けUIの新設・変更・設計見直し。内容と体験に合う情報の採否、画面構成、視覚表現、一貫性、実描画の確認 |
| `japanese-tech-writing-review` | 明示的な技術文書の推敲・論証・表記確認 |
| `natural-japanese` | 明示的な自然さの推敲・採点・文体調整 |
| `audit-codex-work-quality` | 日次・固定期間の作業監査 |
| `relaygraph` | 採用済みrepositoryの関係調査・変更・検証。新規導入は明示依頼時 |

UIの新設・変更では`AGENTS.md`から`design-ui-information`の参照を求め、同Skillの`agents/openai.yaml`は暗黙呼出しを許可する。二つの文書Skillは各Skillの明示呼出し設定を維持する。`review-test-value`は通常のSkillとして利用する。通常のREADME編集、commit、短報告へ自動の校正工程を付けない。明示された文書modeの必要工程は保つ。

Skillはruntimeが通知する実pathから読む。本repositoryの`skills/`は配布元であり、全hostの探索先が同じとは仮定しない。新規sessionの一覧で発見と重複を確認する。`withmate-glossary`はWithMateが配布する別枠のmanaged Skillであり、コピー・forkしない。

`natural-japanese`のupstreamは[coji/natural-japanese](https://github.com/coji/natural-japanese)。同期commitとlicenseは同Skillの`NOTICE`／`LICENSE`に記録する。

```powershell
pwsh ./scripts/sync-natural-japanese.ps1 -Check
pwsh ./scripts/sync-natural-japanese.ps1
```

同期scriptはlocal adaptationと明示起動policyを再現し、同Skillに未コミット変更があれば拒否する。通常の作業中に無関係な同期を行う必要はない。

### UI Skillの適用と検証

`design-ui-information`は業務・操作中心のUIに限定しない。記事、作品集、商品紹介、検索・閲覧サービス、モバイルアプリ、娯楽・制作ツール等も、内容と中心となる体験から構成する。本文や作品を補足へ追いやらず、不要な情報の羅列、無計画な縦積み、画面ごとの別設計を完成扱いしない。短さや特定の見た目を全UIへ強制しない。

表示内容・文言・見た目・操作の変更はSkill名の明示がなくても対象とし、誤字修正などの確認は影響範囲に限定する。UIへ影響しない内部処理の変更へUI設計工程を追加しない。短い必須基準は[`AGENTS.md`](AGENTS.md)、詳細の正本は[`SKILL.md`](skills/design-ui-information/SKILL.md)、製品固有の方針・共通部品・基準画面は対象アプリやサイト側で扱う。

Metadataの`allow_implicit_invocation: true`は暗黙呼出しの許可であり、個々の依頼で適用された証拠ではない。公式の[Skill呼び出しとmetadataの説明](https://learn.chatgpt.com/docs/build-skills)も参照し、配布元の編集、実行環境への反映、実際の出力を分けて検証する。

ルール更新・配置時は、許可された環境で次を確認する。

1. `AGENTS.md`、Skill本文、metadata、READMEの適用条件と完了条件を照合する。明示呼出し限定、文字や単一surfaceの一律優先、本文の補足扱い、描画未確認を代替検査で確認済みにする旧方針が残っていないかを見る。YAMLの構文、Skill名と`$design-ui-information`の対応も確認する。
2. 新規sessionで有効な指示と、runtimeが通知するSkillの実path・内容・発見・重複を確認する。別のpathを読んでいる、旧版や重複がある、参照記録が取れない場合は区別して記録する。配布元を編集しただけで反映済みとしない。
3. Skill名や「デザインも考えて」を付けない通常のUI依頼と、UI非関連の依頼を実行する。下表の異なる体験・条件を使い、利用可能な参照記録と実際の採否・構成・表現・描画確認を照合する。適用の自己申告や参照記録だけでは合格にしない。
4. PR説明など既存の記録先へ、依頼と条件、確認できた参照、描画上の結果、修正・再確認、未実施・未確認を簡潔に残す。問題が変更範囲内なら修正して再確認し、範囲外なら分けて報告する。

以下はこのルール変更の検証ケースであり、日々の小さなUI変更ごとに全件を課すものではない。提供する文章・画像・データと、変更を許可する範囲を用意して実行する。

| 依頼・条件 | 期待する結果 |
| --- | --- |
| 提供した長文と写真で記事ページを作る | 本文・写真を主内容とし、章立て・行長・文字・余白を設計する。長さだけで折りたたまず、不必要な操作誘導を足さない。 |
| 内部IDや未使用の技術情報を含むデータで、音楽・書籍・作品等のコレクションを作る | 鑑賞・探索に合う画像、まとまり、密度、移動方法を選び、全metadataを列挙しない。 |
| 指定した作品・商品と表現方針でポートフォリオや紹介ページを作る | 画像・文字・余白を目的に合わせる。管理画面の密度や単一面を強制せず、架空の実績や定型sectionで埋めない。 |
| 短い補足が大きなカードで縦積みされ、主内容が下方へ押し出されたページを整理する | 採否、まとまり、面積、順序、反復を直す。文字縮小・全折りたたみ・内部スクロールへの移し替えで済ませない。 |
| 画像と長文を含むページを幅広・狭幅で表示する | 読む順序と主従を保ち、画像比率・折り返し・余白を実描画で確認する。横幅を埋めるだけ、全部縦積みにするだけで済ませない。 |
| 共通規約と妥当な既存画面がある製品へ閲覧画面・設定画面を追加する | 構成が異なってもnavigation、文字・余白・色、用語、操作を揃え、同等部品を作り直さない。 |
| 比較・入力を中心とし、利用者が照合に使う番号もある画面を作る | 必要な比較材料・番号と情報密度を保つ。情報削減や鑑賞向けの大きな余白を一律に強制しない。 |
| 検索結果0件、未取得、取得失敗、共有機能だけの利用制限を実装する | 状態を区別し、空領域や制約の説明を過大に展開しない。主内容全体への影響と補助機能だけの制約を分ける。 |
| 誤字修正とUI非関連の内部処理変更をそれぞれ依頼する | 前者は変更箇所と影響に確認を限定し、後者にUI設計・描画工程を追加しない。 |
| 描画環境または必要な操作許可がない条件でUIを変更する | 実装、代替確認、視覚上の未確認を分ける。UI品質確認済みとせず、権限を緩和しない。 |

描画確認ではページ全体と代表的な閲覧・操作の流れを見て、参照方針や関係画面と比較する。取得したスクリーンショットを見ずに完了とせず、操作・motionの変更は静止画だけで済ませない。Test/build、DOM、accessibility検査の成功は視覚品質の代替ではない。Computer Useの明示指示条件を含む既存の操作範囲は維持する。

上記は検証手順であって実施記録ではない。ルールを変更したこと、sessionで適用されたこと、出力品質を確認したことを区別し、未実施は未実施として残す。利用者調査をしていない場合、使いやすさや好みが実証されたとは扱わない。専用の採点・台帳・CI基盤は追加しない。

## 配置と検証

端末への適用時は既存`config.toml`へ設定例の必要sectionだけを反映する。MCP binding、認証、private path、無関係な設定を共有例へ持ち込まず、live全体を上書きしない。`agents/`とregistry例、選択profileを同じCodex homeへ配置する。

hookは有効な`CODEX_HOME`（未指定ならユーザーhomeの`.codex`）から解決する。`/hooks`でtrustと到達を確認し、inline hooks等との重複を避ける。新規session、一般child、再開・compactionで短い抑制を届ける。read-only reviewの境界は起動時の依頼で明示する。
WithMateのMemory／Character操作はMCP toolの説明とschemaに従い、[runbook](docs/runbooks/withmate-character-context.md)はセットアップ・障害調査時に参照する。Glossaryは[導入説明](docs/runbooks/withmate-repository-glossary.md)とruntime-managed Skillを必要時に参照する。通常の許可と対象・revision・個別承認条件を維持する。生成済みruntimeやplugin状態、実config、認証はGit管理しない。

CIは決定論的な抽出器、parser、Git差分選択、adapterの回帰checkを確認する。LLM reviewは親が通常のread-onlyサブエージェントへ委譲し、モデル実行やsecretを公開CIへ追加しない。
