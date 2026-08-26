#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@'
Implementation restraint:
- 要求された動作と、その正しさに必要な変更だけを実装する。現在の要求に根拠のない抽象化、設定項目、拡張点、将来対応を追加しない。
- 後方互換性は、明示要求、public API、protocol、schema、既知の外部consumerなどaccepted contractに根拠がある場合だけ維持する。根拠がなければ古い経路を残さない。
- fallback、retry、既定値、例外の握り潰しは、accepted contractが要求する場合だけ追加する。検知されるべき失敗を成功に見せかけない。
- testはaccepted behaviorと具体的なfailure modeを検証する。削除状態自体がsecurity、protocolなどのcontractでない限り、「削除した項目が削除され続けること」だけを固定するtestを追加しない。
- scope外のrobustnessやcompatibilityが必要に見える場合は、黙って実装せず根拠とtrade-offをユーザーへ示す。
'@
