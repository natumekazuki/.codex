# Codex system promptの記録

このディレクトリでは、WithMateセッションで使われたCodex組み込み指示のバージョン管理下の記録を保持します。

## 範囲

英語スナップショットには、Codex rolloutの最初の `session_meta.payload.base_instructions.text` だけを収録します。ユーザープロンプト、Character context、`AGENTS.md`、runtimeの権限、MCP環境値、認証、セッション状態は含めません。

日本語版は翻訳参照用です。設定で明示的に選択しない限り、Codexへ渡すファイルではありません。

WithMate用ファイルは編集可能な統合用コピーです。英語版と日本語版を用意し、取得した英語ベースラインを基に、重複する人格説明、60秒単位の進捗・待機制約、Skill利用時の宣言要件を取り除き、技術者前提の技術コミュニケーションとMermaid利用を反映しています。Character固有の文言は後続変更で調整します。

## 構成

| パス | 目的 |
| --- | --- |
| `snapshots/YYYY-MM-DD-<model>.en.md` | 日付とモデルごとの英語原文の不変スナップショット |
| `snapshots/YYYY-MM-DD-<model>.ja.md` | 対応する英語スナップショットの日本語訳 |
| `.codex/model-instructions-withmate.md` | 編集可能なWithMate用指示ファイル（英語版） |
| `.codex/model-instructions-withmate.ja.md` | 編集可能なWithMate用指示ファイル（日本語版） |
| `scripts/capture-codex-system-prompt.ps1` | rolloutから組み込み指示を抽出するスクリプト |
| `docs/runbooks/system-prompt-maintenance.md` | 取得、レビュー、翻訳、設定の手順 |

## 初回記録

初回記録は、Codex CLI 0.154.0で動作していた `gpt-5.6-luna` セッションから、2026-09-16に取得しました。取得した本文は17,730文字です。

記録間の変更はGit履歴で追跡します。既存の日付付きスナップショットは上書きせず、元のプロンプトが変わった場合は新しい日付のファイルを作成します。
