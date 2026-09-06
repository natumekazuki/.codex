# Metadata Review Contract v2

## Purpose

Phase 1は、test sourceを見ずに`@test-value` metadataが自己完結した検証上の主張かを審査する。sourceから意味を補完してはならない。

## Input

packetは`review_contract_version = "metadata-review-v2"`と`records`を持つ。各recordは次だけを持つ。

- `record_id`: locatorとmetadata hashから決定論的に作るopaque ID
- `metadata_format_version`: 現在のtestは`2`。正常なGit削除元に限り`1`。
- `metadata`
- `metadata_hash`

packetへsource path、line、symbol、source text、source hash、assertion summary、production source、oracle本文、実行証拠を含めない。未知のkey、重複record、metadata hash不一致はAI審査前に拒否する。

## Review

- `claim`が成立と不成立を区別できるか。
- `oracle`が現在の実装結果を正解として循環していないか。
- `fault`が具体的な欠陥を示し、`observable`が直接読む対象を示すか。
- `claim`、`fault`、`observable`、`observation_boundary`、`scope`が同じ契約境界を扱うか。
- lifecycleが主張の目的と整合するか。

test本文があれば判断できる、という理由で不足を補完しない。不足がmetadata自身の再設計を要する場合は`REDESIGN`、boundedな追加contextでmetadata単体の意味を確定できる場合は`NEEDS_CONTEXT`とする。

## 歴史的v1削除

`metadata_format_version = 1`はbuilderがGit transitionの削除元として検証した旧metadataである。元の`claim`、`failure_mode`、`oracle`、`scope`、`lifecycle`で主張の反証可能性と具体的な欠陥を評価する。v2専用fieldの欠如自体を違反とせず、値を推測・追加しない。意味が曖昧なら通常どおりREDESIGN／NEEDS_CONTEXTとし、evidenceは実在するfieldだけを指す。

このphaseへ削除元のsourceやlocatorを追加しない。削除identityは後段のalignmentで再検証する。v1の現在testを許す経路ではない。

## Output

```json
{
  "review_contract_version": "metadata-review-v2",
  "reviews": [
    {
      "record_id": "sha256:...",
      "metadata_hash": "sha256:...",
      "verdict": "VALID",
      "evidence": [
        {
          "fields": ["claim", "fault", "scope"],
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

`finding`は`SELF_CONTAINED_CLAIM`、`CONCRETE_FAULT`、`COHERENT_BOUNDARY`、`LIFECYCLE_ALIGNED`、`ORACLE_DECLARED`、`CLAIM_NOT_FALSIFIABLE`、`FAULT_NOT_SPECIFIC`、`BOUNDARY_INCONSISTENT`、`ORACLE_CIRCULAR`のいずれかとする。`fields`は入力metadataに存在するtop-level field、`oracle.type`、`oracle.ref`だけを参照できる。`VALID`と`REDESIGN`は一件以上の`evidence`を必要とする。

Phase 1を実行するruntimeは、履歴を継承しない新規の独立した`codex exec` workerとrepositoryを読めない強制権限境界を提供しなければならない。agent instructionや`read-only` sandboxだけではmetadata-only境界を満たさない。runtime smokeでこの境界を確認できるまで二段階workflowを有効化しない。
