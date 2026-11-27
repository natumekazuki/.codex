# Codex system promptの記録

ここには、組み込み指示を比較するための[取得時の英語本文と対応訳](snapshots/)を置きます。収録範囲はrolloutの先頭にある `session_meta.payload.base_instructions.text` だけです。Character、AGENTS.md、runtimeの権限・MCP、会話・認証は含めません。取得した原文は編集しません。

実際に選択できるWithMate用の配布物は、編集可能な[英語版](../../.codex/model-instructions-withmate.md)と[日本語版](../../.codex/model-instructions-withmate.ja.md)です。設定例は英語版のパスをコメントとして示します。どちらも `model_instructions_file` に設定した場合だけ組み込み本文を**置換**します。取得版や訳を保存しただけで、Sessionへの指示やCharacter設定は変わりません。

[取得・比較・適用手順](../runbooks/system-prompt-maintenance.md)はベースライン更新と配布ファイルだけの編集を区別します。更新で役割を終えた原文・訳はGit履歴を参照し、現行指示として併置しません。
