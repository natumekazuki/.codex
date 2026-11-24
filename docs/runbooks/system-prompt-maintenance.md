# Codex system promptの保守

この配布物は `model_instructions_file` を設定する場合の**完全な置換本文**です。Characterの差分や共通AGENTS.mdへのリンクだけに取り替えると、元の作業・安全・tool・Skill契約も失われます。共通規約の改訂とベースラインの更新を分けて扱います。[資産の所在](../system-prompt/README.md)・[Codex設定リファレンス](https://learn.chatgpt.com/docs/config-file/config-reference)

## 配布する英語版・日本語版を変える時

[英語版](../../.codex/model-instructions-withmate.md)と[日本語版](../../.codex/model-instructions-withmate.ja.md)に同じ判断を反映し、変更前後で要件と機械向け文字列を照合します。特に、依頼・訂正・Compact後の継続、read-onlyと変更の違い、他者差分・破壊操作の保護、tool・Skillの読み方、進捗と最終回答が両方で機能する範囲を確認します。Characterと成果物の区別は[WithMate利用guide](../guides/withmate.md#character表現の適用範囲)で定めます。

組み込み由来の変更と意図したカスタマイズは、理由と差分がGit履歴で区別できるようにします。配布本文の編集だけなら新しい取得版を作らず、以前のsnapshotを現行説明に合わせて改稿しません。

## ベースラインの取得・更新

月次、またはCodex CLI・モデル・WithMate統合の更新時に、使用中のベースラインとの差を確認します。上流本文を取り直す場合は、置換設定のない新規Sessionを使い、対象モデル・CLI版とrolloutを特定します。最新日時だけで目的のSessionとみなしません。

```powershell
pwsh ./scripts/capture-codex-system-prompt.ps1 `
    -RolloutPath 'C:\path\to\rollout.jsonl' `
    -OutputPath 'docs/system-prompt/snapshots/YYYY-MM-DD-model.en.md'
```

[取得script](../../scripts/capture-codex-system-prompt.ps1)は先頭の `session_meta.payload.base_instructions.text` を抽出します。本文のないrolloutや別種のレコードを代用しません。出力と取得元のモデル・CLI版を確認し、rolloutそのものや非公開の環境情報を保存しません。

取得した原文は変更せず、前版と比較して対応する訳を作ります。置換本文に反映すべき変更と独自差分を見極め、参照も揃えます。ベースラインが交代した時だけ、役割を終えた原文と訳を現行配布から外します。

## 任意の適用と確認

[設定例](../../config.example.toml)の指定先は英語版です。日本語版を選ぶ時は `model-instructions-withmate.ja.md` に差し替え、二つを連結しません。端末への適用は配布元の編集と別です。

- 信頼済みプロジェクトの `.codex/config.toml` では、その設定ファイルと同じディレクトリに置いた本文をトップレベルの `model_instructions_file = "model-instructions-withmate.md"` で選べます。相対pathとtrustの条件は[高度な設定ガイド](https://learn.chatgpt.com/docs/config-file/config-advanced)を参照します。
- ユーザー単位では、その端末が使う設定に対象ファイルの絶対pathを指定します。この設定を読む全Sessionに影響するため、範囲と既存値を確認し、必要なキーだけ扱います。認証・MCP・個人設定を配布元へ取り込みません。

適用後は新しいSessionのrolloutで `base_instructions.text` を指定ファイルと比較します。AGENTS.md・Character・権限・MCPは別レイヤーとして確認します。設定例・ファイル一致だけで既存Turnへの適用や挙動の改善とは判断しません。不一致ならtrust・path・profileと起動したSessionを切り分け、意図しない置換は元の設定へ戻します。
