---
name: audit-codex-work-quality
description: 開始日時と終了日時で固定したCodexセッション区間、実行証拠、明示的に関連付けられるPR成果を読み取り専用で収集し、観点別の監査結果を専用SQLite履歴へ記録して重複分析を避けながら、成果物品質、レビュー収束、ユーザー誘導負荷、検証の直接性、変更規模と異常系対策の比例性、過剰な恒久ルール化を振り返る。ユーザーが「今日・昨日・夜間のCodex作業を振り返る」「日付をまたぐ作業を監査する」「前回その観点を分析したのはいつか確認する」「レビューが収束しない原因を調べる」「オーバーエンジニアリングを監査する」「成果物品質の改善点を出す」と依頼したときに使う。通常のcode review、単一taskのvalidation report、session handoffには使わない。
---

# Codex Work Quality Audit

活動量ではなく、固定区間の論理変更と最終成果物が要求へどれだけ直接届いたかを監査し、品質低下を生んだ因果構造を反証可能な形で説明する。

## Accepted contract

- 対象期間は開始日時と終了日時で必ず固定する。現地時刻の半開区間`[start, end)`とし、`end > start`を要求する。複数の非連続区間へ暗黙展開しない。
- 固定区間は観測事実を数える`observation window`とする。原因の成立経緯を確かめるために区間外の履歴、ADR、policy、sourceを読む場合は`causal context`と明示し、区間内のevent、成果、件数へ混ぜない。
- PRは、session内の明示URL / number、同じrepositoryのexact commit OID、または一意に確認できるhead branchのいずれかで論理変更へ関連付ける。時刻、title、topicの類似だけで関連付けない。関連付けの根拠とconfidenceを記録し、曖昧ならPR evidenceを使わずgapにする。
- observation window内に発生したPR作成、更新、review、check、merge eventだけを区間内の観測として数える。区間終了後に確定したmerge、CI、revert、follow-upは`outcome context`と明示し、区間内の活動量へ混ぜずに成果のpostcondition検証へだけ使う。
- 関連PRがある場合は、GitHubを認証済みのread-only queryで確認する。PR、repository、branch、commit、review、checkを変更するcommandを実行しない。GitHub、repository、または認証を利用できない場合はsession監査を継続し、PR evidence gapを開示する。
- additions、deletions、file数、commit数は変更面積の記述に使い、単独の品質scoreまたは過剰設計の判定にしない。要求へ直接必要なbehavior、必要なcontract / validation、現実的な異常系、仮説的hardening、incidental churnへ変更を分けて比例性を判定する。
- 公開PRであってもraw diff、review本文、comment全文を監査出力または中間fileへ既定で複製しない。最終成果物の理解に必要なfile、finding、check、postconditionだけを読み、取得量が大きい場合は無言でtruncateせず未確認範囲をgapにする。
- startとendはoffsetなしのISO local datetimeで受け取り、timezoneを一つ選んでUTCへ変換する。`Asia/Tokyo`は追加packageなしで保証し、他のIANA timezoneはhostのtimezone dataが利用できる場合だけ受け付ける。DSTで曖昧または存在しない現地時刻は拒否する。
- session作成日ではなく、message、turn、operation、eventの発生時刻で対象を選ぶ。日をまたぐsessionも対象eventが区間内なら含める。
- SQLite CLIを必須依存とする。`sqlite3 --version`が失敗したら代替実装へfallbackせず停止する。
- WithMate DBは`sqlite3 -readonly`と`PRAGMA query_only=ON`を同じconnectionで使う。Memory tableを読まない。
- `.codex/sessions`はread-onlyでstream処理する。raw logや抽出JSONを既定でfileへ保存しない。
- rolloutのpath日付は探索用のhintに限り、候補除外には使わない。file末尾のevent timestampが対象区間より前だと確認できた場合だけ除外し、mtimeをevent時刻の代用にしない。末尾時刻を判定できないfileは候補へ含めてgap countを出す。
- WithMateのtimestamp domainを固定区間で絞る前に検査し、不正値の件数を`data_gaps`へ出す。rolloutのrelevant recordにtimestampがない、または解釈できない場合はreason別の件数へ集約する。時刻を解釈できない証拠を無言で対象外にせず、recordごとのgap文字列にも展開しない。
- user本文はCharacter envelopeの構造部分だけを除き、先頭・末尾の空白や改行を含む原文を保持する。cross-source messageはkind、本文digest、正確なUTC timestampが一致し、各sourceに候補が一つだけある場合に限って統合する。曖昧な候補は重複排除しない。
- workspaceを指定した場合は、WithMate rowとrollout fileをcanonical sessionへ統合する前に、大文字小文字を区別しないexact pathで絞る。同じcanonical session IDへ異なるworkspaceの証拠を混在させない。workspaceを指定しない場合は、統合されたsessionが持つ全workspace affiliationを`workspaces`へ開示する。
- usage、token、rate limitの量的評価は既定で除外する。ユーザーが明示した場合だけ別scopeとして扱う。
- startが未来の区間は受け付けない。endが収集時刻より後なら`partial`、それ以外は`complete`と明示する。
- AGENTS、Skill、hook、repository policyを自動変更しない。恒久変更は提案に留める。
- 既定出力はevent streamではなくsession indexとする。各sessionの時刻、workspace、source、event kind集計、known / unknown failure数、先頭・末尾から選んだ短いgoal / outcome cueだけを返し、`events`は投影しない。cueの省略数とevent-level detailを投影しなかった件数を開示する。
- `--detail`のper-session / global出力上限は、`provider_error`、明示的なerror eventまたはturn error、構造化signalで失敗と確認できたtool resultを同じknown failure evidenceとして優先保持する。known failure evidenceだけで明示上限を超える場合は、暗黙に欠落させず停止する。tool call / resultは、同じcanonical sessionとsource内で非空stringのcall IDが双方に一つずつある場合だけ対応済みとする。sourceが成功・失敗を構造化していない実行証拠、対応resultがないcall、空・不正・重複IDで対応が曖昧なcallは推測で分類せず、indexでは件数、detailでは`unknown_failure_status_events`と`unknown_failure_status_omitted`へ開示する。
- session indexにはtool command、tool output、raw error、stderr、provider payload summary、audit event summaryの本文を投影しない。`--detail`では、明示されたtext / event / row / byte上限内の本文、元の文字数、truncation、SHA-256と、source kind、operation type、call ID、tool種別、構造化された成否を分析用evidenceとして保持する。非文字列payloadはsource typeを伴うbounded JSONに変換し、変換不能は`data_gaps`へ開示する。detail evidenceを最終レポートへ機械的に転載せず、ユーザーが保存を明示しない限り中間fileへ永続化しない。
- WithMate DB、Codex rollout、repository、GitHubは引き続きread-onlyで扱う。書き込みはこのSkillが所有する監査履歴DBだけへ限定し、collectorへ履歴writeを追加しない。
- 監査履歴の同一性は、UTC半開区間、正規化したworkspace scope、`focus_key`、正規化した`focus_question`、analysis contract versionの組で決める。類義語や意味の近さを推測して統合しない。同じ区間でも観点または具体的な問いが違えば別分析として扱う。
- `complete`な固定区間で完了した同一観点の結果だけを再利用する。`partial`、`failed`、`abandoned`は履歴へ残しても後続分析を抑止しない。
- 履歴へ保存する結果はboundedなuser-facing要約、confidence、finding family、良かった判断、data gap、介入候補、outcome context確認時刻だけとする。保存CLIはfield、型、件数、長さ、全体byte数を機械検証するが、許可済み自由文が要約かraw引用かは判定できない。呼び出す監査workflowがprojection boundaryを所有し、session/event本文、cue、command/output、raw error、stderr、PR diff、review/comment本文、absolute workspace pathを許可済みfieldへ転載しない。
- 監査開始前に観点単位でclaimし、同じ対象の未期限切れclaimがある場合は重複分析を開始しない。期限切れclaimを置換した後のlate completionは拒否する。長時間の監査ではclaimをheartbeatする。
- 完了結果はユーザーへ最終報告する前に履歴へ確定する。履歴writeに失敗した場合は分析成功と重複抑止成功を分け、履歴未記録を開示する。

## Workflow

1. ユーザーの開始・終了時刻を絶対local datetimeへ一度だけ解決し、`start`、`end`、`timezone`、local interval、UTC intervalを先に表示する。時刻が指定されず結果が変わる場合は一度確認し、暦日へ暗黙補完しない。
2. `references/audit-history.md`を全文読み、依頼された観点を安定した`focus_key`と具体的な`focus_question`へ分ける。観点ごとに履歴をlookupして、前回日時、結果、関連する別questionを確認する。
3. 観点ごとに履歴をclaimする。`reuse`は保存済み結果を提示してその観点を再分析せず、`busy`は重複着手せずactive claimを開示し、`claimed`だけを今回の分析対象にする。明示的に再分析する場合だけboundedな`force_reason`を渡す。
4. `sqlite3 --version`、WithMate DB、`.codex/sessions`の存在を確認する。欠けた入力を成功扱いせず、開始済みclaimを`fail`で閉じる。
5. claimedな観点がある場合だけ、まず既定のsession index modeで収集する。

   ```powershell
   python scripts/collect_session_evidence.py --start 2026-08-01T20:00 --end 2026-08-02T04:00 --timezone Asia/Tokyo
   ```

6. indexのgoal / outcome cue、failure集計、event kind集計から、論理変更、review finding、検証失敗、ユーザーによる方向修正が集中したsessionだけ、`--detail --session-id <id>`で掘る。全sessionのevent detailを一括でcontextへ入れない。
7. `references/quality-rubric.md`を全文読み、session単位ではなく論理変更単位へ証拠を統合する。
8. session evidenceからPR URL / number、repository、branch、commit OIDを抽出し、Accepted contractの関連付け規則を満たすPRだけを候補にする。repository identity、base / head、commitをread-backして誤関連付けがないことを確認する。
9. 関連PRごとに、state、base / head、created / updated / merged時刻、merge commit、commit数、changed filesと行数、review decision、check resultをread-onlyで取得する。final diffは先にfile別統計と構造を確認し、監査対象のcontractと複雑性判断に必要な範囲を読む。区間終了後の状態はoutcome contextへ分離する。
10. PR evidenceをGoal / Artifact / Contract / Validation / Review / Outcomeへ統合し、`references/quality-rubric.md`の比例性と異常系到達性を評価する。PRがない論理変更、local-only成果、明示的にPRを作らないtaskを未完了扱いにしない。
11. 同じfindingをInvariant / failure familyで束ねる。review回数やtool call数だけで品質を判定しない。
12. materialなfinding familyごとに因果timelineを作り、`symptom -> proximate mechanism -> enabling condition -> systemic cause -> origin decision -> reinforcing / balancing feedback`を、該当する深さまで追う。途中の層を証拠なしで補完しない。
13. 少なくとも二つの競合仮説を置き、各仮説を支持する証拠、反証、説明できない事実、confidenceを比較する。複数要因の相互作用が必要なら、一つの主因へ強制的に縮約しない。
14. 既存の防止策が何だったか、その防止策がなぜ検出・停止・縮小に失敗したかを確認する。成功した変更または反例となるsessionとも比較し、単発事故から因果を一般化しない。
15. 介入案は因果分析と分離する。ユーザーが改善提案または実験を求めた場合だけ、confidenceが十分な因果linkについて局所・構造・policyの候補を同じ因果層ごとに比較する。最小差分を分析の目的または既定の結論にしない。
16. 各claimed観点についてboundedな構造化結果を`complete`する。途中で監査を完了できなかった観点は`fail`し、`completed`以外を分析済みとして扱わない。

## Collector usage

- `--start`と`--end`は必須。`YYYY-MM-DDTHH:MM[:SS[.ffffff]]`のoffsetなしlocal datetimeを使い、`[start, end)`として固定する。
- `--end`は`--start`より後にする。未来のstart、DSTで曖昧または存在しない現地時刻、offset付き入力は拒否する。
- `--timezone`は既定`Asia/Tokyo`。別timezoneを使う場合も1回だけ解決する。
- `--withmate-db`と`--codex-home`は環境差を明示するときだけ指定する。
- `--workspace`は各sourceの証拠をcanonical sessionへ統合する前にworkspaceで絞る。大文字小文字を区別しないexact path比較である。
- `--session-id`はindexで得たcanonical session IDを指定する。複数回指定できる。
- `--detail`は対象sessionのbounded event evidence、長いmessage preview、tool command / output、raw error、stderr、provider summary、audit event summaryを出す。reasoning、usage、provider payload全体は出さない。既定の監査ではindexで対象を絞ってから`--session-id`と併用し、detailに含まれるraw evidenceを必要な分析だけに使う。
- `--max-rollout-bytes`、`--max-rollout-line-bytes`、`--max-rollout-files`、`--max-tail-probe-bytes`、`--max-database-bytes`、`--max-database-rows`、`--max-collected-events`は収集処理のresource limitである。SQLiteのbyte上限はschema確認を含む全queryのstdout合計へ適用する。超過時は部分結果を成功扱いせず停止する。
- `--max-events-per-session`と`--max-events`はdetail event出力だけの上限であり、`--detail`なしでは拒否する。明示した0や負数は既定値へ読み替えず拒否する。indexのcue上限はschema contractへ固定し、CLI optionを増やさない。
- collectorが報告する`data_gaps`、`truncation`、`malformed_lines`を監査結果へ反映する。
- indexの`unknown_failure_status_events`が0より大きいsessionは、集計だけで検証成否を断定せず、必要なら`--detail --session-id`で確認する。detailの`unknown_failure_status_omitted`が0より大きい場合も同様に扱う。
- stdoutをfileへredirectするのは、ユーザーが保存を明示した場合だけにする。

## Analysis rules

- 成果物、accepted contract、実行したcheck、review evidence、ユーザーの修正指示を一次証拠にする。
- commentaryの自信、作業時間、message数、review回数を成果物品質の代用にしない。
- user steeringは、要求追加と、agentが先に防げた方向修正を分ける。
- review findingはvalidityを再確認し、`blocking`、改善候補、noiseを混ぜない。
- 異常系対策は、accepted / supported scope、通常利用から必要な前提条件、実発生または再現証拠、影響、検知、復旧、より局所的な防止境界を確認する。理論上構築できるだけのcaseを現実的なblocking riskとして数えない。
- PRの比例性は、行数ではなく要求へ直接寄与した責務と、追加されたmode、fallback、設定、dependency、policy、test matrix、運用負担の関係で判断する。green CI、merge済み、review finding数の少なさだけで比例的とみなさない。
- 特定modelの傾向へ帰属する場合は、同程度のgoal、supported scope、risk、review条件を持つ比較対象を要求する。単一期間または単一modelの事例だけなら、観測した設計傾向とmodel attributionを分ける。
- `root cause`はラベルではなく因果説明として示す。近接原因だけで止めず、成立条件、canonical ownerまたはdecision point、既存防御が失敗した理由、結果を増幅または抑制したloopまで、証拠が支える範囲を掘る。
- materialな結論には競合仮説と反証を付ける。相関、時間順序、agentの自己説明だけから原因を断定しない。
- 因果の深さは、観測された主要事実、成功例との差、再発または収束遅延を一つのmodelで説明でき、主要な競合仮説を証拠で比較できた地点で止める。未説明の事実はgapとして残す。
- 改善案を出す場合、因果modelのどのlinkを切るか、canonical owner、counterfactual、望ましくない副作用、次の3から5論理変更で観測できる成功指標を示す。`minimality`は同じ因果層で同等に有効な案を比較する制約であり、構造的原因を局所対策へ置き換える理由にしない。
- evidenceが不足する場合は断定を弱め、追加で読むsessionまたはartifactを特定する。

## Output

必要な因果深度を保ち、次の順で重複なく報告する。

1. 対象の開始・終了日時、timezone、固定区間、`complete` / `partial`
2. 論理変更と成果
3. 関連PRとassociation evidence、final artifact / outcome context
4. 変更規模の比例性と異常系到達性
5. 品質低下または収束遅延のfinding familyと根拠
6. 因果timelineと、最も早く防げた地点
7. 因果model、既存防御が失敗した理由、reinforcing / balancing feedback
8. 競合仮説、反証、confidence
9. 良かった判断と成功例との差
10. 未確認事項、収集gap、残リスク
11. 求められた場合だけ、因果linkへ対応する介入候補と次回experiment

token使用量、Candidate専用表、raw transcriptは、依頼されていなければ出力しない。
