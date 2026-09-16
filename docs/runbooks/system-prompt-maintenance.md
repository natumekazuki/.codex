# Codex system promptの保守

このrunbookでは、Codex組み込み指示の英語原文、日本語訳、WithMate統合用コピーを、レビュー可能なバージョン管理下で維持する方法を定めます。

## 取得元と範囲

取得元は、Codex rollout JSONLの最初の `session_meta` レコードです。取得対象の本文は `payload.base_instructions.text` です。

これは、完全なセッションコンテキストより意図的に狭い範囲です。`AGENTS.md`、runtimeのdeveloper instructions、権限、MCP設定、ユーザープロンプト、WithMateのCharacter contextは別の入力として扱います。これらをシステムプロンプトのスナップショットへ混ぜたり、セッション固有の環境値をGitへ保存したりしないでください。

`model_instructions_file` は組み込み指示本文を置き換える設定であり、Character層を追記するだけの設定ではありません。意図した差分をレビューするまでは、WithMate用ファイルに運用上必要なベースライン全体を保持してください。詳細は[OpenAI公式のCodex設定リファレンス](https://learn.chatgpt.com/docs/config-file/config-reference)を参照してください。

## 新しいスナップショットの取得

1. Codexまたはモデルを更新した後に、新しいCodexセッションを開始します。セッションメタデータから、使用中のモデルとCLIバージョンを記録します。
2. rollout JSONLを特定します。次のコマンドは内容を開かずに、候補のうち最も新しいファイルを表示します。

   ```powershell
   $codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
   Get-ChildItem -LiteralPath (Join-Path $codexRoot 'sessions') -Recurse -Filter 'rollout-*.jsonl' -File |
       Sort-Object LastWriteTime -Descending |
       Select-Object -First 1 -ExpandProperty FullName
   ```

3. 新しい日付付きファイルへ取得します。同じ作業用ファイルを意図的に再生成する場合だけ、`-Force` を使います。

   ```powershell
   pwsh ./scripts/capture-codex-system-prompt.ps1 `
       -RolloutPath 'C:\path\to\rollout.jsonl' `
       -OutputPath 'docs/system-prompt/snapshots/YYYY-MM-DD-model.en.md'
   ```

4. 表示された文字数を確認します。rolloutが `session_meta` で始まっていない場合、または `base_instructions.text` を含まない場合、スクリプトは失敗します。
5. 取得後の英語スナップショットは編集しません。取得元が変わった場合は、新しい日付のスナップショットを作成します。

## 改善レビュー

少なくとも月1回、またはCodex CLI、モデル、WithMate統合を更新した後に、このレビューを実施します。

1. 新しい英語スナップショットを前回の記録と比較します。

   ```powershell
   git diff --no-index `
       docs/system-prompt/snapshots/previous.en.md `
       docs/system-prompt/snapshots/current.en.md
   ```

2. 次の領域について、指示の追加、削除、並び替えを確認します。

   - 応答スタイルとユーザー向けの進捗報告
   - ファイル編集、破壊的操作、承認範囲
   - tool、skill、browser、appの扱い
   - 委譲、継続実行、コンテキスト圧縮の挙動
   - 失敗や未確認事項を報告する際の信頼性要件

3. 変更が上流のベースライン変更なのか、WithMate固有の意図したカスタマイズなのかを判断します。両者の判断はGit履歴でも分けて記録します。
4. 新しい英語スナップショットに対応するよう、日本語訳の見出しと規範的な要件を更新します。コード、キー名、パス、コマンドなどの機械可読な文字列は完全に維持します。
5. WithMate用ファイルを独立してレビューします。後から意図的に差分を持たせても構いませんが、各差分にはユーザー向けまたは運用上の具体的な理由を持たせます。
6. モデルまたは取得規約が変わった場合は、`docs/system-prompt/README.md` に新しいスナップショットを記録し、文書の更新をまとめてコミットします。

## WithMate用ファイルの準備

WithMate用の統合ファイルは `.codex/model-instructions-withmate.md`（英語版）と `.codex/model-instructions-withmate.ja.md`（日本語版）です。現時点では取得した英語ベースラインを基に、重複する人格説明、60秒単位の進捗・待機制約、Skill利用時の宣言要件を取り除き、技術者前提の技術コミュニケーションとMermaid利用を反映しています。Character向けの文言調整はまだ行っていません。

今後WithMate用の文言を調整する場合は、次の手順に従います。

1. 現在の英語スナップショットを出発点にします。
2. タスク実行、ファイル安全性、報告、tool利用の要件を維持します。
3. 応答スタイルの変更は、ユーザーに見える自然言語の応答に限定します。Characterの文言をコード、設定例、test、diff、コミットメッセージ、artifact metadataへ入れないでください。
4. 英語版と日本語版を同じカスタマイズ内容として更新し、機械可読な文字列と要件の対応を確認します。
5. 両方のWithMate用ファイルとスナップショットを比較し、適用前にdiffをレビューします。
6. 設定変更後は新しいCodexセッションを開始します。既存セッションでファイルが読み込まれた証拠とはみなしません。

## `config.toml` による適用

WithMate用ファイルをレビューしてから適用します。実際に使うユーザー設定はローカルに置き、認証情報やマシン固有の値とともにコミットしないでください。

### プロジェクト単位の設定

信頼済みのリポジトリで、リポジトリローカルの `.codex/config.toml` を作成または編集します。

```toml
model_instructions_file = "model-instructions-withmate.md"
```

日本語版を使う場合は、上の設定行を次の行に置き換えます。

```toml
model_instructions_file = "model-instructions-withmate.ja.md"
```

このファイルを `.codex/config.toml` と同じディレクトリに置きます。プロジェクト設定内の相対パスは、設定ファイルを含む `.codex/` ディレクトリを基準に解決されます。プロジェクト単位の設定は、プロジェクトが信頼済みの場合だけ読み込まれます。詳細は[OpenAI公式の高度な設定ガイド](https://learn.chatgpt.com/docs/config-file/config-advanced)を参照してください。

### ユーザー単位の設定

同じファイルを複数セッションへ適用する場合は、ローカルの `~/.codex/config.toml` にトップレベルのキーを追加します。Windowsでは、アクティブな `CODEX_HOME` は通常ユーザープロファイル配下です。ファイルがユーザー設定ディレクトリの外にある場合は、checkout済みのWithMate用ファイルを絶対パスで指定します。

```toml
model_instructions_file = "C:\\path\\to\\repository\\.codex\\model-instructions-withmate.md"
```

日本語版を使う場合は、上の設定行を次の行に置き換えます。

```toml
model_instructions_file = "C:\\path\\to\\repository\\.codex\\model-instructions-withmate.ja.md"
```

この設定を読むすべてのセッションで組み込み指示の取得元が変わるため、全体へ有効化する前に適用範囲を確認します。

### 有効化と確認

1. 編集前に、現在のローカル `config.toml` のコピーを保管します。
2. `model_instructions_file` キーだけを追加します。認証情報、MCPのruntime値、無関係な設定をリポジトリへコピーしないでください。
3. 適用対象の信頼済みリポジトリで新しいセッションを開始します。
4. 新しいrolloutの `session_meta.payload.base_instructions.text` を確認し、内容を設定したファイルと比較します。
5. セッションが期待した `AGENTS.md`、権限、WithMate MCPコンテキストを別レイヤーとして引き続き受け取っていることを確認します。
6. 新しいセッションでファイルが読み込まれなければ、overrideを削除し、取得した証拠を保持したうえで、trust、パス解決、profile選択、セッション再起動を調査してから再試行します。

## Gitレビューのチェックリスト

保守更新をコミットする前に、次を確認します。

- 新しい日付付きの英語スナップショットが存在する
- 取得元のモデルとCLIバージョンが記録されている
- 日本語訳の構成が英語原文と対応している
- WithMate用ファイルの差分が意図したもので、diffで確認できる
- rollout履歴、認証情報、runtime環境値、非公開のセッションデータをリポジトリへコピーしていない
- 実際に使う `config.toml` を誤ってstageしていない
