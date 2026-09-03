#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

@'
Implementation restraint:
- code、test、compatibility、fallback、config、abstractionを追加する前に、現在の要求、accepted contract、観測済みfailure modeのどれが根拠かを特定する。根拠がなければ追加しない。
- 追加前にcanonical ownerと既存helper / patternを探し、次にstandard library、native platform、導入済みdependencyを使う。現在のscopeをそれらで素直に満たせない場合だけ新しいabstractionやdependencyを作る。
- canonical ownerで最も単純な完全解を実装する。並行経路、shim、flag、「将来のため」のscaffoldingを足すより、既存経路の変更または削除を優先する。ただし最小diffを理由に症状だけをpatchしたり、同じownerの経路を不整合なまま残したりしない。
- 後方互換性、旧実装の経路、互換性維持を目的とするshim、adapter、二重read / write、fallbackは原則として追加または維持しない。
- 互換性対応なしでは現在の要求が成立せず、具体的な外部consumerまたはmigration要件を確認できる場合だけ、必要性、対象範囲、trade-off、撤去条件を示し、その作業に対するユーザーの明示承認を得てから実装する。既存codeやtest、過去の挙動、有益そうという推測は必要性または承認の根拠にしない。
- failureは観測可能に保つ。specific errorへcontextを加える、またはsystem boundaryで明示的に変換する処理はよい。retry、fallback、既定値は明示された既知のrecoverable failureにだけ使い、失敗をsuccess-shaped resultへ変えない。
- checkはaccepted behaviorと具体的なfailure modeをstable observable boundaryで検証する。absence自体がsecurity、protocol、data-loss preventionなどのcontractでない限り、削除済みbehavior、実装詳細、absenceだけを固定するtestを追加しない。
- trust boundaryのinput validation、security、accessibility、data-loss prevention、明示要求までYAGNIで削らない。scope外のrobustnessやcompatibilityが有益に見える場合は、黙って実装せず根拠とtrade-offを示す。
'@
