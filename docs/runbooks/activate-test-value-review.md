# テスト価値審査の有効化準備

## 現在の範囲

標準入口は`skills/review-test-value/SKILL.md`の単一審査であり、完了条件は抽出exit `0`と各testの`ACCEPT`である。二段階worker、metadata v2、coordinator、resolution ledger、aggregate gateは有効化していない。

#42の準備として、環境のreadinessを報告するpreflightと、既存v1のmetadata、alignment、deep結果に対するJSON Schema生成を提供する。preflightはworkerを起動せず、審査packetを読まない。実効tool集合と自動注入contextを同じ実行構成で検証する経路が未実装のため、versionやroleを取得できても`BLOCKED`を返す。

#43と#44の実装は未完了である。環境検証だけを済ませれば切替可能な状態ではない。#45は、下記の実装と検証が完了するまで有効化済みとして閉じない。

2026-09-05にWindows nativeのCLI `0.153.4`を調査した。同版の公開sourceでは、[execのJSONL出力](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/exec/src/event_processor_with_jsonl_output.rs#L396)がsession設定からthread IDだけを通知し、実効tool一覧を出さない。[prompt debug](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/core/src/prompt_debug.rs#L101)もinputだけを返す。[設定loader](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/config/src/loader/mod.rs#L528)のuser設定除外はmanaged層の除外を意味しない。このsource調査と現物のversion確認は、現物binaryの実効dispatchやsourceとのビット単位の同値性を証明しない。

## 候補版の明示実行

作業対象のcheckoutをcwdにし、次の入口を使う。live Skillの自動選択を候補版の実行証拠にしない。`<native-codex-executable>`はnpmの`.cmd`や`.ps1`ではなく、そのwrapperが解決するnative executableの絶対pathである。

```powershell
python -X utf8 skills/review-test-value/scripts/preflight_review_worker.py `
  --cli <native-codex-executable> `
  --role-file agents/test_value_luna.toml
python -X utf8 skills/review-test-value/scripts/preflight_review_worker.py `
  --cli <native-codex-executable> `
  --role-file agents/test_value_sol.toml
python -X utf8 skills/review-test-value/scripts/validate_review_result.py --emit-schema metadata
python -X utf8 skills/review-test-value/scripts/validate_review_result.py --emit-schema alignment
python -X utf8 skills/review-test-value/scripts/validate_review_result.py --emit-schema deep
```

preflightのexit `2`は非成功である。roleに書かれたmodelとeffortは要求値であり、実モデルの利用可否や実効設定の証拠ではない。receiptにsecret、role指示全文、raw transcriptを含めない。証拠の保存先は、そのsessionで通知されたSessionFolderとする。

生成schemaは型、enum、必須field、未知field禁止を表す。非空制約、verdict間の条件、record集合と順序、hash、frozen結果の照合は既存validatorが所有する。JSON Schema評価器での成功はCodexの実モデル受理や隔離smokeの成功を証明しない。

## 実装を再開する条件

CLIの[非対話実行](https://learn.chatgpt.com/docs/non-interactive-mode)と[権限](https://learn.chatgpt.com/docs/permissions)を対象版のsource、help、実効出力に照合する。`--ignore-user-config`を指定しただけでmanaged設定、hooks、skills、MCPが除外されたと判断しない。旧`sandbox_mode`と新permission profileを重ねない。

次の順で不足を閉じる。

1. #42: 独立した各`codex exec`と同じ設定読込で、model、effort、permission、公開tool、自動注入元をhostから確認する。確認できない構成はpacket送信前に停止する。親履歴、全checkoutと共通`.git`、認証、親ログ、別phase、MCP、web、shell、追加child、link経由読取に対する直接拒否試験を実装する。
2. #42: stdinでのpacket入力、出力schemaと既存validatorの照合、receipt、有限deadline、cancel時の所有process tree終了、所有scratchだけのcleanupを実装する。version照会のtimeoutをworker lifecycleの検証で代用しない。
3. #43: 2026-09-05に承認された移行専用のv1読取りと、3言語のv2、phase v2、未知boundaryの型付き解消を一体で実装する。対象v1は両modeで移行要求を返し、その場でv2へ書き直して元の選択条件で再抽出する。移行不能時は停止し、v1のまま評価しない。情報不足を推測で埋める自動変換や旧resultの読替えを追加しない。
4. #44: 既存のselector、builder、validator、routingを接続し、全言語と全batch、親riskとmetadata risk、保持根拠、DROP/MOVE resolutionを集計する。ledgerを失った空selectionを成功にしない。未実装の保持根拠やresolutionをcallerのbooleanで代用しない。
5. #45: offline checksと必要なcommit-bound reviewを終え、synthetic repositoryで両Luna phaseとrequired SolのE2Eを行う。Phase 1不合格でもPhase 2を省略しない。mockの成功と実モデルの成功を分けて記録する。
6. #45: task baseとactivation候補commitを固定し、候補自身の新規・変更testを候補版の新方式で審査する。新規sessionで候補版の読込と実効設定を確認した後、検証済みのOS/runtimeに限って標準Skillとaggregate gateを同じリリースで切り替える。

Windows nativeとWSL、Astra parentとGPT-5.6 parentは別の確認範囲とする。WSLへ無断移送せず、auth.jsonをcopyせず、新しい課金APIを導入しない。必要なloginやlive設定の変更は、その操作への明示承認を得る。

## 検証

既存の言語adapter準備と検証はSkillのValidation節を使う。schema検証用依存は独立したPython環境へ導入できる。

```powershell
python -m pip install -r skills/review-test-value/scripts/requirements-test.txt
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_output_schema.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_preflight_review_worker.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_packets.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_result_schema.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_routing.py
```

preflightとschemaのoffline成功は、新方式によるtest価値審査の`PASS`ではない。bootstrap変更は現行SkillのGit modeをtask baseから適用して審査する。activation候補自身の新方式審査は、この旧審査とは別に必要である。

## 切戻し

v2をconsumerへ導入する前なら、対象の準備変更を通常の追加commitで戻し、確認済みの旧入口を維持できる。ユーザーのworktreeをresetせず、無関係な変更を破棄しない。

v2導入後はworkerの新規実行を停止し、v2読取能力、移行専用のv1読取り、未解決ledgerを保持する。未実行を`BLOCKED`として報告し、修正した新経路へ戻す。v1専用extractorへ戻したり、旧単一審査や別modelへsilent fallbackして`PASS`を出したりしない。v2読取とgateの意味を保つ別の変更が必要なら、明示的に設計と承認を行う。

## mainへ統合する前の確認

この作業のtask baseは`f7ba58ae47263c2a6a46d006c92c1d69ec29f704`である。旧bootstrap計画のbaseや移行前mainを価値審査のbaseへ流用しない。Astra側がmainへmerge済みか、squashで履歴が変わったかを確認し、Astra差分を重複してPRに含めない。履歴変更、push、PR公開、mergeはそれぞれ承認されたscopeに限る。
