# Extracted Test Value Output v2

抽出器は引き続きUTF-8 JSONを一つ返す。source解析とGit selectionの契約は変更しない。

```json
{"schema_version":2,"adapter":"python-source-v1","coverage":"python-source-declarations-v1","repository_root":".","tests":[],"transitions":null,"diagnostics":[],"warnings":[]}
```

recordはsource locator、metadata_format_version、metadata、source_text、source_hash、metadata_hashを持つ。LF正規化・canonical JSON・SHA-256を使い、source/metadataを補完しない。locatorは編集をまたぐ永続IDではない。

明示path modeのtransitionsはnull。標準のGit modeはkind/before/afterを持つADDED、SURVIVED、DELETEDを返す。testsはADDED/SURVIVEDのafter集合と順序まで一致し、削除元はDELETED.beforeへ保存する。未変更testやpure renameを新規審査対象にしない。詳細は[Git selection](git-selection-v1.md)と[source adapters](source-adapters-v1.md)を参照する。

現在の新規・意味変更にはv2を要求する。完全削除の正しいv1は過去の証拠として保持し、存在しないv2 fieldへ変換しない。不正な過去metadata、対応外宣言、syntax/decode/adapter失敗を削除で隠さない。diagnosticがある抽出結果をreview成功へ変換しない。

抽出exitは0=errorなし、1=source/metadata diagnostic、2=環境・I/O等の失敗。空抽出のexit 0は意味reviewや過去義務のPASSではない。

## 単一reviewへの接続

`build_review_packets.selected_records`が全言語のtransitionとhashを確認し、host-owned identityを作る。modelへはmetadata・source・locator・bounded context等とbatch-local ordinalを渡す。返却値にrecord ID、hash、contract versionは含めない。

意味契約は[review-contract-v3](review-contract-v3.md)。model-visible schema、ordinal検査、identity付与の正本は`validate_review_result.py`、保持・削除/移設・集約はhost側script。単一のcanonical `review-state.json`へ最終分類とhost identityを保存する。旧metadata/alignment/deep resultやrouting artifactを読み替えない。

coordinatorのexitは0=全体PASS、1=CHANGES_REQUIRED、2=BLOCKED。phase validatorの成功、空selection、削除だけでは全体PASSにしない。[candidate有効化](../../../docs/runbooks/activate-test-value-review.md)が終わるまで明示起動に限定する。
