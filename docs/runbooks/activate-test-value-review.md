# テスト価値審査の候補実行と有効化

## 現在の状態

[Issue #52](https://github.com/natumekazuki/.codex/issues/52)の候補を作成中である。必須test価値審査の有効化とlive配布は未完了。旧Issueは再開しない。現在mainにあるv2抽出、Git transition、packet、validator、Sol選定、retention／resolutionを再利用し、残るworkerとcoordinatorを[Issue #50](https://github.com/natumekazuki/.codex/issues/50)で接続する。

今回のtask baseは`81b1ee740ab1ab7ad3eff98e66663ba23ea556e0`。着手時のmainと一致することを確認した。以後の別taskはその開始時のbaseを使い、この値や過去taskのbaseを流用しない。

候補Skillを別のCodex homeから`debug prompt-input`へ読み込ませた確認では、必須審査・監査・RelayGraphが通常一覧に入り、明示呼出し専用のUI・文書3種類は一覧から外れた。roleの実モデルsmokeは独立CLI runが終了したものの、JSONLには空のreceiverを持つwaitだけが記録され、spawnやchild modelの証拠を取得できなかった。最終応答の自己申告だけでrole実効確認を完了扱いしない。

同版app-serverの新規threadで、候補natural-japaneseを`turn/start`の`type: skill`入力として渡す確認も行った。user itemにtextとskillが記録され、明示したlight推敲が完了した。通常一覧からの除外と明示呼出しの成立を分けて確認したもので、全任意Skillや汎用childの確認を代替しない。`codex exec`のplain textに`$Skill名`を書くだけでは、このstructured inputと同じ確認にならない。

## 実行境界

専門Lunaのmetadata／alignmentと必要なSolは、それぞれ独立した新規Codex CLI runとする。model／effort／role指示は`agents/test_value_luna.toml`と`agents/test_value_sol.toml`を正本とする。通常の子のfork、親の自己評価、別modelへのfallbackは隔離審査の代行にならない。

metadata phaseは正規metadataだけを受け取る。本文・locator・親履歴・別phase・ログ・Memory・MCPから補完できないよう、user／project／managed config、AGENTS、Skill、hook、tool、network、shellの自動入力と読取経路を確認する。`--ignore-user-config`だけで全入力が消えるとは仮定しない。管理者の安全policyは維持し、必要な境界を確認できない場合はpacket送信前にBLOCKEDとする。

実装の対応範囲はWindows native CLI `0.153.4`、既存ChatGPT Pro認証に限定する。同版のcloud-config eligibilityではProが取得対象外であることをsourceで確認した。管理configの存在、未確認の認証種別・CLI版では送信前に停止する。認証は既存CLIのChatGPTログインを使い、auth.jsonのコピーや新たな課金APIを導入しない。入力はstdin等のdataとして渡す。正式な起動設定・CLI identityと合成canaryの強制読取拒否を確認し、存在しないJSONL fieldをpreflightの要件にしない。

2026-09-06の既存試行では、Windows native CLI `0.153.4`のelevated sandboxでLuna/medium・Sol/xhighの合成canary読取がAccess denied、command exit 1となった。これは指定pathの拒否を示し、worker全体や全自動入力の隔離を証明するものではない。今回、合成した認証拒否testをcoordinatorの一つの入口から実行し、Luna/mediumのmetadata・alignment、riskで必要となるSol/xhigh、host保持根拠、aggregate PASSまで接続した。各phaseは独立runでcanary拒否とtool item 0件を確認した。これは合成例の機能確認であり、この変更自身の審査や後続のworker修正の証拠へ付け替えない。

## 完了判定

候補の一回の入口で、task baseとsnapshot固定、全対象言語の抽出、Luna両phase、決定論的なrequired Sol、hostが実際に確認した保持根拠、既存ledgerのDROP／MOVE解消、全体gateを接続する。metadataがREDESIGNでもalignmentを省略しない。元の判定は固定し、削除・移設後の解消を別の結果として扱う。

全言語・全batch・現在のrecord・未解決義務が揃って初めてPASSとする。空selection、消えたledger、別snapshotのreceipt、構文validatorの正常終了を全体PASSにしない。終了契約は0=PASS、1=CHANGES_REQUIRED、2=BLOCKED。実行不能、不正JSON/hash、timeout/cancel、途中失敗は非成功として伝える。

保持の意味判断はhostがsourceとaccepted contractを読んで行う。oracle.refの存在、callerのPRESENT=true、modelの自由出力だけで保持を承認しない。追加contextは限定した内容とref/hashに結び付ける。初期予算は同時worker1、通常audit10%、Solの追加context再実行最大1回とし、最適値とは表現しない。

`--prepare`はhost evidenceの雛形と、recordに対応するpath・symbol・claimを返す。repositoryの根拠には`source = repository`／`authority = repository`を付ける。hostが実際に取得した外部Issue・契約・明示要求には`source = host-observed`と対応するauthority（`issue`／`external-contract`／`explicit-user-requirement`）を付け、本文・hash・意味判断を渡す。外部根拠を保持のためだけにrepositoryへ複製しない。

再開時は返された`unresolved`から不足するcontextと元recordを確認する。本文とmetadataを同時に修正し自動対応できない場合は、`supersessions`へ旧generation／recordと新recordのidentity、保持される契約の根拠と`SUPPORTED`判断を渡す。現在の新規審査がPASSであることを別途確認し、同名という理由だけで旧義務を消さない。DROP／MOVEは`resolution_attempts`と既存ledgerで解消する。

Solの入力が800,000文字を超える場合は、全対象・routing・auditを固定した後、record順を保つ連続batchへ事前分割する。各batchの結果と実行証拠を検証し、全件を集約した結果の由来をgenerationへ保存する。CLI 0.153.4の入力上限は1,048,576文字であり、800,000文字はモデルのtoken上限への適合を保証しない初期予算である。単独recordでも予算を超える場合や途中batchが失敗した場合は、対象を削らずBLOCKEDとする。Lunaの各phaseは単一packetであり、入力を処理できなければ非成功として返す。

stateの書込みが途中で終わり未公開generationが残った場合は、記録を無視して続行せず停止する。

## 検証と切替

既存の直接checkは[SkillのValidation](../../skills/review-test-value/SKILL.md#validation)を使う。offlineの成功と、Windows／CLI／modelを特定した実モデルE2Eを分ける。旧preflightはversionとroleのreadinessを返すだけで、exit 2のBLOCKEDは成功ではない。

workerの入力隔離、全phaseと必要Sol、保持・削除・移設、途中失敗、timeout/cancelと所有process・scratchの終了を直接確認する。この変更自身の対象testも同じtask baseから候補の新方式で審査する。自己検証の成功だけをsandboxの証拠にしない。

候補の実行と自身の審査、新規sessionでの読込確認が揃ってから、Skillの標準入口とAGENTSの完了条件を全体gateへ揃える。未確認のOS／runtimeには成功を広げない。AGENTS・role・Skill・hookを整合した単位でliveへ適用し、実config全体を上書きしない。

## 切戻し

必須審査に障害があればBLOCKEDとして修復する。親をSolへ変更しても審査は省略しない。適用済みの既知の差分だけをレビュー可能な形で戻し、ユーザーworktreeをresetしない。v2利用後にv1専用extractorへ戻さず、v2読取能力と未解決ledgerを保持する。
