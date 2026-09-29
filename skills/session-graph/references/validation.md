# 配置・受入確認

本Skillと保存helperの変更・配置時に、必要な範囲で行う。配布元のテスト成功を、配置先のモデル動作確認に読み替えない。

## 配置

`skills/session-graph/`をディレクトリごと、現在のruntimeが探索するSkill置き場へ既存のコピー／link方式で配置する。`SKILL.md`だけでなく`agents/`、`assets/`、`scripts/`、`references/`を揃える。共通AGENTS.mdは従来どおり`~/.codex/`、hookは有効なCodex homeへ配置し、`/hooks`で変更後のtrustと重複を確認する。既存config全体や他のSkillは上書きしない。

新規sessionの一覧でSkillの実path・発見・重複を確認する。`UserPromptSubmit`と`SessionStart`のstartup／resume／compactで短い入口が届くことを確認する。hookにはSessionFolderの独自フィールドを仮定せず、モデルが現在の提供済みSession情報から解決する。WithMateでは`# SessionFolder`を利用する。手動Compactとターン途中の自動Compactの両方で、同じpathを復元できるか実環境で確認する。

`PreCompact`のstdoutに意味内容の保存を依存させない。`Stop`は追加しない。hook発火は記録の正しさの証明ではない。契約は[Codex Hooks](https://developers.openai.com/codex/hooks)、探索とmetadataは[Codex Skills](https://developers.openai.com/codex/skills)で利用バージョンと照合する。

## 保存helper

```powershell
python -X utf8 -m unittest discover -s skills/session-graph/scripts -p "test_*.py"
python -X utf8 -m py_compile skills/session-graph/scripts/session_graph.py
```

競合時のexit 3、保存失敗後の旧内容保持、初回の同時作成、ロック待ちの打切り、プロセス中断後の解放を確認する。Windows／Linuxは実際に動かした環境を区別する。正本の構文・要求の意味はこのテストの対象ではない。

## モデルとユーザー向け表示

代表ケースを使い、最初から完成記録を渡すだけでなく**指示を記録するところから**確認する。

| ケース | 確認 |
| --- | --- |
| 配置・操作・禁止・対象外を含む依頼 | 作業前に各条件が残り、AI案と区別される |
| 途中で訂正・一部撤回・追加 | 古い条件と二重有効にならず、無関係な要求を失わない |
| 設計相談／read-only review | 記録だけが許可され、ソース・外部writeへ権限が広がらない |
| 実装済み・検証未実施の状態から再開 | 未検証を完了にせず、必要な確認を選ぶ |
| MainとAuxiliaryから同じFolderへ並行更新 | 同じ手順で保存し、競合時に双方の条件を残して再適用する |
| 手動／自動Compactとresume | 要約だけでなく現在のSession情報と最新グラフから復元する |
| 読込不能・消失・不正ファイル・保存失敗 | 空図で隠さず未記録を明示する |
| 未完了あり／対象外の会話 | 前者は残件を記録して終了し、後者は不要なファイルを作らない |

[表現例](../assets/example.mmd)と実作業のグラフを既存のMermaidレンダラーで表示する。短いラベルから要求を識別でき、実装済みと検証済み、依存先、判断待ちを見分けられるかを実際に見る。複数機能に増えた場合の交差・過密・文字量も確認する。構文検証だけで視覚確認済みにしない。表示経路がない場合は不足を記録し、WithMate専用ビューアの開発をこの変更へ混ぜない。

実施結果と未実施の環境・経路は既存のPR／作業報告へ残す。常設の採点基盤、監査エージェント、別台帳は追加しない。
