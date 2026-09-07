# 単一test価値review candidateの有効化

## 状態と変更範囲

`test-value-review-v3`はcandidateであり、明示起動だけで利用する。AGENTSのactive条件とSkillの`allow_implicit_invocation: false`は変更しない。旧metadata/alignment/deepのE2Eや審査結果をv3の証拠として流用しない。

本candidateはmain `0fc8abbe64227458ba1f111bbca92516f350b826`から単一の意味reviewへ置き換えたもの。以後の実装・自己審査では、そのtask開始時のbaseを使う。取り除いた旧phase、routing、hash chaining、通常canary/auditへの互換layerはない。旧candidate stateの変換や自動再利用もしない。

## 実行境界

モデル・effortは既存のLuna/maxを維持し、`agents/test_value_luna.toml`を正本とする。deep roleは廃止する。metadataだけを隔離する別phaseはなく、metadata・source・bounded contextを同じinputで読む。モデルに公開するtoolはない。

現時点のnative worker対応範囲はWindows、Codex CLI 0.153.4、既存ChatGPT Pro認証。managed configを含む未確認の環境、未知のCLI版・認証種別は停止する。role、contract、実行file、設定、tool無効化は送信前に決定論的に確認する。preflightの`--version`はLLM callではない。モデル接続のためのhost通信と、モデルによるtool/network操作を混同しない。

```powershell
python -X utf8 skills/review-test-value/scripts/preflight_review_worker.py `
  --cli <absolute-codex.exe> --role-file <absolute-test_value_luna.toml>
```

`ready=true`は起動前条件を満たすという意味だけで、実モデルE2Eや有効化の成功ではない。通常batchには合成canaryを入れない。実filesystem拒否を追加確認する場合は、明示的なruntime smokeとして、そのCLIが提供するsandboxの正式な操作で実施する。未検証のpermissionやtool集合を確認済みとしない。

## Offline確認

既存CIはPython/TypeScript/C#の抽出とGit selection、単一responseの型/ordinal、host gate、再開、並列batch、Windowsの所有process終了を確認する。通常のCIに認証や有料model実行を追加しない。

```powershell
python -m pip install -r skills/review-test-value/scripts/requirements-test.txt
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_single_review.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_worker.py
```

多言語adapterは既存の依存準備と`test_extract_test_values_multilang.py`を使う。旧phaseのschema組合せtestは新しいflat schema・ordinal・gateのtestへ置き換え、旧API互換のためには残さない。値の型/ordinal異常、input不足、host証拠不足が成功へ変換されないことを確認する。

## 明示的な実モデルE2E

認証済みWindows端末で、次を明示的に実行する。環境変数がない通常CIではskipする。これは合成testの意味reviewであり、毎回のcanaryではない。

```powershell
$env:TEST_VALUE_LIVE_E2E = '1'
$env:TEST_VALUE_CODEX_EXE = '<absolute-codex.exe>'
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_live_e2e.py
Remove-Item Env:TEST_VALUE_LIVE_E2E
Remove-Item Env:TEST_VALUE_CODEX_EXE
```

さらにcandidate自身の新規・意味変更・削除testを、[Skill](../../skills/review-test-value/SKILL.md)のprepare→host evidence→通常実行で審査する。実行結果をmodel自己申告だけで判断せず、現在のinput snapshot、CLI/role/contract、call数、canonical resultと最終gateを照合する。旧多段candidateでの審査成功を付け替えない。

新規sessionで候補Skillの明示呼出し、現在のrole読込、必要なhost context作成、NEEDS_CONTEXT後の対象recordだけの再reviewを確認する。失敗の分類、timeout/cancel、複数batchの一部失敗、削除/移設の現artifact確認も対象にする。

## 有効化条件

- flat schemaとhost ordinalが一致し、通常fresh runのcall数が`ceil(records / batch-size)`である。
- toolsなしの単一review、bounded input、有限deadlineが実環境で成立する。
- candidate自身を新方式でreviewし、必要なdirect checkと全体gateを満たす。
- 新規sessionの明示呼出しとreadinessを確認し、未実施のOS/model/認証へ成功を広げない。
- 上記が揃ったときだけ、registry/Skillのpolicy、README、AGENTSのactive条件、runbook状態を整合した変更で切り替える。

今回のLinux上のoffline結果だけでは上記を満たさない。Draft PRの未確認範囲を解消するまでcandidateのままにする。品質や消費量の改善を、call数やコード量の削減だけから達成済みと断定しない。

## 証拠と切戻し

記録するのは公開可能なcommit、CLI/OS、role/model/effort、実施check、call数、gate、未確認範囲だけ。raw prompt、source本文、private path、認証、モデル出力全文を恒久logやPRへ保存しない。task-localのcanonical stateは義務の再開に必要な最小情報だけを保持する。

旧candidate stateは保全し、v3用に新しいtask directoryで同じ固定baseから全対象と削除義務を再確認する。旧taskの継続成功とは表現しない。v3 stateが失われたときは所有markerを消して回避せず、原本を復旧する。新契約が有効化できない場合はactiveにせず修復し、旧phaseや別モデルへのsilent fallbackを作らない。ユーザーworktreeと既存認証を変更・削除しない。
