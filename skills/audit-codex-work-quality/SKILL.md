---
name: audit-codex-work-quality
description: 日次・夜間など期間を固定したCodex作業監査の明示依頼で、成果物品質とレビュー収束を実行証拠から分析し、観点別のSQLite履歴へ記録する。通常のcode review、単一taskの検証報告、引継ぎには使わない。
---

# Codex Work Quality Audit

監査の単位はSessionや作業量ではなく、一つの目的に向かう論理変更である。依頼された問いに、最終成果物・維持契約・実施された検証・区間内の出来事から答える。回数・行数・作業時間を品質scoreにしない。usage・token・rate limitは明示依頼時だけ別軸で扱う。

## 対象と履歴を先に決める

開始・終了を一度だけoffsetなしの絶対local datetimeへ解決し、一つのtimezoneの半開区間 `[start, end)` と対応するUTCを示す。時刻の不足が結果を変えるときだけ確認し、暗黙に暦日や複数区間へ広げない。`end > start` とし、未来の開始、DSTで曖昧・存在しない時刻は受け付けない。既定の `Asia/Tokyo` 以外のIANA timezoneにはhostのtimezone dataが必要。収集時点が終了前なら `partial`、終了後なら `complete` の区間として扱う。

[監査履歴の契約](references/audit-history.md)に従い、UTC区間・workspace scope・`focus_key`・具体的な `focus_question`・契約versionを同一性の基準にlookupし、観点ごとにclaimする。同義に見える問いを勝手にまとめない。`reuse`なら完了済み結果を使い、`busy`なら重複着手しない。`claimed`の観点だけを収集・分析し、長い作業ではheartbeatする。明示された再分析だけが強制再実行の対象である。

## 収集範囲と読取境界

SQLite CLI（`sqlite3 --version`）、対象のWithMate DB、Codexのsessionsを確認する。欠ければ別実装に切り替えず、開始済みclaimを `fail` で閉じる。WithMateは同一接続で `sqlite3 -readonly` と `PRAGMA query_only=ON` を使い、Memory tableを読まない。rolloutはread-onlyでstream処理し、repository・GitHubも読取専用とする。監査によるwriteは専用の履歴DBだけで、規約・PR・設定を変更しない。

Skillの `scripts/collect_session_evidence.py` で、まずSession indexを取得する。例えばSkill directoryから:

```powershell
python scripts/collect_session_evidence.py --start 2026-08-01T20:00 --end 2026-08-02T04:00 --timezone Asia/Tokyo
```

- **区間・所属。** Session作成日ではなくevent時刻を使う。rolloutのpath日付は探索の手掛かりであり、mtimeで代用しない。末尾が区間より前と確かめられないfileは候補に残す。WithMateの時刻域は抽出前に調べ、不正値やrolloutの解釈不能時刻を理由別件数で `data_gaps` に含める。`--workspace` 指定時は統合前に大小文字を区別しないexact pathで絞る。未指定なら全所属を `workspaces` に示す。
- **同一event。** user本文はCharacter envelopeの構造だけを除き空白・改行を保つ。sourceをまたぐmessageはkind・本文digest・正確なUTC時刻が一致し、各sourceで一意の場合だけ統合する。tool callとresultの対応は同じcanonical session・source内の非空の文字列call IDが双方で一意の場合に限る。
- **indexとdetail。** indexは時刻、workspace、source、event種別・失敗件数、先頭・末尾からの短いgoal/outcome cueと省略量を示す。events、command/output、raw error、stderr、provider・audit payloadの本文は出さない。問いや失敗の根拠を深掘りするSessionだけ `--detail --session-id <id>` で選ぶ。detailは制限内の本文・元の長さ・truncation・SHA-256・source・操作・対応識別子・構造化された成否を含む。非文字列payloadの変換失敗もgapとし、reasoning・usage・provider payload全体は出さない。
- **結果不明と上限。** 明示error・turn/provider error・構造化されたtool失敗をknown failureとして優先し、それだけでdetail出力上限を超えたら停止する。構造化されていない成否やresultの欠落・曖昧な対応はunknownであり、件数とdetailの `unknown_failure_status_events`・`unknown_failure_status_omitted` を区別する。collectorのbyte・行・file・event等の資源上限超過は失敗であり部分成功ではない。SQLite byte上限はschema確認を含む全queryのstdout合計。`--max-events-per-session` と `--max-events` はdetail専用の正の値で、indexのcue上限とは別である。

入出力pathや上限を指定する場合はcollectorの `--help` を使う。収集の欠落・省略・不正行は結論の根拠に反映する。raw log・抽出JSONの保存やstdoutのfile出力は既定で行わず、保存の明示依頼を要する。公開PRもraw diff・review本文を中間fileや報告へ複製しない。

## 論理変更を検証する

[品質rubric](references/quality-rubric.md)で、観測した成果、比例性、到達可能な異常系、指摘の妥当性を評価する。関連PRはSession内の明示URL／番号、同じrepositoryのexact commit OID、一意なhead branchに限って対応付け、repository・base/head・commitをread-backする。対応根拠とconfidenceを残し、時刻や話題の類似で補わない。認証済みのread-only queryで最終差分・review・check・merge等を必要な範囲で確認する。取得不能・対応不明なら残りの監査を続ける。PRを作らない成果はそれだけで未完了ではない。

区間内に発生したeventだけを観測として数える。区間外で原因をたどった資料は `causal context`、終了後のmerge・CI・revert等は `outcome context` として分ける。後から得た情報で当時の規約違反や事前に発見できたはずの欠落を作らない。

結果を左右するfindingは、同じ不変条件・失敗の種類ごとにまとめる。実際の発見時点と当時の根拠で検出できた地点を分け、rubricの基準で競合仮説・反証・既存の防止策・成功例との差を比較する。改善案や実験は依頼された場合に限り、根拠のある因果関係に結び付ける。

## 結果の確定

最終報告前に、観点ごとのboundedな利用者向け要約を履歴契約どおりに `complete` し、完了できなかったclaimは `fail` で閉じる。専用CLIの型・件数・長さ検査では自由文の機密や引用は検出できない。生の記録・command・エラー・PR本文・絶対workspace pathを許可済みfieldに入れない。保存失敗時は分析結果と履歴未記録を分けて伝える。

報告は固定区間と結果を明らかにし、問いへの結論、成果物と根拠、確信度を変える不足を中心にする。履歴の構造化入力を報告の空欄として並べない。
