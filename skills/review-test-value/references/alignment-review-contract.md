# Alignment Review Contract v3

## Purpose

Phase 2は、固定済みのPhase 1結果を変更せず、metadataとtest sourceのactual observable、observation boundaryを照合する。Phase 1が`REDESIGN`のrecordも省略しない。

## Input

hostのcanonical packetには固定済みPhase 1 resultとsource identity／hashが含まれる。modelへ渡すprojectionは各recordを次の意味fieldへ射影する。

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
      "adapter": "python",
      "coverage": "full"
    }
  ]
}
```

projectionのnested frozen reviewからrecord identity、metadata／source hash、contract versionを除く。source textはactual observableの判断に必要なため保持する。`ordinal`はbatch内の0始まりの位置である。

canonical packetのrecord identity、metadata／source hash、固定済みreview、extractor sourceはhost artifactの責務である。未知のkey、record集合、hash、順序はmodel呼出し前にhostが検証する。

alignment packet、deep packet、final aggregationは固定済みPhase 1 result artifactを独立入力として受け取り、`metadata_result_hash`と埋め込み`metadata_review`の両方を照合する。Phase 1 resultのrecord集合、verdict、hashを変更しない。source locatorとmetadata hashから`record_id`を再計算する。recordの追加、欠落、重複、metadata hashまたはsource hash不一致、canonical schemaにないfieldはAI審査前に拒否する。

## Review

- assertionが直接読む値、状態、event、artifactを`actual_observables`へ列挙する。
- actual boundaryを`consumer`、`public-boundary`、`component-behavior`、`declaration`、`implementation`から選ぶ。
- metadataが主張する境界とactual boundaryが一致するかを判定する。
- declarationそのものが正式なpublic artifactなら`public-boundary`として扱う。
- `fault`と`observable`が本文で直接検出できる範囲を超えるときは`overclaim = true`とする。任意の`impact`が間接的な影響を記すことだけではoverclaimにしない。
- test本文だけで確定できないhelper、fixture、mock、oracle、SUTを`context_requirements`へ具体的に挙げる。
- 正しい内部変更で壊れるprivate wiringや内部順序の固定、入力と期待値の同じ生成元への依存、mockが対象処理を置き換えていないかを確認する。対象欠陥を入れても通る観測を十分な検証としない。
- 既存checkとの差と、type・schema・static・build・smoke・browser・visual checkの方が直接的かを意味根拠へ反映する。record外の既存checkを見たと推測せず、必要なら限定contextを要求する。根拠のあるDROP/MOVEを扱い、安全契約を保証するnegative assertionは自動却下しない。

## 歴史的v1削除

`metadata_format_version = 1`は元source・metadata・locatorから再計算した削除専用IDに一致する場合だけ受理する。`claim`と`failure_mode`を本文の観測で検出できるか評価する。v1にない宣言boundaryとのenum一致は要求しないが、主張の意味の一致、actual boundaryとobservable、overclaim、source evidence、情報不足時のRECHECKは通常どおり確認する。元metadataへv2 fieldを補完しない。

v1削除の最終処置はDROP（declaration境界はMOVE_TO_POLICY_CHECK）とし、保持根拠と削除／代替チェックの解消確認を必要とする。ALIGNEDやAPPROVEだけで全体PASSにはしない。

## Output

model outputは次の意味fieldだけを返す。

```json
{
  "reviews": [
    {
      "ordinal": 0,
      "verdict": "ALIGNED",
      "actual_boundary": "component-behavior",
      "actual_observables": ["final gate"],
      "overclaim": false,
      "evidence": ["source assertion"],
      "unverified": [],
      "context_requirements": [],
      "next_action": null
    }
  ]
}
```

`verdict`は`ALIGNED`、`MISMATCH`、`RECHECK`のいずれかとする。`ALIGNED`は`overclaim = false`を必要とし、metadata format version 2では入力metadataの`observation_boundary`と`actual_boundary`を一致させる。`declared_boundary`を重複出力しない。`ALIGNED`と`MISMATCH`はrecord内のsourceを示す`evidence`を一件以上必要とし、確定した判定では`actual_observables`を一件以上返す。`RECHECK`では未確定の`actual_boundary`を`null`、直接観測も不明なら`actual_observables`を空配列にできる。`RECHECK`は`context_requirements`を一件以上必要とする。Phase 1 verdictを出力し直さない。

hostは検証済みordinalと入力順からrecord identity、metadata／source hash、contract versionを付与してcanonical resultを構築する。dispositionはrouting policyとdeterministic final aggregationが決定し、alignment model outputには含めない。

全recordを一度ずつ、入力順のordinalで返す。ordinalの欠落、重複、範囲外、順序変更、booleanや非整数、host identity／hash／contract versionの復唱は拒否する。
