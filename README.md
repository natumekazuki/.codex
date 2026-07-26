# .codex

Codex のユーザー設定、作業ルール、agent、Skill、hook を端末間で共有するための個人設定リポジトリです。端末固有の設定、認証情報、会話履歴、実行時データは含めません。

## 管理するもの

| パス | 内容 |
| --- | --- |
| `AGENTS.md` | 作業方針、権限境界、検証・レビューのルール |
| `config.example.toml` | 端末間で共有できる Codex 設定の例 |
| `config/agents.example.toml` | agent registry の設定例 |
| `agents/` | child agent の役割と実行設定 |
| `skills/` | Codex で使う個人 Skill |
| `hooks.json`, `hooks/` | subagent routing などの hook 定義と検証 |
| `docs/adr/` | 長期的な設計判断とその理由 |
| `docs/architecture/` | source や test だけでは復元しにくい非局所的な設計情報 |
| `docs/runbooks/` | 端末設定や運用上の手順 |
| `templates/` | ADR、plan、review、architecture 文書の雛形 |

## 管理しないもの

次のファイルやディレクトリは端末ごとに生成・管理し、Git では追跡しません。正確な除外対象は [`.gitignore`](.gitignore) を参照してください。

- 実際に使用する `config.toml`
- `auth.json`、session、memory、SQLite、log などの認証情報・履歴・実行時データ
- plugin cache、browser、computer-use などの runtime 生成物
- hook の現在モードを保存する `hooks/subagent-routing.local.json`
- WithMate が自動配置・更新する `skills/withmate-memory/`

## セットアップ

新しい端末では、このリポジトリを Codex home に配置します。

```sh
git clone https://github.com/natumekazuki/.codex.git "$HOME/.codex"
```

すでに `$HOME/.codex` がある場合は、既存の認証情報や端末固有設定を退避し、内容を確認してから統合してください。

1. `config.example.toml` から必要な設定を `config.toml` へ移す
2. child agent を使う場合は、`config/agents.example.toml` の必要な section を `config.toml` へ追加する
3. command、environment variable、project path などの端末固有値を調整する
4. WithMate を使う端末では、`withmate-memory` Skill が自動配置されたことを確認する

サンプル設定はそのまま上書きするための完成済み設定ではありません。既存の `config.toml` と比較し、必要な section だけを取り込んでください。

## 運用と確認

subagent routing mode の変更方法は [`hooks/subagent-routing-modes.md`](hooks/subagent-routing-modes.md) を参照してください。

hook の動作確認:

```powershell
pwsh -NoProfile -File hooks/test-subagent-routing.ps1
```

設定やルールを変更するときは、次のファイルを正本として扱います。

| 対象 | 正本 |
| --- | --- |
| 作業方針と権限境界 | `AGENTS.md` |
| agent の役割、model、sandbox | `agents/*.toml` |
| routing の実行時処理 | `hooks/subagent-routing.ps1` |
| routing mode の操作方法 | `hooks/subagent-routing-modes.md` |
| 長期的な設計判断 | `docs/adr/` |

## ライセンス

このリポジトリ全体を対象とするライセンスは設定していません。第三者由来のファイルについては、各ディレクトリ内のライセンス表記や出典情報に従ってください。
