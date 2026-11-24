# native子の設定を導入・比較する

これは配布設定を変える時の確認手順であり、通常の委譲の前提ではない。仕事の選び方と通常Sessionとの境界は[委譲ガイド](../architecture/subagent-workspace.md#nativeサブエージェント)に従う。

## 配布元と端末で確認するもの

| 確認先 | 確認できること |
| --- | --- |
| [共有設定例](../../config.example.toml)・[registryとprofile](../../config/)・[role定義](../../agents/) | TOMLが読め、registryの参照が解決する。親profile、一般子の既定、明示roleのmodel・effortを別々に確認する |
| [hookの登録](../../hooks.json)・[Windows起動検査](../../hooks/test-windows-launch.ps1) | startup/resume/compactと対象役のSubagentStartは共通入口を再通知する。PreToolUseは別に、明示modelの許可／拒否、Astra→Astra拒否、履歴なしへの置換と他引数の保持を行う |
| 適用後の新規Session | 配置したroleと既定の**実model・effort**、hookのtrust・該当イベントでの到達。APIの掲載やscriptの単体成功だけでは実起動の証拠にならない |

端末への配置が依頼された時だけ、使う設定欄・role・profile・hookを有効なCodex homeへ揃える。共通文書の参照先はOSのユーザーhome直下の `~/.codex/`。認証・MCP binding・無関係な設定は上書きしない。Terra利用の配布条件はCodex CLI 0.159.0以降。省略modelや任意の外部roleの実modelをPreToolUseが検証するとはみなさない。

## 役割・指示を比較する時

変更が効く代表入力と、同じ制限を課すべきでない対照を選ぶ。新規Sessionで開始commit・作業・使えるtool・完了条件を揃え、指示の比較ではmodel・effortも固定する。model比較と同じmodel内のeffort比較を混ぜない。旧modelをfallbackへ戻さず、本番への外部副作用を生じさせない。

成果の正しさ、判断に響く見落とし、人の手直し、不要な追加、所要時間・観測できた使用量を比較する。対象・実行条件を結果とともに残し、少数例やAPI単価から実利用枠や普遍的な優位を断定しない。専門reviewや実描画が必要な入力ではその成果も確認する。新しい常設の採点・保存基盤は要らない。
