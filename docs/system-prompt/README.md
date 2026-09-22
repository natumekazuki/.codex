# Codex system promptの記録

このディレクトリでは、WithMate用指示の現行ベースラインとなるCodex組み込み指示と日本語訳を管理します。

## 範囲

英語スナップショットには、Codex rolloutの最初の `session_meta.payload.base_instructions.text` だけを収録します。ユーザープロンプト、Character context、`AGENTS.md`、runtimeの権限、MCP環境値、認証、セッション状態は含めません。

日本語版は翻訳参照用です。設定で明示的に選択しない限り、Codexへ渡すファイルではありません。

WithMate用ファイルは編集可能な統合用コピーです。英語版と日本語版を用意し、取得した英語ベースラインを基に、重複する人格説明、60秒単位の進捗・待機制約、Skill利用時の宣言要件を取り除き、技術者前提の技術コミュニケーションとMermaid利用を反映しています。Character固有の文言は後続変更で調整します。

## 構成

| パス | 目的 |
| --- | --- |
| `snapshots/YYYY-MM-DD-<model>.en.md` | 現行ベースラインの英語原文。取得内容は改変しない |
| `snapshots/YYYY-MM-DD-<model>.ja.md` | 対応する英語スナップショットの日本語訳 |
| `.codex/model-instructions-withmate.md` | 編集可能なWithMate用指示ファイル（英語版） |
| `.codex/model-instructions-withmate.ja.md` | 編集可能なWithMate用指示ファイル（日本語版） |
| `scripts/capture-codex-system-prompt.ps1` | rolloutから組み込み指示を抽出するスクリプト |
| `docs/runbooks/system-prompt-maintenance.md` | 取得、レビュー、翻訳、設定の手順 |

## 更新と保存

現行ベースラインとして必要な原文と訳だけを置きます。ベースラインの更新時は参照とWithMate用ファイルを揃え、役割を終えたスナップショットと訳を削除します。過去の内容はGit履歴で参照し、履歴保存を目的としたファイルの併存は行いません。
