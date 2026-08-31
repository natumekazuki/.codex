# Review Routing Policy v1

## Sol routing

次のいずれかに該当するrecordはSol reviewをrequiredにする。

- Phase 1が`NEEDS_CONTEXT`
- Phase 2が`RECHECK`
- Phase 2がbounded contextを要求する
- metadataの`kind = "security"`
- metadataまたは親workflowのrisk tagが空でない
- deterministic audit対象

risk tagは`security`、`authentication`、`authorization`、`billing`、`irreversible-data-loss`、`privacy`だけを認める。metadataと親workflowのtagは和集合にし、metadataから親tagを解除できない。親workflowのrisk contextは`record_id`と`metadata_hash`へ固定する。未知のtag、型不一致、record IDまたはhash不一致はrouting前に拒否する。

high-riskでもaudit対象でもない明白な`REDESIGN`または`MISMATCH`だけを理由にSolへ送らない。required agentがunavailableなら親agentは代行せず、`NEEDS_CONTEXT`、`BLOCKED`とする。

audit selectionは`record_id`とcontract versionのSHA-256を100で割った剰余が`audit_percent`未満かで決める。同じ入力は常に同じ結果になる。

`review_routing.py`のinputは`records`配列を持つJSON objectとする。各recordは`record_id`、`metadata_hash`、`source_hash`、`contract_version`、`metadata`、`parent_risk_context`、Phase 1とPhase 2のverdict、`context_requirements`、`audit_percent`を持つ。outputは`review_contract_version = "review-routing-v1"`と同順の`records`を持つrouting manifestであり、各entryへrecord identity、親risk context、audit率、routing resultを固定する。

deep packet builderとfinal aggregatorは、alignment packetと固定済みPhase 1 / Phase 2 resultからrouting resultを再計算する。record ID、metadata hash、source hash、verdict、context requirement、risk context、audit選択、required判定のいずれかが一致しないmanifestを拒否する。callerが渡した`sol_required` booleanだけでdeep reviewやgateを省略しない。

## Status

ADR-0022の優先表をそのまま適用する。未完了・schema不正、required Solのunavailable・schema不正・`NEEDS_CONTEXT`を最優先で`NEEDS_CONTEXT`とする。Solは固定済みの`REDESIGN`または`MISMATCH`を救済しない。

## Disposition

- `declaration`: `MOVE_TO_POLICY_CHECK`
- `implementation`: 有効なtemporary条件があれば`KEEP_TEMPORARY`、それ以外は`DROP`
- `consumer`、`public-boundary`、`component-behavior`: `permanent`かつ保持根拠ありなら`KEEP_PERMANENT`、保持根拠なしなら`DROP`、有効なtemporary条件があれば`KEEP_TEMPORARY`
- actual boundaryまたは保持根拠が未確定なら`null`

Bootstrapはmetadata v1を読む。`characterization`は`expires_on`または`review_when`がある場合だけtemporary条件が有効である。v1の`ephemeral`は削除条件を表現できないため、temporary条件未確定として`null`にする。v2の`remove_when`対応はactivation changeで追加する。

保持根拠の入力は`PRESENT`、`ABSENT`、`UNRESOLVED`とし、AIの自由記述から推測しない。`UNRESOLVED`は`disposition = null`、`status = NEEDS_CONTEXT`、`gate = BLOCKED`へ閉じる。

## Gate

- `NEEDS_CONTEXT`: `BLOCKED`
- `REDESIGN`: `CHANGES_REQUIRED`
- `ACCEPT`でdispositionが`null`またはartifact stateが不可能: `BLOCKED`
- `KEEP_PERMANENT`かつpermanent test: `PASS`
- `KEEP_TEMPORARY`かつ有効なtemporary test: `PASS`
- `MOVE_TO_POLICY_CHECK`または`DROP`で元testが残る: `CHANGES_REQUIRED`

resolution ledgerと元test削除後の`PASS`はactivation changeで有効化する。Bootstrap validatorは対応resolutionを受け取らず、削除済みartifactを`PASS`にしない。

final aggregatorのinputは、一つのalignment packet `record`、同じrecordの`alignment_review`、検証対象の`routing_manifest`、requiredな場合の`sol_result`または未実行を表す`null`、`retention_basis`、`artifact_state`だけを持つ。metadata verdict、alignment verdict、Sol required、Sol verdict、actual boundary、metadataを独立したscalarとして再入力しない。
