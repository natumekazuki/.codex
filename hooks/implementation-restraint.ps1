#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@'
Implementation restraint:
- code、test、compatibility、fallback、config、abstractionを追加する前に、現在の要求、accepted contract、観測済みfailure modeのどれが根拠かを特定する。根拠がなければ追加しない。
- 追加前にcanonical ownerと既存helper / patternを探し、次にstandard library、native platform、導入済みdependencyを使う。現在のscopeをそれらで素直に満たせない場合だけ新しいabstractionやdependencyを作る。
- canonical ownerで最も単純な完全解を実装する。並行経路、shim、flag、「将来のため」のscaffoldingを足すより、既存経路の変更または削除を優先する。ただし最小diffを理由に症状だけをpatchしたり、同じownerの経路を不整合なまま残したりしない。
- failureは観測可能に保つ。specific errorへcontextを加える、またはsystem boundaryで明示的に変換する処理はよい。retry、fallback、既定値は明示された既知のrecoverable failureにだけ使い、失敗をsuccess-shaped resultへ変えない。
- checkはaccepted behaviorと具体的なfailure modeをstable observable boundaryで検証する。absence自体がsecurity、protocol、data-loss preventionなどのcontractでない限り、削除済みbehavior、実装詳細、absenceだけを固定するtestを追加しない。
- trust boundaryのinput validation、security、accessibility、data-loss prevention、明示要求までYAGNIで削らない。scope外のrobustnessやcompatibilityが有益に見える場合は、黙って実装せず根拠とtrade-offを示す。
'@
