# Alignment Review Contract v1

## Purpose

Phase 2は、固定済みのPhase 1結果を変更せず、metadataとtest sourceのactual observable、observation boundary、保持先候補を照合する。Phase 1が`REDESIGN`のrecordも省略しない。

## Input

packetは`review_contract_version = "alignment-review-v1"`、固定済みPhase 1 result全体の`metadata_result_hash`、`records`を持つ。各recordは次を持つ。

- Phase 1と同じ`record_id`、`metadata_format_version`、`metadata`、`metadata_hash`
- 固定済みの`metadata_review`
- extractorが返した`source`、`source_text`、`source_hash`
- extractor resultの`adapter`と`coverage`

alignment packet、deep packet、final aggregationは固定済みPhase 1 result artifactを独立入力として受け取り、`metadata_result_hash`と埋め込み`metadata_review`の両方を照合する。Phase 1 resultのrecord集合、verdict、hashを変更しない。source locatorとmetadata hashから`record_id`を再計算する。recordの追加、欠落、重複、metadata hashまたはsource hash不一致、canonical schemaにないfieldはAI審査前に拒否する。

## Review

- assertionが直接読む値、状態、event、artifactを`actual_observables`へ列挙する。
- actual boundaryを`consumer`、`public-boundary`、`component-behavior`、`declaration`、`implementation`から選ぶ。
- metadataが主張する境界とactual boundaryが一致するかを判定する。
- declarationそのものが正式なpublic artifactなら`public-boundary`として扱う。
- metadataが本文より広い影響を主張する場合は`overclaim = true`とする。
- test本文だけで確定できないhelper、fixture、mock、oracle、SUTを`context_requirements`へ具体的に挙げる。

## Output

`verdict`は`ALIGNED`、`MISMATCH`、`RECHECK`のいずれかとする。`ALIGNED`は`overclaim = false`を必要とし、`declared_boundary`が明示されている場合は`actual_boundary`と一致させる。`ALIGNED`と`MISMATCH`はrecord内のsourceを示す`evidence`を一件以上必要とし、全verdictで`actual_observables`を一件以上返す。`RECHECK`は`context_requirements`を一件以上必要とする。Phase 1 verdictを出力し直さない。

`disposition_candidate`は`KEEP_PERMANENT`、`KEEP_TEMPORARY`、`MOVE_TO_POLICY_CHECK`、`DROP`、`null`のいずれかであり、final dispositionではない。

全recordを一度ずつ返し、追加・欠落・重複を認めない。
