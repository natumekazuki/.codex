# WithMateの環境設定とProvider・Model・Depth選定

子Sessionの実行設定を選ぶとき、native委譲の環境固有方針を確認するとき、またはworktreeを準備するときに読む。3製品はそれぞれ自分の配置内で完結し、他製品の実設定をimport・自動同期しない。

## Git管理外の環境固有ファイル

現在の製品の `~/.codex/withmate.local.md` があれば、関係するWorktree root・利用経路・Model／Depthの選定基準を読む。`~` は実行環境のユーザーhomeへ解決し、cwdや別checkoutで代用しない。存在しない場合は今回の指示・既存規約・下記の基本線で決まる作業を進め、結果を左右する未設定・矛盾だけ確認する。アクセス失敗を「設定なし」と扱わない。

[withmate.example.md](../../withmate.example.md)は編集用の例であり、コピー前から有効な設定ではない。localファイルはMarkdownの判断材料で、nativeの設定形式や実カタログを置換する機械configではない。必要なら配置先へ新規作成し、既存内容を無断で上書きしない。開発worktree内のlocalファイルとユーザーhomeへの実配置を区別する。

環境固有に定義できるものは次のとおり。

- Worktree root、既知のrepository分類、配置先の例外。
- 利用する契約枠・API経路、従量利用の条件、用途ごとの優先順位。
- 一般実装、定型処理、視覚・文章、難しい設計判断等へのModel選定基準とDepthの目安。
- 必要な場合だけ、取得元・時点・対象Workspaceを明記したローカルの候補一覧と実測上の所見。

今回の明示指定はlocalの既定より優先する。local方針は共通の選定開始値を調整できるが、操作承認・認可・sandbox・native担当の制限、必須確認を緩めない。指定と実カタログが食い違えば推測で補わず、影響する選択だけ確認する。ファイルの存在・編集自体をAPI利用許可や課金設定変更とみなさない。

`withmate.local.md` はGit管理外とし、認証値、Session URL／token、Memory、実行履歴を入れない。モデル候補や環境値の更新のために追跡対象の例・共通guideを書き換えたり、独自の同期・台帳・自動配布を追加したりしない。

## カタログを構築・利用する

候補の正本は、子の実際のWorkspaceを指定した `session.get_catalog`。Providerを省略すれば全Providerを取得できる。許可された利用経路の候補全体を確認し、localの用途・選定基準と照合する。別Workspaceのcache、公式の発売情報、native roleの一覧をその子の利用可能一覧と同一視しない。

| WithMate Provider | 選ぶ単位・主な利用経路 | Depthの扱い |
| --- | --- | --- |
| `codex` | Codexの契約枠。返却されたmodel IDを使う | そのmodelの `reasoningEfforts` から選ぶ |
| `claude` | Claudeの契約枠。返却されたalias・完全IDをそのまま使う | SDKが返す対応effort。aliasの表示名や既定を推測しない |
| `opencode` | `opencode-go/...`、Freeの `opencode/...`、登録済みOpenAI APIの `openai/...` 等、許可済みの経路 | native variantがDepth。model IDへ `#variant` を付けず別項目で渡す |

OpenCodeのnative配信元はmodel IDの一部であり、WithMate Providerを `openai` や `opencode-go` に変えない。Freeという名前だけで現在の料金・利用条件を保証せず、契約とnative情報を確認する。同じModelでも契約枠とAPI従量、Goと別の有料配信経路は区別する。

カタログにはProvider・完全な選択ID・対応Depth・用途の選び方を揃える。候補を手元に残す場合はlocalファイルの資料部分に置き、観測値と希望する選定方針を分ける。未評価の候補も消さず、用途未評価として扱う。取得失敗、正常な空一覧、非対応の空Depth、未許可の経路を区別する。APIが未提供ならsource・native一覧の確認までとし、WithMateでの作成・起動確認を済ませたとは扱わない。

## 選ぶ順序と用途

1. Worker／個別統括の責務と、必要な成果・判断・検証方法を決める。
2. ユーザー指定と環境固有の利用方針に従い、許可された経路からProviderを選ぶ。指定がない新規のWithMate子はCodexを基本とする。Claude・OpenCode等へ切り替える根拠は用途、利用方針、消費枠、手戻りであり、安価さだけでは決めない。
3. 候補全体を用途と照合し、適切なModel・Depthを直接選ぶ。上位Modelを使う前に下位Modelを失敗させる工程は設けない。
4. `session.create_child` へProvider・Model・Depth・Workspaceと、許可済みapproval／sandboxの実値を指定する。起点Sessionの設定はユーザーが選び、既存Sessionへの追加依頼は受付時点の受信側設定で実行される。

次は選定基準を作るための基本線であり、特定環境のallowlist・性能比較の実測ではない。利用可能な同等候補を含めて選び、ローカルの優先順位・実績で具体化する。

| 成果に必要な判断 | 候補を選ぶ基準 |
| --- | --- |
| 手順・期待結果が決まった抽出、変換、照合、設計済み実装 | Luna、HaikuやGo／Freeの定型処理向け候補。未解決の設計・安全判断を小さい作業という理由で押し込まない |
| 画像・画面読解、素材に基づく文章、検証可能な局所修正 | Terra等、必要な入力modality・toolを扱える候補。モデル名だけで画像対応を推測しない |
| 広い調査、一般の設計・実装・debug・review | Sol、Sonnet等、広い文脈と判断を保てる候補。Goの一般実装候補も利用方針・確認結果に応じて選ぶ |
| 要件の衝突、難しいtradeoff・反例、長期の複合判断 | Astra、Opus等の判断向け候補。名前や価格だけで品質を保証しない |
| 未評価の新Model・旧世代・preview・特殊用途 | 現行Modelと同等とは扱わず、公式の用途・必要な能力・既存評価を確認する。指定や比較目的がある場合も必要な検証を省略しない |

公式の用途案内: [OpenAI Models](https://learn.chatgpt.com/docs/models)、[OpenAI Model selection](https://learn.chatgpt.com/docs/model-selection)、[Claude Models](https://platform.claude.com/docs/en/models/overview)、[OpenCode Go](https://opencode.ai/docs/console/go/)。製品の公式推奨と、この環境で採用した選定基準は分ける。

## Depth

Depthは親がその依頼の不確実性・判断の重さ・完了条件から選ぶ。routineで結果をすぐ確認できる作業は浅め、複数の資料・依存・edge caseを判断する作業は深めを候補にする。固定対応表を全Modelへ強制しない。

- 対応Depthが空ならDepthなし。未指定を表す値は現在の契約に従う。V7の `reasoningEffort: ""` は未指定であり、文字列 `none` は実際に候補にある場合だけ使う。
- `medium` がないModelへ他製品の既定を移さない。`thinking` 等の任意のvariantも、対応候補と意味を確認して使う。`high` 等の同名値をModel間の能力・消費の等価値としない。
- localに指定した目安が未対応なら、選び直しが方針内で可能か判断し、未合意の切替は確認する。失敗を隠すModel・Provider・課金経路の自動fallbackは作らない。
- 認証、課金、Extra Usage、native実設定は別の操作である。カタログの取得や選定だけを理由に変更しない。

参考: [Codex reasoning effort](https://learn.chatgpt.com/docs/models#pick-a-reasoning-effort)、[Claude effort](https://code.claude.com/docs/en/model-config#adjust-effort-level)、[OpenCode variants](https://opencode.ai/docs/models/#variants)、[WithMateカタログ契約](https://github.com/natumekazuki/WithMate/blob/0bb78dd03cdf58e19776df188346fbdeb9712b72/src-shared/session/session-management-contract.ts)。
