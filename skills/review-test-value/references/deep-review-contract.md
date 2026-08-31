# Deep Review Contract v1

## Purpose

Sol deep reviewは、Lunaだけで閉じないrecord、高リスクrecord、監査recordをbounded contextで裁定する。通常のcode reviewを代替しない。

## Input

packetは`review_contract_version = "deep-review-v1"`と`records`を持つ。各recordは次を持つ。

- Phase 1、Phase 2と同じrecord identity、metadata、source、hash
- 固定済みの`metadata_review`と`alignment_review`
- `routing_reasons`と親workflowを含む`risk_tags`
- 必要なsourceと証拠だけを含む`context`
- `included_scope`と`excluded_scope`

Solはpacket外を探索しない。alignment recordはallowlist fieldから再構築し、未知fieldを転送しない。context itemは`kind`、`ref`、`content`、`content_hash`を持ち、hash不一致をAI審査前に拒否する。routing manifestはrecord ID、metadata hash、source hash、固定済みPhase 1 / Phase 2 verdict、manifestとは独立した親workflow risk context、audit率から決定論的に再計算し、不一致を拒否する。

## Output

```json
{
  "review_contract_version": "deep-review-v1",
  "reviews": [
    {
      "record_id": "sha256:...",
      "metadata_hash": "...",
      "source_hash": "...",
      "verdict": "APPROVE",
      "evidence": [],
      "unverified": [],
      "context_requirements": [],
      "next_action": null
    }
  ]
}
```

`verdict`は`APPROVE`、`REDESIGN`、`NEEDS_CONTEXT`のいずれかとする。`APPROVE`と`REDESIGN`は`evidence`を一件以上必要とする。packetだけで閉じられない場合は`NEEDS_CONTEXT`とし、必要なsourceまたは証拠を`context_requirements`へ具体的に挙げる。
