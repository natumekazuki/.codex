# WithMateの環境固有設定（記入例）

このファイルは配布用の例です。利用するときは自分の環境用に編集し、`~/.codex/withmate.local.md` として保存します。既存のlocalファイルを上書きせず、他製品へは自動同期しません。認証値・Session URL／tokenは記載しません。

## Worktree

- Worktree root: 未設定。この環境の絶対pathを記入する。
- repositoryの分類: 既存配置・明示規約を踏襲する。例として `WithMate: Electron`、`ExampleApp: .net/MAUI` は、その環境で確認できた場合だけ採用する。
- 明示した例外: 必要な場合だけ記入する。SessionFolder・Crew Folderはworktreeのrootにしない。

## 利用経路

以下は選定開始値の例であり、契約・利用承認そのものではありません。利用するものと従量利用の条件を記入します。

- 新規WithMate子の既定: Codexの契約枠。
- ほかの候補: Claudeの契約枠、OpenCode Go／Free、登録済みOpenAI API。
- API従量・有料追加枠の条件: この環境での許可範囲を記入する。課金・Extra Usage設定は自動変更しない。

## Model／Depthの選定基準

WithMateの通常子とnativeサブエージェントの対象を区別して記入します。IDとDepthは対象Workspaceの実カタログで確認し、nativeの固定role・許可model・tool制限は別に守ります。

| 用途 | 優先する候補・理由 | Depthの目安 |
| --- | --- | --- |
| 一般調査・実装 | 例: Sol。広い文脈と一般判断 | 対応する既定、またはmedium |
| 手順が確定した反復作業 | 例: Luna、Goの定型処理向け候補 | Lunaではhighを開始候補にし、Modelごとに確認 |
| 視覚・文章・検証可能な局所修正 | 例: Terra。入力と確認方法が明確 | 対応する既定、またはmedium |
| 難しい設計判断・反例 | 例: Astra。必要な問題へ限定する | low／medium等から必要な判断に合わせる |
| Claudeを使う仕事 | 例: Sonnetを一般作業、Opusを難しい判断の候補にする | 対応する既定、またはmedium |
| 新Model・未評価の候補 | 公式用途・必要能力と実績を確認して選ぶ | 未対応値を補わず、実候補から選ぶ |

## カタログ資料（任意）

取得時点・対象Workspace・取得元と、Provider／model ID／対応Depth／用途判断を必要な範囲で記載します。観測値は選定方針と分け、古い一覧を現在の `session.get_catalog` より優先しません。提供・料金・権限・起動成功を一覧掲載だけで保証しません。
