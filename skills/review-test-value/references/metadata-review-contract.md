# Metadata Review Contract v3

## Purpose

Phase 1は、test sourceを見ずに`@test-value` metadataが自己完結した検証上の主張かを審査する。sourceから意味を補完してはならない。

## Input

hostはcanonical packetとしてrecord identity、metadata hash、contract versionを保持する。modelへ渡すtransport projectionは次の形だけを持つ。

```json
{
  "records": [
    {
      "ordinal": 0,
      "metadata_format_version": 2,
      "metadata": {"...": "..."}
    }
  ]
}
```

`ordinal`はbatch内の0始まりの位置である。metadata phaseのmodel inputにはsource locator、source本文、record identity、hash、contract versionを含めない。hostはcanonical packetをmodel inputへそのまま転送せず、未知のkey、重複record、metadata hash不一致をmodel呼出し前に拒否する。

canonical packetの`metadata_format_version`、`metadata`、identity、hashはhost artifactの責務である。現在のtestは`2`で、正常なGit削除元に限り`1`を使う。`metadata`の値に書かれたSHA-256らしい文字列は意味内容として保持する。

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

model outputは次の形だけを返す。

```json
{
  "reviews": [
    {
      "ordinal": 0,
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

`verdict`は`VALID`、`REDESIGN`、`NEEDS_CONTEXT`のいずれかとする。`evidence`はmetadata field pathと定義済みfindingだけを持つ構造化objectの配列とし、自由文やsource fieldを根拠として受理しない。`NEEDS_CONTEXT`は`unverified`と`next_action`へ必要な追加sourceを具体的に示す。全recordを一度ずつ、入力順のordinalで返す。ordinalの欠落、重複、範囲外、順序変更、booleanや非整数はhostが拒否する。hostは検証済みordinalと入力順からrecord identity、metadata hash、contract versionを付与してcanonical resultを構築する。modelへこれらを復唱させない。

`finding`は`SELF_CONTAINED_CLAIM`、`CONCRETE_FAULT`、`COHERENT_BOUNDARY`、`LIFECYCLE_ALIGNED`、`ORACLE_DECLARED`、`CLAIM_NOT_FALSIFIABLE`、`FAULT_NOT_SPECIFIC`、`BOUNDARY_INCONSISTENT`、`ORACLE_CIRCULAR`のいずれかとする。`fields`は入力metadataに存在するtop-level field、`oracle.type`、`oracle.ref`だけを参照できる。`VALID`と`REDESIGN`は一件以上の`evidence`を必要とする。

Phase 1を実行するruntimeは、履歴を継承しない新規の独立した`codex exec` workerとrepositoryを読めない強制権限境界を提供しなければならない。agent instructionや`read-only` sandboxだけではmetadata-only境界を満たさない。runtime smokeでこの境界を確認できるまで二段階workflowを有効化しない。
