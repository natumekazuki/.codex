# ADR-0009: 作業品質監査の証拠収集境界を固定する

- Status: accepted
- Date: 2026-08-02

## Context

Codexの作業品質を振り返るには、日付をまたぐ作業を一つの区間として扱い、WithMateのSQLiteデータとCodex rolloutを同じ時間境界で収集する必要がある。論理変更がPRへ到達した場合は、最終成果物、review、CI、merge後の状態も、セッション中の自己評価とは独立した品質証拠になる。収集対象にはユーザー発言、実行結果、error、PRのdiffやcommentなどが含まれ得るため、読み取り方法、関連付け、resource limit、公開結果へ投影する情報の境界を誤ると、監査の欠落、別作業の誤帰属、または機密情報の露出につながる。

この監査は日常的に実行する補助workflowであり、source dataを変更せず、同じ入力条件から同じ対象範囲を説明できる必要がある。一方、完全なraw logの複製は監査に不要であり、出力を新たな機密情報の集積先にしてはならない。

## Decision

- 監査対象は、利用者が明示した開始日時と終了日時から作る一つの連続区間へ固定する。timezoneを一つ選び、夜間の日跨ぎを暦日へ分割しない
- WithMateの収集には`sqlite3` CLIのread-only接続を使い、Codex rolloutとともにsourceを変更しない
- PR evidenceはsession内の明示参照、exact commit、または一意なbranchで論理変更へ関連付けられる場合だけ、認証済みのread-only GitHub queryで確認する。時刻やtitleの類似だけでは関連付けず、GitHubが利用できない場合はgapとして扱う
- 固定区間内のPR eventと、区間終了後に確定したmerge、CI、revert、follow-upを分ける。後者はoutcome contextとしてpostcondition検証へ使い、区間内の活動へ数えない
- 収集量には明示的なfile、byte、row、eventの上限を設け、上限超過や対象範囲を判定できない重大な欠落はfail-closedまたは集約したgapとして開示する
- 既定出力はsession indexとし、session identity、時間範囲、workspace、source、event / failure集計、短いgoal / outcome cueだけを返す。event-level evidenceはindexで対象sessionを選んだ後、`--detail --session-id`で取得する
- user / assistant messageは品質監査に必要な範囲で長さを制限して保持する。toolのcommand、raw error、stderr、PRのraw diff、review本文、comment全文は公開結果や中間fileへ既定で複製せず、監査に必要な構造化証拠と対象箇所だけを扱う
- 実行手順、field、上限、error semanticsの正本は`skills/audit-codex-work-quality/`のSkill、collector、executable contractとし、このADRへ複製しない

## Alternatives

- 暦日単位で収集する: 夜間作業が日付境界で分断され、一つの作業区間として比較できないため採用しない
- PythonのSQLite bindingへ依存する: 既存環境で利用するCLIのread-only境界と運用上の前提を一つに固定するため、現時点では採用しない
- tool commandとraw resultを切り詰めて保持する: 短縮してもsecret露出を防げず、監査に本文は不要なため採用しない
- 制限超過時に黙って打ち切る: gapの有無を判断できず、監査結果へ過度な確信を与えるため採用しない
- source logをそのまま監査成果物として保存する: 必要以上の機密情報を複製し、出力の安全境界を維持できないため採用しない

## Consequences

- Positive: 日付をまたぐ作業を一つの説明可能な区間として監査できる
- Positive: source dataを変更せず、収集量と失敗条件を事前に制御できる
- Positive: tool実行の成否や相関を追跡しながら、raw commandやerrorに含まれるsecretの二次露出を抑えられる
- Positive: 日常の振り返りでは小さいsession indexから掘る対象を選べるため、全eventを監査contextへ投入する必要がない
- Negative: raw tool本文が必要な調査ではsource logを別途、適切な権限と取扱いで確認する必要がある
- Negative: GitHub、対象repository、認証、またはPRとの一意な関連付けを利用できない場合は、PRの最終成果とpostconditionを確認できないgapが残る
- Negative: `sqlite3` CLIとtimezone dataが利用できない環境では監査を開始できないか、一部のtimezone検証に制約が出る
- Negative: resource limitを超える大規模区間は、対象を狭めるか明示的に上限を再設定する必要がある
- Negative: indexだけでは個別の実行順序やfinding本文を確定できず、materialなsessionはdetail収集が必要になる
- Follow-up: raw本文を安全に共有する要件が生じた場合だけ、secret分類とredaction contractを別の論理変更として設計する

## Policy Anchors

- Reusable workflow and user-facing collection contract: `skills/audit-codex-work-quality/SKILL.md`
- Collector source: `skills/audit-codex-work-quality/scripts/collect_session_evidence.py`
- Executable contract: `skills/audit-codex-work-quality/scripts/test_collect_session_evidence.py`
- General source, contract, and ADR placement rules: `AGENTS.md`
