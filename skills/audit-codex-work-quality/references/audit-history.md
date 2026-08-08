# Audit history

## 目的

同じUTC半開区間、workspace scope、観点、具体的な問い、analysis contract versionの完了済み監査を再利用し、別観点または別questionは独立して分析する。履歴DBは既定で`$CODEX_HOME/audit-codex-work-quality/history.sqlite3`へ置く。

## 観点

既存rubricへ対応する場合は、次の`focus_key`を優先する。

- `goal-artifact-alignment`
- `defect-contract-discovery`
- `finding-recurrence`
- `fix-complexity`
- `validation-directness`
- `review-validity-noise`
- `user-steering`
- `permanent-rule-proportionality`
- `change-proportionality`
- `exception-reachability`
- `root-cause`

別の観点はlowercase英数字とhyphenで安定したkeyを作る。`focus_question`には今回答える具体的な問いを入れる。意味の近さを推測して既存questionへ統合しない。

## 入力方法

`scripts/audit_history.py`はstdinから一つのJSON objectを受け取る。PowerShellでは外部processへの文字化けを避けるため、実行前に次を設定する。

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
```

## Lookup and claim

`lookup`はread-onlyで、DBが存在しない場合も作成しない。`claim`だけが対象行を作成する。

```json
{
  "start": "2026-08-01T20:00",
  "end": "2026-08-02T04:00",
  "timezone": "Asia/Tokyo",
  "workspace": "<absolute workspace path or null>",
  "focus_key": "review-convergence",
  "focus_question": "なぜreview findingが収束しなかったか"
}
```

`claim`では同じfieldに、1回のclaim試行で固定する`claim_key`を追加する。response loss時は同じkeyを再利用する。明示的な再分析だけ`force_reason`を追加する。

```powershell
$request | ConvertTo-Json -Depth 10 | python scripts/audit_history.py lookup
$claim | ConvertTo-Json -Depth 10 | python scripts/audit_history.py claim
```

- `action=reuse`: 保存済み結果を使い、collectorを起動しない。
- `action=busy`: 同じ対象を別runが分析中である。重複着手しない。
- `action=claimed`: 返された`run_id`と元の`claim_key`を保持して分析する。
- `action=terminal`: 同じ`claim_key`のpartial / failed / abandoned runがある。新しい分析には新しいkeyを使う。

複数観点では観点ごとにlookup / claimする。reuse済み観点を再分析せず、claimedな観点だけを今回のscopeにする。collector証拠はclaimed観点間で共有してよい。

## Heartbeat, complete, and fail

長い収集・PR確認・分析phaseの境界でheartbeatする。

```json
{"run_id":"<run id>","claim_key":"<claim key>"}
```

```powershell
$heartbeat | ConvertTo-Json | python scripts/audit_history.py heartbeat
```

完了結果は次のallowlistだけを保存する。配列は値がない場合も空配列を渡す。`interventions`はユーザーが改善案を求めた場合だけ値を入れる。

保存CLIが検証するのはfield、型、件数、長さ、全体byte数である。自由文の意味や出典は機械判定しないため、`summary`を含む許可済みfieldにもsession/event本文、command/output、raw error、PR・review本文、absolute workspace pathを転載せず、分析後のuser-facing projectionだけを渡す。

```json
{
  "run_id": "<run id>",
  "claim_key": "<claim key>",
  "result": {
    "summary": "観点に対する短い結論",
    "confidence": "high|medium|low|unknown",
    "finding_families": [],
    "good_decisions": [],
    "data_gaps": [],
    "interventions": [],
    "outcome_context_checked_at_utc": "2026-08-08T12:00:00Z"
  }
}
```

```powershell
$result | ConvertTo-Json -Depth 10 | python scripts/audit_history.py complete
```

監査を完了できない場合は、raw errorを入れずboundedなcodeとsummaryでclaimを閉じる。

```json
{
  "run_id": "<run id>",
  "claim_key": "<claim key>",
  "failure_code": "evidence-unavailable",
  "failure_summary": "必要な証拠を取得できなかった"
}
```

同じresultまたはfailureでの再送はidempotentに成功し、異なる内容への書換えは拒否する。履歴write失敗時は分析結果を返してよいが、履歴未記録と次回の重複抑止gapを明示する。
