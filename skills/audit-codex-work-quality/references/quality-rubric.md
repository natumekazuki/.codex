# Codex作業品質の振り返りrubric

## 目次

1. 評価単位
2. 証拠の優先順位
3. 品質軸
4. Finding family
5. PRと成果物の比例性
6. Root-cause analysis
7. 介入提案のgate
8. 報告テンプレート

## 1. 評価単位

session数やturn数ではなく、ユーザーが得ようとした一つの成果を「論理変更」として扱う。同じ成果へ向けた実装、review、finding対応、commit、PRは一つへまとめる。途中でaccepted contractまたは目的が実質的に変わった場合だけ分ける。

各論理変更について次を固定する。

- Goal: ユーザーが求めた観測可能な結果
- Artifact: source、文書、commit、PR、調査結論など実際の成果物
- Contract: 明示要求、外部契約、accepted ADR、実行可能な契約
- Validation: failure modeを直接確認したcheck
- Review: valid finding、noise、未解決risk
- Steering: ユーザーが変更した方向と、その必要性
- Outcome: 完了、部分完了、撤回、未解決

## 2. 証拠の優先順位

強い順に扱う。

1. final artifactとpostcondition
2. source / executable contract / accepted anchor
3. checkのcommand、対象、result
4. 根拠と到達条件を持つreview finding
5. userによる明示的な方向修正
6. agentのcommentaryまたは自己評価

作業量、token、経過時間、turn数、review回数は品質の直接証拠にしない。ユーザーがusage分析を明示した場合も、成果物品質と別軸で報告する。

## 3. 品質軸

### 3.1 Goal / artifact alignment

- 最終成果物が依頼の完了条件へ直接対応したか。
- 依頼外のcleanup、policy変更、文書増加が成果を薄めていないか。
- 外部操作は依頼された対象とbase branchへ実行されたか。

### 3.2 Defect / contract discovery stage

- 後段で判明した事実ごとに、実際の発見時点と原因分類を分ける。
- 原因は次のいずれかに分類する。
  - `事前確認可能な欠落`: 明確な正本があり、着手前に読めば結論を確定できた。
  - `解釈の不一致`: 当時の同じ情報から複数の妥当なscope解釈があり、ユーザー意図が明示されていなかった。
  - `実装中に顕在化した判断`: 組み込みや実装を進めたことで、既存経路との関係が観測可能な結果を変える判断事項になった。
- 最も早い検出地点を`brief / preflight / implementation / targeted check / specialist review / holistic review / user feedback`から選び、その地点で実際に利用できた根拠を示す。後から判明した事実を、着手前から既知だったように扱わない。
- 事前確認可能だった証拠がない場合、preflight強化を既定の改善策にしない。
- 実装中の発見後に追加編集を止めて判断を求めた場合は、予防失敗の有無と発見後の対応品質を別々に評価する。

### 3.3 Finding family recurrence

- 表現が違っても同じInvariant、authority、scope、failure timingに属するfindingを一つへ束ねる。
- 同じfamilyが再発したら、局所修正よりworkflowまたはcanonical ownerの欠落を疑う。
- 反復回数だけで重大度を上げず、影響と到達条件を確認する。

### 3.4 Fix-induced complexity

- finding対応が新しいmode、例外、fallback、重複authorityを増やしていないか。
- sourceよりpolicy説明が大きくなっていないか。
- 一つのincidentを防ぐために全taskへ恒久負担を課していないか。
- 変更量だけで判定せず、§5で要求へ必要な責務と最終成果物のsurfaceを比較する。

### 3.5 Validation directness

- checkが対象failure modeを直接観測しているか。
- static文字列一致や内部手順の固定で正しさを代用していないか。
- 未実行check、環境差、partial dataが明示されているか。

### 3.6 Reviewer validity / noise

- findingにaccepted contract、安全境界、現実的な到達条件、具体的影響、source evidenceがあるか。
- hardening案やstyle preferenceをblockingと混同していないか。
- reviewerの指摘を採用前にrootが検証したか。

### 3.7 User steering burden

- user steeringが新しい要求なのか、agentが既存要求から先に判断できた訂正なのかを分ける。
- branch、base、scope、commit / push / PR、日付など結果を反転させる値を必要な時点で固定したか。
- userが同じ指摘を繰り返した場合はfinding familyとして扱う。
- 「最後」「あと一歩」などの進捗予測後に新しいfinding familyが反復する場合は、完了gate違反と混同せず、未探索の反例を残件として数えたforecast calibration failureとして扱う。

### 3.8 Permanent-rule proportionality

- 恒久ルールが複数の現実的な再発caseを防ぐか。
- 既存のcanonical boundaryを直す方が小さくないか。
- 単一incidentしか根拠がない場合、まずtask-local checklistまたは次回experimentで検証できないか。

## 4. Finding family

次の順でまとめる。

1. 観測されたcase
2. 欠けたInvariantまたは判断境界
3. 同じfamilyの兄弟case
4. 成果物または収束へ与えた影響
5. 事実の発見時点、原因分類、当時の根拠で最も早く検出できた地点
6. 既に存在する防止策と、機能しなかった理由
7. 実装中に発見した場合の停止・判断依頼と、予防失敗と分けた対応品質

同じreview commentの件数ではなく、異なるInvariant familyの数を示す。

## 5. PRと成果物の比例性

### 5.1 Associationと時間境界

- session内の明示URL / number、exact commit OID、一意なhead branchのいずれかでPRを論理変更へ関連付け、根拠とconfidenceを残す。
- 時刻、title、topicの類似だけでは関連付けない。複数候補、fork、branch再利用、repository不一致があればgapとする。
- observation window内のPR eventと、区間終了後に確定したmerge、CI、revert、follow-upを分ける。後者は`outcome context`として成果のpostconditionへ使い、区間内活動へ数えない。

### 5.2 Change surface

PRのadditions、deletions、file数、commit数は記述的なevidenceとして使い、次へ分類する。厳密な行数配賦ができない場合はfile、hunk、責務単位で根拠を示す。

- direct behavior: ユーザーが求めた観測可能なbehaviorまたはfailure解消
- necessary contract: accepted contractを保つtype、schema、validation、migration、platform実装
- realistic hardening: supported scopeで到達可能な異常系に対する防止、検知、復旧
- hypothetical hardening: 到達条件または実発生証拠がない一般的な防御
- incidental churn: rename、重複文書、作り直し、最終behaviorへ寄与しない中間構造

一つの数値ratioへ潰さず、要求へ必要な責務数と、追加したmodule、mode、fallback、config、dependency、policy、test matrix、運用手順の関係を説明する。横断的不変条件、migration、security境界など、要求上必要な非局所変更をfile数だけで過剰としない。

### 5.3 異常系の到達可能性

異常系ごとに次を確認する。

1. accepted contractまたはsupported scopeに含まれるか
2. defaultまたは通常操作から到達するか、追加前提が何個あるか
3. 実発生、再現、既知の外部仕様のどれに根拠があるか
4. 影響が機密性、不可逆なdata loss、停止、限定的なerrorのどれか
5. 自動検知、復旧、retry、既存防御があるか
6. 全体modeや恒久policyを増やさず、局所boundaryで同じriskを閉じられるか

`expected-path`、`realistic-exception`、`remote-hypothesis`、`unsupported`のいずれかへ分類する。理論上可能であることだけを理由に`remote-hypothesis`をblocking相当へ昇格しない。高影響でもsupported scopeへ現実的に到達する根拠がなければ、確信度と追加調査条件を分ける。

### 5.4 Outcomeとreview yield

- PRのopen / draft / merged / closed、base、merge commit、CI、review decision、revert、follow-upを確認する。
- valid review findingがdefault path、realistic exception、remote hypothesisのどこを守ったかを区別する。
- mergeやgreen CIは必要なpostconditionになり得るが、設計の比例性を単独で証明しない。
- PRがないlocal-only成果を自動的に未完了または低品質としない。PR evidenceは存在する論理変更の最終成果を強化する証拠である。

### 5.5 Model attribution

特定modelの設計傾向を結論にする場合は、goal、supported scope、risk、repository、review条件が近い比較群を要求する。比較群がない場合は、観測された過剰設計のpatternまでを結論とし、model名は未検証の仮説として分離する。

## 6. Root-cause analysis

### 6.1 Observationとcausal context

- 固定区間内のevent、成果物、finding、user steeringを`observation`とする。
- 原因の起源を調べるために区間外のcommit、ADR、policy、sourceを読む場合は`causal context`とする。
- causal contextは因果仮説の検証に使えるが、区間内の件数、成果、失敗として集計しない。

### 6.2 Causal depth

materialなfinding familyは次のchainで分析する。すべての層が存在するとは限らず、証拠のない層は`unknown`とする。

1. Symptom: 観測された品質低下または収束遅延
2. Proximate mechanism: 直接その結果を発生させた処理、判断、情報欠落
3. Enabling condition: mechanismを停止できなかった前提、権限、順序、責務境界
4. Systemic / structural cause: 複数caseで同じmechanismを許すworkflow、canonical owner、evidence model
5. Origin decision: その構造を選んだ根拠と、元々守ろうとしたcontract
6. Feedback: 結果を増幅するreinforcing loopと、抑制するbalancing loop

「注意不足」「もっと慎重にする」、category名、最も近い失敗箇所だけをroot causeにしない。複数要因の相互作用が主要事実を最もよく説明する場合は、単一のprimary causeへ縮約しない。

### 6.3 Competing hypotheses

materialな結論ごとに少なくとも二つの妥当な仮説を比較する。

| Hypothesis | Supporting evidence | Disconfirming evidence | Unexplained facts | Confidence |
| --- | --- | --- | --- | --- |

confidenceは`high / medium / low`とし、根拠を一文で付ける。仮説が観測事実を説明できるだけで採用せず、成功例との差、時間順序、反例、既存防御が機能したcaseを使って識別する。

### 6.4 Existing defenses and feedback

- 既に存在したpreflight、test、review、Candidate、review上限、authority gateを列挙する。
- 各防御が`存在しなかった / 遅すぎた / wrong boundaryを見た / 情報を持てなかった / 自身が増幅要因になった`のどれかを証拠で判定する。
- findingからsource変更、evidence失効、再review、追加findingへ戻る循環など、結果が次の原因条件を強めるloopを明示する。
- balancing loopがあっても、実際にどこで効いたかを確認する。policyに書かれているだけで機能したとみなさない。

分析は、主要な観測事実、成功例との差、再発または収束遅延を因果modelで説明し、主要な競合仮説を比較できた時点で閉じる。説明できない事実はevidence gapとして残す。

## 7. 介入提案のgate

介入案は因果分析を置き換えない。ユーザーが改善提案または実験を求めた場合だけ、confidenceが十分な因果linkについて候補を出し、次を満たすか確認する。

- evidence: 少なくとも一つの具体的なartifactまたはfinding familyがある
- causal leverage: 因果modelのどのlinkまたはfeedback loopを切るか示せる
- counterfactual: 変更があれば最も早い検出地点または増幅地点で結果がどう変わったか説明できる
- ownership: source、test、Skill、AGENTS、toolingのどこが正本か明確である
- side effects: 防御の弱体化、新しい恒久負担、別のfailure modeを示す
- observable result: 次の3から5論理変更で成功を判定できる

局所・構造・policyの候補を因果層ごとに分ける。`minimality`は同じ因果linkへ同等に作用する案の比較条件として使い、上流の構造原因が確認されたときに局所案だけを選ぶ理由にしない。

## 8. 報告テンプレート

```text
対象: Local [start, end) / Timezone / UTC [start, end) / complete|partial

論理変更と成果:
- Goal / Artifact / Outcome

PR / outcome evidence:
- Association basis / PR state / Final artifact / Outcome context

Proportionality:
- Direct behavior / Necessary contract / Realistic hardening / Hypothetical hardening / Incidental churn
- Reachability / Added responsibility surface / Judgment and confidence

良かった判断:
- Evidence / Why it mattered

Findings:
- Family / Evidence / Impact / Discovery stage / Cause classification / Earliest evidence-based catch point / Post-discovery response

Causal timeline:
- Observation / Mechanism / Decision point

Causal model:
- Symptom -> proximate mechanism -> enabling condition -> systemic cause -> origin decision
- Existing defenses and why they failed
- Reinforcing and balancing feedback

Competing hypotheses:
- Hypothesis / Evidence for and against / Unexplained facts / Confidence

Data gaps and residual risk:
- Missing or truncated evidence / Effect on confidence

Interventions (only when requested or causally justified):
- Causal link / Local, structural, or policy change / Counterfactual / Side effects / Success signal
```
