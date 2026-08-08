# ADR-0014: 観点別の作業品質監査履歴を専用SQLiteへ保存する

- Status: accepted
- Date: 2026-08-08
- Supersedes: none

## Context

固定区間の作業品質監査を繰り返す際、前回どの観点をいつ分析し、どの結論になったかを参照できないと、同じ区間と観点の証拠収集・分析を重複して実行する。一方、同じ区間でも観点や具体的な問いが異なれば、新しい分析として扱う必要がある。

ADR-0009は、WithMate DB、Codex rollout、GitHub、repositoryをread-onlyで収集し、raw evidenceを既定で永続化しない境界を定めている。この境界を維持しつつ監査結果だけを再利用するには、source evidenceと履歴のowner、保存内容、同一性、並行実行、失敗時の扱いを分離する必要がある。

## Decision

- source evidenceのcollectorはread-onlyのまま維持し、監査履歴は別の専用SQLite DBへ保存する
- 履歴DBの更新にはPython標準`sqlite3`を使い、WithMate DBの読み取りは引き続き`sqlite3 -readonly`と`PRAGMA query_only=ON`を同じconnectionで使う
- 監査対象の同一性は、UTC半開区間、privacy-safeなworkspace scope digest、安定した観点key、正規化した具体的な問い、analysis contract versionの組で決める。hash一致時にもcanonical identityを照合する
- 完了済みで固定区間も`complete`な結果だけを再利用する。`partial`、`failed`、`abandoned`は後続分析を抑止しない
- 分析開始前に対象をclaimし、同じ対象のactive claimを一つに制限する。claimには有限leaseとheartbeatを持たせ、期限切れclaimを置換した後のlate completionを拒否する
- 保存する結果はboundedなuser-facing構造化要約に限定する。保存CLIはfield、型、件数、長さ、全体byte数を検証し、監査workflowがsemantic projection boundaryとしてsession/event本文、cue、command/output、raw error、stderr、PR diff、review/comment本文、absolute workspace pathを許可済み自由文fieldへ転載しない。自由文の意味や出典を保存CLIが推測してDLPすることは契約に含めない
- schema version、入力field、文字列・配列・result・DBの上限を固定し、future schema、partial schema、corruption、上限超過では自動repairやtruncateをせず停止する
- DB更新は`BEGIN IMMEDIATE`とforeign key検証を使い、claim、state transition、result確定をatomicにする。response loss時はclaim keyまたはresult digestでidempotentに再送できるようにする
- 自動prune、端末間同期、raw report exportは行わない。必要になった場合は別の保存・削除・共有契約として設計する

## Alternatives

- WithMate Memoryへ保存する: 固定区間・観点・run stateの一意性とatomic claimを機械的に保証する正本ではないため採用しない
- repository内のMarkdownへ保存する: user-privateな横断履歴がrepositoryごとに分散し、dirty worktreeや誤commitを生むため採用しない
- Skill directoryへJSONLを追記する: Skill更新とruntime stateが混在し、並行claim、idempotent transition、schema migrationを安全に扱いにくいため採用しない
- 分析完了後だけ結果を記録する: 並行した二つの監査が同時に未分析と判断でき、重複着手を防げないため採用しない
- raw final reportを保存する: 再利用に不要なsource evidenceや機密情報を新しい集積先へ複製するため採用しない

## Consequences

- Positive: 同じ区間・scope・観点・問いの重複着手と重複分析を抑止できる
- Positive: 同じ区間でも別観点または別questionは独立して分析でき、前回の関連結果も参照できる
- Positive: source evidenceのread-only境界と履歴writeのownerが分離される
- Positive: partial、failure、crash、response loss、並行実行を明示的なstate transitionとして扱える
- Negative: 監査workflowにlookup、claim、heartbeat、complete / failの状態管理が加わる
- Negative: lease期間を超える長時間監査ではheartbeatが必要になる
- Negative: 自動pruneを行わないため、上限到達時は別途明示的なretention判断が必要になる
- Follow-up: 端末間同期、retention、外部共有が必要になった場合だけ、privacyとmigrationを含む別契約として設計する

## Executable Anchors

- Source: `skills/audit-codex-work-quality/scripts/audit_history.py`
- Tests / types / schemas / static checks: `skills/audit-codex-work-quality/scripts/test_audit_history.py`
- Workflow contract: `skills/audit-codex-work-quality/SKILL.md`
- Collection boundary: `docs/adr/0009-bounded-audit-evidence-collection.md`
