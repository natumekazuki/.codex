# Metadata Review Contract v1

## Purpose

Phase 1は、test sourceを見ずに`@test-value` metadataが自己完結した検証上の主張かを審査する。sourceから意味を補完してはならない。

## Input

packetは`review_contract_version = "metadata-review-v1"`と`records`を持つ。各recordは次だけを持つ。

- `record_id`: locatorとmetadata hashから決定論的に作るopaque ID
- `metadata_format_version`: Bootstrapでは`1`
- `metadata`
- `metadata_hash`

packetへsource path、line、symbol、source text、source hash、assertion summary、production source、oracle本文、実行証拠を含めない。未知のkey、重複record、metadata hash不一致はAI審査前に拒否する。

## Review

- `claim`が成立と不成立を区別できるか。
- `oracle`が現在の実装結果を正解として循環していないか。
- `failure_mode`が具体的な欠陥と観測可能な影響を示すか。
- `claim`、`failure_mode`、`scope`が同じ契約境界を扱うか。
- lifecycleが主張の目的と整合するか。

test本文があれば判断できる、という理由で不足を補完しない。不足がmetadata自身の再設計を要する場合は`REDESIGN`、boundedな追加contextでmetadata単体の意味を確定できる場合は`NEEDS_CONTEXT`とする。

## Output

```json
{
  "review_contract_version": "metadata-review-v1",
  "reviews": [
    {
      "record_id": "sha256:...",
      "metadata_hash": "sha256:...",
      "verdict": "VALID",
      "evidence": [
        {
          "fields": ["claim", "failure_mode", "scope"],
          "finding": "COHERENT_BOUNDARY"
        }
      ],
      "unverified": ["oracle.refの本文"],
      "next_action": null
    }
  ]
}
```

`verdict`は`VALID`、`REDESIGN`、`NEEDS_CONTEXT`のいずれかとする。`metadata_hash`は入力recordと一致させる。`evidence`はmetadata field pathと定義済みfindingだけを持つ構造化objectの配列とし、自由文やsource fieldを根拠として受理しない。`NEEDS_CONTEXT`は`unverified`と`next_action`へ必要な追加sourceを具体的に示す。全recordを一度ずつ返し、追加・欠落・重複を認めない。

`finding`は`SELF_CONTAINED_CLAIM`、`CONCRETE_FAILURE_MODE`、`COHERENT_BOUNDARY`、`LIFECYCLE_ALIGNED`、`ORACLE_DECLARED`のいずれかとする。`fields`は入力metadataに存在するtop-level field、`oracle.type`、`oracle.ref`だけを参照できる。`VALID`と`REDESIGN`は一件以上の`evidence`を必要とする。

Phase 1を実行するruntimeは、履歴を継承しない新規childとrepositoryを読めない強制権限境界を提供しなければならない。agent instructionや`read-only` sandboxだけではmetadata-only境界を満たさない。runtime smokeでこの境界を確認できるまで二段階workflowを有効化しない。
