# Subagent role比較runbook

## 目的

model変更をtoken削減とみなす前に、同じtask classとrouting条件で品質、親の再作業、token、latencyを比較する。単一runでは既定roleを変更しない。

## 比較単位

- requirements、observable outcome、semantic owner、targeted checkが同程度に確定したtaskを使う
- task class、routing mode、child数、review triggerを揃える
- `focused_implementer`と`implementer`を各task classで複数run実行する
- sourceを再利用する場合は同じbase stateから開始し、片方の結果をもう片方へ渡さない

## 記録項目

```text
Task class / run ID:
Base source identity:
Routing mode / selected role / child count:
Review trigger:
Parent input / cached input / output tokens:
Child role input / cached input / output tokens:
Parent + all children total tokens:
Parent repair: changed lines or hunks / additional turns:
Targeted check first-run result:
Blocking findings / validation gaps:
Wall-clock time:
Quality notes and accepted residual risk:
```

raw tokenとdurationはsession logから取得し、比較用の集計はIssueまたはtask-local benchmark recordへ置く。Hookへrole固有の計測workflowを追加しない。

## 判定

- 親子合計tokenだけでなく、親の修正量、追加turn、validation、findingを同時に見る
- 品質低下、blocking finding増加、または親の再作業増加がtoken差を相殺するtask classでは`implementer`を維持する
- 複数runで同じ傾向が出たtask classだけ、`focused_implementer`を継続候補とする
- reasoning effortやreviewer modelを変更する場合は、別の比較seriesとして記録する
