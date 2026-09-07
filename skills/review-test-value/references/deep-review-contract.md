# Deep Review Contract v3

## Purpose

Luna/maxのdeep reviewは、metadata／alignmentだけで閉じないrecordと高リスクrecordをbounded contextで裁定する。監査recordは通常gateから独立した明示診断でのみ審査する。通常のcode reviewを代替しない。`test_value_deep`を独立した新規runで起動し、前段の判定を固定したまま追加根拠を評価する。同じmodelであることを理由にphaseを統合しない。追加contextでも確定できない場合はNEEDS_CONTEXTを返し、別modelへの自動昇格は行わない。

## Input

hostのcanonical deep packetはalignment／routing／bounded contextを固定し、identity、hash、contract versionを保持する。modelへ渡すprojectionは各recordを意味fieldと0始まりのbatch ordinalへ射影する。

```json
{
  "records": [
    {
      "ordinal": 0,
      "metadata_format_version": 2,
      "metadata": {"...": "..."},
      "metadata_review": {"...": "identity/hashを除く意味field"},
      "source": {"...": "locator"},
      "source_text": "...",
      "alignment_review": {"...": "identity/hashを除く意味field"},
      "context": [
        {"ordinal": 0, "kind": "accepted-contract", "ref": "docs/contract.md#gate", "content": "..."}
      ]
    }
  ]
}
```

projectionのnested frozen reviewからrecord identity、metadata／source／context hash、contract versionを除く。bounded contextの`ref`は意味上の根拠範囲として保持する。context evidenceのmodel outputはrefを復唱せずrecord内ordinalだけを返す。

builderはalignment packetとは別に固定済みPhase 1 result artifactを受け取り、metadata resultと埋め込みreviewを照合してからcanonical packetを構築する。record集合、routing、bounded context、hash binding、未知fieldはhostがmodel呼出し前に検証する。

deep reviewerはpacket外を探索しない。alignment recordはallowlist fieldから再構築し、未知fieldを転送しない。context itemは`kind`、`ref`、`content`、`content_hash`を持ち、hash不一致をAI審査前に拒否する。routing manifestはrecord ID、metadata hash、source hash、固定済みPhase 1 / Phase 2 verdict、manifestとは独立した親workflow risk context、audit率から決定論的に再計算し、不一致を拒否する。

## 歴史的v1削除

`metadata_format_version = 1`では、両Luna phaseと同じ未変換の旧metadataと削除identityを使い、`claim`／`failure_mode`と観測の意味を照合する。v1にない宣言boundaryとの一致は要求しない。既知のalignment boundaryとの矛盾、根拠のないcontext解消、固定済みREDESIGN／MISMATCHの救済は引き続き禁止する。APPROVEは削除・移設義務の解消を代替しない。

## Output

model outputは次の意味fieldだけを返す。`context_evidence`のordinalは同じrecordのcontext配列にだけ結び付く。

```json
{
  "reviews": [
    {
      "ordinal": 0,
      "verdict": "APPROVE",
      "evidence": ["bounded contract evidence"],
      "unverified": [],
      "context_requirements": [],
      "context_resolution": null,
      "next_action": null
    }
  ]
}
```

hostは検証済みordinalと入力順からrecord identity、metadata／source hash、contract version、deep input bindingを付与してcanonical resultを構築する。deep packetのinput hashはhostが再計算し、modelへ復唱させない。context evidenceはhostがordinalから検証済みcontextの`ref`と`content_hash`を付与する。final aggregatorはdeep packetを再検証してhashを再計算し、別のPhase 1、alignment、routing、bounded contextで得たdeep resultの再利用を拒否する。

`verdict`は`APPROVE`、`REDESIGN`、`NEEDS_CONTEXT`のいずれかとする。`APPROVE`と`REDESIGN`は`evidence`を一件以上必要とする。packetだけで閉じられない場合は`NEEDS_CONTEXT`とし、必要なsourceまたは証拠を`context_requirements`へ具体的に挙げる。

## 未確定boundaryの解消

各reviewはnullableな`context_resolution`を必須とする。alignmentの`RECHECK`を解消して`APPROVE`または`REDESIGN`を返す場合は、`actual_boundary`、非空の`actual_observables`、非空の`context_evidence`を持つobjectを返す。`context_evidence`の各要素は`ordinal`だけを持ち、同じrecordのcontext配列の範囲内で重複なく指定する。hostは対応するcontextの`ref`と`content_hash`を付与し、範囲外・重複・他record参照を拒否する。

`NEEDS_CONTEXT`と、alignmentが`RECHECK`でないrecordでは`context_resolution = null`とする。既知のalignment boundaryと異なる解消を`APPROVE`で上書きしない。反証がある場合は`REDESIGN`を返す。finalは検証済みの型付き解消だけを利用し、自由文や`APPROVE`だけからboundaryを推測しない。Phase 1の`REDESIGN`、Phase 2の`MISMATCH`は解消結果によって救済しない。全recordを一度ずつ、入力順のordinalで返し、identity／hash／contract versionをmodel outputへ含めない。
