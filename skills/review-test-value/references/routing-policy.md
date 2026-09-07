# Review Routing Policy v2

## Deep routing

通常gateのdeep reviewは、後続の意味審査がgate、actual boundaryまたは削除・移設
resolutionを変更できるrecordだけをrequiredにする。次の条件を満たす場合に
requiredにする。

- Phase 1が`NEEDS_CONTEXT`
- Phase 2が`RECHECK`
- Phase 2がbounded contextを要求する
- metadataの`kind = "security"`
- metadataまたは親workflowのrisk tagが空でない

Phase 1が`REDESIGN`でも、metadataだけを根拠にPhase 2を省略しない。Phase 2は
actual boundaryとDROP／MOVE resolutionを確定できるため、全recordで実行対象に
する。Phase 2の結果が固定された後、hostが`terminal = true`を付与できるのは、
Phase 2が`RECHECK`でない状態でPhase 1が`REDESIGN`、またはPhase 2が`MISMATCH`
のrecordだけである。terminal recordはrisk tagやaudit選択があっても通常gateの
deep reviewへ送らない。`REDESIGN`と`RECHECK`の組み合わせは、deep reviewが
actual boundaryまたは必要なresolutionを確定できるため例外としてrequiredに
できる。metadataが`NEEDS_CONTEXT`でもPhase 2が`MISMATCH`なら、alignmentが
boundaryを確定したterminal recordとして扱う。

deterministic auditは通常gateのrequired条件ではない。audit選択は独立artifact
のための決定論的な`audit_selected`信号として保持し、auditのfailureや未実行を
対象recordの通常gateへ伝播させない。

risk tagは`security`、`authentication`、`authorization`、`billing`、`irreversible-data-loss`、`privacy`だけを認める。metadataと親workflowのtagは和集合にし、metadataから親tagを解除できない。親workflowのrisk contextはrouting manifestとは独立した`review-workflow-context-v1` artifactとして`record_id`と`metadata_hash`へ固定する。未知のtag、型不一致、record IDまたはhash不一致はrouting前に拒否する。

required agentがunavailableなら親agentは代行せず、`NEEDS_CONTEXT`、`BLOCKED`とする。

audit selectionは`record_id`とcontract versionのSHA-256を100で割った剰余が`audit_percent`未満かで決める。同じ入力は常に同じ結果になる。候補版のaudit計算には`deep-review-v3`を渡す。workflow context自体のshape/versionはv1のままとする。

`review_routing.py`のinputは`records`と`workflow_context`を持つJSON objectとする。各routing recordは`record_id`、`metadata_hash`、`source_hash`、`contract_version`、`metadata`、Phase 1とPhase 2のverdict、`context_requirements`を持つ。`workflow_context`は`review_contract_version = "review-workflow-context-v1"`と同順の`records`を持ち、各entryは`record_id`、`metadata_hash`、`parent_risk_tags`、`audit_percent`だけを持つ。outputのrouting manifestは`review_contract_version = "review-routing-v2"`と同順の`records`を持ち、各entryへrecord identity、workflow contextのhash、routing resultを固定する。routing resultの`terminal`はalignment後にhostが付与するcanonical stateであり、model outputではない。`audit_selected`はselectionを表すが、`required`や`reasons`へauditだけの理由を追加しない。

deep packet builderとfinal aggregatorは、alignment packet、固定済みPhase 1 result artifact、Phase 2 result、manifestとは独立したworkflow contextからrouting resultを再計算する。alignment packetの`metadata_result_hash`と埋め込みreviewを元artifactへ照合する。record ID、metadata hash、source hash、verdict、context requirement、workflow context hash、risk context、audit選択、required判定のいずれかが一致しないmanifestを拒否する。callerが渡した`sol_required` booleanだけでdeep reviewやgateを省略しない。

既存artifactの`sol_required`、`sol_verdict`、`sol_result`はdeep phaseを指すschema名として維持する。modelの選択やSolへの呼出しを意味しない。

## Status

ADR-0022の優先表を、host-owned `terminal`の先行確定と組み合わせて適用する。`terminal = true`のPhase 1 `REDESIGN`またはPhase 2 `MISMATCH`は、required deep reviewerが未実行でも`REDESIGN`を維持する。その他のrequired deep reviewerのunavailable・schema不正・`NEEDS_CONTEXT`は`NEEDS_CONTEXT`とする。deep reviewerは固定済みの`REDESIGN`または`MISMATCH`を救済しない。

## Disposition

- `declaration`: `MOVE_TO_POLICY_CHECK`
- `implementation`: 有効なtemporary条件があれば`KEEP_TEMPORARY`、それ以外は`DROP`
- `consumer`、`public-boundary`、`component-behavior`: `permanent`かつ保持根拠ありなら`KEEP_PERMANENT`、保持根拠なしなら`DROP`、有効なtemporary条件があれば`KEEP_TEMPORARY`
- actual boundaryまたは保持根拠が未確定なら`null`

現在のtestはmetadata v2を審査する。正常な歴史的v1削除は[alignment契約](alignment-review-contract.md#歴史的v1削除)のDROP／MOVEと解消確認を使う。v2では、`characterization`は`expires_on`または`review_when`、`ephemeral`は`remove_when`をtemporary条件とする。記載された条件が現在も有効かはhostの保持根拠確認が必要であり、期限文字列の存在だけで運用上のPASSを出さない。

保持根拠の入力は`PRESENT`、`ABSENT`、`UNRESOLVED`とし、AIの自由記述から推測しない。`UNRESOLVED`は`disposition = null`、`status = NEEDS_CONTEXT`、`gate = BLOCKED`へ閉じる。

## Gate

- `NEEDS_CONTEXT`: `BLOCKED`
- `REDESIGN`: `CHANGES_REQUIRED`
- `ACCEPT`でdispositionが`null`またはartifact stateが不可能: `BLOCKED`
- `KEEP_PERMANENT`かつpermanent test: `PASS`
- `KEEP_TEMPORARY`かつ有効なtemporary test: `PASS`
- `MOVE_TO_POLICY_CHECK`または`DROP`で元testが残る: `CHANGES_REQUIRED`

resolution ledgerと元test削除後の`PASS`はactivation changeで有効化する。Bootstrap validatorは対応resolutionを受け取らず、削除済みartifactを`PASS`にしない。

final aggregatorのinputは完全な`alignment_packet`、同じrecord集合と順序の固定済み`metadata_result`と`alignment_result`、検証対象のcanonical `deep_packet`、独立した`workflow_routing_context`、検証対象の`routing_manifest`、required record集合とdeep packet hashへ結合した`sol_result`または未実行を表す`null`、同じrecord集合と順序の`retention_records`だけを持つ。正規artifactをrecordごとに分割しない。metadata verdict、alignment verdict、deep required、deep verdict、actual boundary、metadataを独立したscalarとして再入力しない。

`terminal = false`のrequired recordに対応するdeep resultがない場合、またはdeep verdictが`NEEDS_CONTEXT`の場合は、dispositionを計算せず`NEEDS_CONTEXT / null / BLOCKED`へ短絡する。`terminal = true`の`REDESIGN`または`MISMATCH`はdeep resultの有無より先に`REDESIGN`を確定する。
