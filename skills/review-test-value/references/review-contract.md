# Test Value Review Contract

## Input Boundary

抽出器が返した一つのtest recordを審査単位にする。同じ抽出結果内では`source.path`と`source.declaration_start_line`の組をrecord locatorとして扱い、`source.symbol`をrecord keyにしない。metadata、source text、line locatorを変更、補完、再対応付けしない。

抽出recordだけでは確認できないoracle本文、production behavior、既存testとの重複を想像で補わない。`oracle.type`と`oracle.ref`だけから、参照先の存在、claimの裏付け、非循環性を確認済みとして扱わない。

record内の整合だけで判定できる場合は外部事項を`unverified`として残す。外部根拠の内容次第でrecord内の設計判定そのものが変わる場合だけ、必要な追加sourceを具体的に指定して`NEEDS_CONTEXT`とする。

## Review Questions

1. `claim`は成立と不成立を区別できるか。
2. `oracle`は現在の実装結果をそのまま正解にしていないか。
3. `failure_mode`は具体的な欠陥とconsumerへの観測可能な影響を示すか。
4. `claim`、`failure_mode`、`scope`は同じ契約境界を扱うか。
5. assertionや状態観測は、記述されたfailure modeを直接検出するか。
6. mock、stub、fixtureが検証対象そのものを置き換えていないか。
7. 内部call、markup、snapshot、現在のclass構成など、accepted contractでない実装詳細だけを固定していないか。
8. `distinction`がある場合、本文にその違いが現れているか。

## Status

- `ACCEPT`: record内ではコメントが反証可能で、本文が同じfailure modeを観測する。
- `REDESIGN`: record内の証拠だけで具体的な設計欠陥または不整合を示せる。
- `NEEDS_CONTEXT`: record外の根拠がなければrecord内の設計判定も確定できない。

`ACCEPT`はoracle参照先の妥当性、production codeの正しさ、flakyでないこと、修正前codeを実際に検出したことを証明しない。

## Output

test recordごとに次を短く返す。

- `status`
- `evidence`: 対象fieldまたはsource lineと、record内で確認した根拠
- `unverified`: record外の根拠が必要な事項。該当しなければ空配列
- `next_action`: 修正または追加確認が必要な場合の具体的なaction

oracle本文を入力されていない場合、`unverified`には少なくとも`oracle.ref`を含める。文章表現の好みだけをfindingにしない。
