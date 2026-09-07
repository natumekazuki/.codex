# テスト価値審査の候補実行と有効化

## 現在の状態

`review-test-value` はcandidateであり、repositoryの必須gateとして公開していない。現在は`$review-test-value`による明示起動だけを許可し、通常の自動選択、test変更への暗黙適用、live配布は行わない。このcheckoutでは、Windows native CLI `0.153.4`と既存ChatGPT Pro認証による22件以上の実モデルE2E、candidate自身の審査、新規Codex sessionでの読込確認をまだ実施していない。有効化済みとは報告しない。

activeな必須gateへ切り替える条件は次のとおりである。

1. 固定した一つのselection全体（手動で1件ずつに分割しない）を、Windows native CLI `0.153.4`、既存ChatGPT Pro認証、Luna/maxの実モデルで22件以上審査する。全batchを集約した終了契約が、規定のphase deadline内に`PASS`、`CHANGES_REQUIRED`、`BLOCKED`のいずれかを返すことを確認する。
2. このcandidateの変更自身を、同じreview契約とtask baseから自己審査する。offline test、合成canary、`BLOCKED`の返却は実モデルE2Eの代わりにしない。
3. 新規Codex sessionでSkillの読込、candidateの明示起動、実効roleと入力隔離を確認する。
4. 上記の証拠と回帰checkを揃え、実際のregistryでactiveへ変更する。active登録、hook／AGENTS／Skillの条件文、runbookの状態記述は同じ変更で更新する。

`config/agents.example.toml`の`test_value_luna`／`test_value_deep`はrole設定例であり、実runtimeのlive登録を証明しない。実際のregistryが確認できない間は、候補の状態を維持する。

候補実装の追跡は[Issue #52](https://github.com/natumekazuki/.codex/issues/52)、workerとcoordinatorの接続は[Issue #50](https://github.com/natumekazuki/.codex/issues/50)で行う。旧Issueは再開しない。

## 共通batch・deadline policy

metadata、alignment、deepは同じbatch policyを使う。coordinatorはselectionを固定し、record順を保つ連続batchを全phaseについて決定する。

| 項目 | policy |
| --- | --- |
| 1 batchのrecord数 | 最大10件 |
| 1 batchの入力サイズ | canonical packetのUnicode文字数で最大800,000文字。prompt wrapper、system instruction、実行時の追加文は数えない |
| 境界 | record数とcanonical packet文字数の両方を満たす最大の連続範囲。単独recordが文字数上限を超えた場合は対象を削らず`BLOCKED` |
| batch順 | selectionのrecord順を維持し、欠落・重複・順序変更を許さない |
| batch時間 | metadataは300秒、alignmentは600秒、deepは900秒。canary最大120秒、cleanup最大5秒を含む |
| phase全体 | `ceil(N / C) × B + 固定10秒`。`N`はbatch数、`C`は解決済み同時実行数、`B`はphaseのbatch時間 |
| worker同時実行 | `--batch-concurrency auto`（default）は`C=N`、正の整数は`C=min(指定値,N)` |
| audit | 10% |
| deep retry | 最大1回 |

workerへ渡すbatch deadlineは、coordinatorのphase plan開始時に取得したmonotonic anchorからの絶対deadlineである。同一phaseではrecord順の連続batchをwaveに分け、wave内のworkerを同時に開始し、全workerのcleanup直後に次waveへ進む。phase planのstartを`P`、batch予算を`B`、batch `i`（0始まり）、解決済み同時実行数を`C`、batch開始を`S_i`とすると、batch deadlineは`min(S_i + B, P + (floor(i / C) + 1) × B)`、phase全体のdeadline offsetは`ceil(N / C) × B + 10秒`とする。同じselection、canonical packet、policyからこのrelative offsetを決定論的に計算する。monotonic anchorそのものは実行ごとに異なるため、異なるrunの絶対時刻を比較しない。metadata→alignment→deepはphase単位で順次実行する。phaseの時計はplan実行開始から進み、git抽出、host evidence準備、依存準備などplan前の処理をphase deadlineへ含めるとは表現しない。

一つのbatchではcanary、review、cleanupが同じmonotonic deadlineを共有する。canaryの経過時間を差し引いた残り時間だけをreviewへ渡し、canaryからreviewへの切替でdeadlineを延長しない。deadline到達時は所有process treeとscratchを終了・削除し、cleanupの終了確認に失敗した場合も成功扱いにせず、専用reason codeを持つ`BLOCKED`にする。local executor／runtimeのspawn失敗もsanitizedな`BATCH_EXECUTION_FAILED`として`BLOCKED`にする。waveが失敗したら後続waveを開始せず、開始済みの兄弟workerのcleanupを待つ。`BLOCKED`は入力indexが最小の失敗を返し、`completed_batches`は同じwaveの兄弟を含む検証済み成功数を数える。

metadata packetをfreezeしてからmetadataのbatch planを確定し、metadata resultをfreezeしてからalignment planを確定する。deep planはmetadata／alignment resultとroutingをfreezeしてから確定する。全batchについてrecord ID、metadata／source hash、件数、順序、結果の完全性を集約時に検証する。一つでもbatchが失敗、timeout、cleanup失敗、欠落、重複、順序不整合になれば、成功batchだけで全体を`PASS`にしない。各phaseの実行前にsanitizedな`execution-plan-{phase}.json`を保存し、最初の失敗は`last-failure.json`へ、既存の失敗がある場合は`failure-<hash>.json`へ診断を残し、以前の記録を上書きしない。validator failureはpacket本文や機密情報を返さず、sanitized detailsにphase、record ID、違反種別、不正fieldを含める。

### phase別予算を変更した再測定

`--metadata-batch-seconds`、`--alignment-batch-seconds`、`--deep-batch-seconds`は各30〜1,800秒の整数を受け付ける。defaultはそれぞれ300／600／900秒。`--batch-concurrency`は`auto`（default）または1以上の整数を受け付ける。boolean・非数値・0・負数・範囲外はpacket送信前に拒否する。時間変更用の環境変数や自動倍増は用意しない。

2026-09-07の従来構成の実測ではmetadataの10／10／2件は完了したが、alignment batch 0（10件、39,924文字）は300秒で`REVIEW_TIMEOUT`となった。process終了と計画・失敗診断の保存は確認できた。alignment 600秒の逐次完了とauto並列の実モデル完了は未確認であり、次の明示指定で再測定する。

```powershell
python -X utf8 skills/review-test-value/scripts/run_test_value_review.py `
  --root <repository-root> --changed-from <task-base> `
  --state-dir <new-state-directory> --cli <native-codex-executable> `
  --host-evidence <host-evidence-json> --alignment-batch-seconds 600 `
  --batch-concurrency auto
```

`--prepare`にも同じ秒数と`--batch-concurrency`を渡す。22 recordsが3batchのalignmentでは、defaultのauto（`C=3`）のoffsetは`ceil(3 / 3) × 600 + 10 = 610秒`、明示`--batch-concurrency 1`の逐次offsetは`3 × 600 + 10 = 1,810秒`である。autoでは1 wave、明示上限がbatch数より小さい場合だけwaveを分け、wave内の全workerのcleanup後に余分な待機を挟まず次waveへ進む。時間予算はcanary・review・cleanupで共有する。

指定した全phaseの値をtask manifestの`execution_policy`／`execution_policy_hash`、各計画の`batch_seconds`／解決済み`batch_concurrency`／`execution_policy_hash`／`plan_hash`へ固定する。`auto`はexecution policyでは`null`としてhashし、planには実行時の解決値を保存する。generationのtoolchain identityにもpolicyを含める。policyの異なる既存state、またはpolicy未記録の旧stateは`STATE_EXECUTION_POLICY_MISMATCH`で停止し、計画も失敗記録も変更しない。再計画は新しいstate directoryで明示実行する方式に限定する。元のstateや未解決義務を消して完了扱いにはしない。

新しいtimeout診断はphase、batch index、batch count、completed batch count、packet hash、`batch_seconds`、policy／plan hashを含む。600秒でもtimeoutすれば`BLOCKED`を保存し、並列度の自動縮小、追加延長、batch workerの無条件retryは自動実行しない。native workerは`multi_agent`を無効にした独立CLIであり、`spawn_agent`のsubagent枠やcapacity signalを使わないため、親の枠を理由にした自動縮小もない。

## 実行境界

Luna/maxによるmetadata／alignmentと必要なdeep reviewは、それぞれ独立した新規Codex CLI runとする。model／effort／role指示は`agents/test_value_luna.toml`と`agents/test_value_deep.toml`を正本とする。workerは`multi_agent`を無効にした独立native CLIを起動し、`spawn_agent`のsubagent枠やcapacity signalを使わない。通常の子のfork、親の自己評価、別modelへのfallbackは隔離審査の代行にならない。

metadata phaseは正規metadataだけを受け取る。本文・locator・親履歴・別phase・ログ・Memory・MCPから補完できないよう、user／project／managed config、AGENTS、Skill、hook、tool、network、shellの自動入力と読取経路を確認する。`--ignore-user-config`だけで全入力が消えるとは仮定しない。管理者の安全policyは維持し、必要な境界を確認できない場合はpacket送信前に`BLOCKED`とする。

対応範囲はWindows native CLI `0.153.4`、既存ChatGPT Pro認証に限定する。管理configの存在、未確認の認証種別・CLI版では送信前に停止する。認証は既存CLIのChatGPTログインを使い、auth.jsonのコピーや新たな課金APIを導入しない。入力はstdin等のdataとして渡す。正式な起動設定・CLI identityと合成canaryの強制読取拒否を確認し、存在しないJSONL fieldをpreflightの要件にしない。

保存schemaの`sol_result`等とtoolchainの`workers.sol`はdeep phaseの既存識別子であり、Solを呼ぶ設定ではない。role・contractのhashが変わるため、旧modelのgenerationを新構成の実行証拠として再利用しない。

## 履歴（有効化の証拠ではない）

以下は候補開発時の記録であり、現在のactive登録、実モデルE2E、または新規session確認の証拠へ流用しない。

2026-09-07、C# test変更22件で`--prepare`はselection、snapshot hash、host evidence requirementを生成したが、metadata phaseは約4分30秒後に`BLOCKED`（`REVIEW_RESULT_VALIDATION_FAILED`、unavailable field）となった。同じ差分の別sessionでも失敗し、stateには失敗recordのID、参照field、sanitized resultが残らなかった。test suite、抽出、host evidence固定は成功しており、test実行失敗とは独立した事象である。

2026-09-06以前のcandidate smokeでは、独立CLIのJSONLに実効spawn／child modelの証拠がなく、別の合成canaryでは読取拒否を確認した。これらは入力隔離やLuna/maxの実効起動を証明せず、現在のactivation条件を満たす証拠へ流用しない。旧候補のtask baseやSkill discoveryの記録も履歴としてのみ保持する。

## 完了契約

candidateの一回の入口で、task baseとsnapshot固定、全対象言語の抽出、metadata／alignment、決定論的なrequired deep review、hostが実際に確認した保持根拠、既存ledgerのDROP／MOVE解消、全体gateを接続する。metadataが`REDESIGN`でもalignmentを省略しない。元の判定は固定し、削除・移設後の解消を別の結果として扱う。

全言語・全batch・現在のrecord・未解決義務が揃って初めて`PASS`とする。空selection、消えたledger、別snapshotのreceipt、構文validatorの正常終了を全体PASSにしない。終了契約は0=`PASS`、1=`CHANGES_REQUIRED`、2=`BLOCKED`。実行不能、不正JSON／hash、timeout／cancel、途中失敗は非成功として伝える。

保持の意味判断はhostがsourceとaccepted contractを読んで行う。`oracle.ref`の存在、callerの`PRESENT=true`、modelの自由出力だけで保持を承認しない。追加contextは限定した内容とref／hashに結び付ける。

`--prepare`はhost evidenceの雛形と、recordに対応するpath・symbol・claimを返す。repositoryの根拠には`source = repository`／`authority = repository`を付ける。hostが実際に取得した外部Issue・契約・明示要求には`source = host-observed`と対応するauthority（`issue`／`external-contract`／`explicit-user-requirement`）を付け、本文・hash・意味判断を渡す。外部根拠を保持のためだけにrepositoryへ複製しない。

再開時は返された`unresolved`から不足するcontextと元recordを確認する。本文とmetadataを同時に修正し自動対応できない場合は、`supersessions`へ旧generation／recordと新recordのidentity、保持される契約の根拠と`SUPPORTED`判断を渡す。現在の新規審査がPASSであることを別途確認し、同名という理由だけで旧義務を消さない。DROP／MOVEは`resolution_attempts`と既存ledgerで解消する。

stateの書込みが途中で終わり未公開generationが残った場合は、記録を無視して続行せず停止する。

## 検証と切替

既存の直接checkは[SkillのValidation](../../skills/review-test-value/SKILL.md#validation)を使う。offlineの成功と、Windows／CLI／modelを特定した実モデルE2Eを分ける。旧preflightはversionとroleのreadinessを返すだけで、exit 2の`BLOCKED`は成功ではない。

candidateの回帰checkでは、batch境界、解決済み`C`、record／hash／順序の集約、canaryからreviewへの残り時間、process treeとscratchのcleanup、schema variantとsanitized validation diagnostics、途中batchの失敗を確認する。22件以上のselectionを一つの固定runでWindows native CLIへ渡し、手動分割なしに規定のphase deadline内で終了契約を得る。1件、上限ちょうど、上限超過、22件、100件、および文字数境界のoffline fixtureは、実モデルE2Eの代わりにしない。

22件のport入力検証fixtureは、coordinatorへ`--alignment-batch-seconds 600 --batch-concurrency auto`を明示指定し、alignmentのphase offset 610秒とbatch 0の完了まで検証する。Windowsで既存のChatGPT Pro認証を用い、次のopt-in実行で再現する。通常CIではモデルを呼ばない。fixture自体の22件のassertion、抽出、`10 + 10 + 2`の分割はofflineで確認できるが、このcheckoutではauto並列の実モデルrunは未実施である。

```powershell
$env:TEST_VALUE_E2E_CLI = 'C:\path\to\codex.exe'
$env:TEST_VALUE_E2E_STATE = 'C:\review-evidence\batch-e2e'
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_live_e2e.py
```

指定先はcheckout外の絶対pathとする。実行ごとにfixture repository・state・`e2e-summary.json`を保持する。新規Codex sessionから同じコマンドを実行し、各runのplanとterminal gateを比較する。このopt-in E2Eは`--batch-concurrency auto`を固定し、小さい22件fixtureの各phase最大3batch、deep retryなしを前提に、外側watchdogを`(300 + 10) + (600 + 10) + (900 + 10) + 180 = 2,010秒`とする。180秒はGit／preflight／最終保存の固定余裕であり、workerのdeadlineを延長しない。各runでは実際に生成されたphase planの時間合計とも照合する。preflight・canaryだけの失敗やskipを実モデルE2E成功と扱わず、モデル審査後の`BLOCKED`も品質確認・有効化の完了とは区別する。auto並列のWindows実モデルE2Eはこのcheckoutでは未実施であり、candidateは引き続き必須gateにしない。

Luna/maxの実効起動を全phaseで確認し、循環したoracle、本文以上の過大主張、mockによるSUTの置換、必要contextの欠落を誤承認しないか、正常例とともに確認する。所要時間・利用量も記録し、旧Sol構成と同等の精度や週枠削減を未測定のまま保証しない。

candidateの22件以上の実モデルE2E、candidate自身の審査、新規sessionでの読込確認、registryの実効状態確認が揃っていないため、現時点では切替を保留する。条件が揃った場合だけ、registryのactive登録と本runbookの「現在の状態」を同じ変更で更新し、必須gateとして公開する。未確認のOS／runtimeには成功を広げない。

## 切戻し

必須審査に障害があれば`BLOCKED`として修復する。active化後の障害ではregistryをcandidate／明示起動へ戻し、runbookと条件文を同じ変更で更新する。親をSolへ変更しても審査は省略しない。適用済みの既知の差分だけをレビュー可能な形で戻し、ユーザーworktreeをresetしない。v2利用後にv1専用extractorへ戻さず、v2読取能力と未解決ledgerを保持する。
