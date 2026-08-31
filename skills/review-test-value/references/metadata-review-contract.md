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
      "verdict": "VALID",
      "evidence": ["claimは失敗条件を区別している"],
      "unverified": ["oracle.refの本文"],
      "next_action": null
    }
  ]
}
```

`verdict`は`VALID`、`REDESIGN`、`NEEDS_CONTEXT`のいずれかとする。`NEEDS_CONTEXT`は`unverified`と`next_action`へ必要な追加sourceを具体的に示す。全recordを一度ずつ返し、追加・欠落・重複を認めない。
