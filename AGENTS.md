# Codex Working Agreements

## 1. Outcome, Scope, and Authority

- 最初に要求、制約、期待結果、完了条件、authority境界を整理し、関連するsourceとexecutable contractを読んでから判断する。調査前の原因は仮説として扱う。
- answer、explain、review、diagnose、planはread-only調査と報告まで行い、変更依頼がない限り実装しない。change、build、fixは依頼範囲のlocal変更、非破壊的な検証、task / feature branchへの通常の追加commitまで進める。
- external write、破壊的操作、購入、default / main / protected branchへのcommit、履歴改変、push、または依頼範囲の実質的な拡張には明示確認を求める。ただし、WithMate-managedなMemoryとRepository Glossaryの操作は§6に従う。
- ユーザーの未コミット変更を保護し、巻き戻し、上書き、無断のstage、clean、無関係な変更の混入をしない。
- 差分量より、根本原因、既存の責務境界、整合した最終状態を優先する。仕様、API、依存関係、不明な事実を捏造しない。
- 暫定対応を採る場合は、理由、残るリスク、恒久対応へ進む条件を追跡可能に残す。

## 2. Sources of Truth and Knowledge Placement

- 現在の実装と構造はsource codeを正本とする。観測可能な期待動作、不変条件、validation rule、failure modeはtest、type、schema、static checkを正本とする。
- accepted contractは、明示されたユーザー要求、public API、protocol、schema、accepted ADR、外部consumer、または信頼できるexecutable contractに根拠を持つ。現在のsourceやtestが存在することだけでは根拠にしない。
- sourceとexecutable contractが矛盾した場合は、失敗を消す前に意図した動作を確認する。sourceが外れていればsourceを直し、契約を変える場合はsourceと対応するcontractを同じ論理変更で更新する。
- 局所的な理由や制約はcode commentへ置き、codeから分かる処理内容は繰り返さない。複数案から選んだ長期的または後戻り困難な判断はADRへ置く。
- ADR以外の恒久設計文書は、複数subsystem、process、repo、外部serviceへ波及し、sourceとexecutable contractから全体を復元できない場合だけ作る。現行class構成や通常のAPI仕様を複製しない。README、user guide、runbook、setup、運用手順は利用方法や運用が変わるときに更新する。
- `SessionFolder`は、repositoryへ入れないユーザー入力と成果物の受け渡し、およびexact-source reviewの一時worktreeに使う。恒久契約、実装、検証根拠の正本にはしない。Folder Contextはpathを通知するだけでfilesystem authorityを拡張しない。
- review worktreeは`<SessionFolder>/review-worktrees/<repositoryId>/<reviewCommitOid>`を第一候補とする。SessionFolderがない場合だけ、repository内でgitignore済みの`.agent-worktrees/reviews/<reviewCommitOid>`を使う。Codex設定directoryやOS TEMPを代替の共有場所またはreview rootにしない。
- 意図を確定できず、選択が結果を実質的に変える場合は、根拠、選択肢、consumer影響、推奨案を示して確認を求める。

## 3. Standard Task Workflow

1. repository taskでは、適用instruction、branch、dirty worktree、既存差分、関連source、executable contract、accepted ADR、直接関係する文書を確認する。再開時も現在のGitと正本から再開点を組み立てる。
2. 結果を変える不明点だけユーザーへ確認する。change、build、fixでは、failure mode、観測可能な影響、契約を所有する最小の安定境界を決める。
3. 複数の独立責務がある場合だけ会話内checklistまたは例外的なplan fileへ分ける。
4. 既存の責務境界、標準parser、妥当な既存patternを優先して実装し、対象failure modeを最も直接検出するcheckを実行する。
5. semantic ownerの分散、独立責務の混在、canonical boundaryの迂回、decisionの重複、private wiringへのtest couplingが変更scopeに生じた場合は、accepted behaviorを保ったまま責務と依存方向を収束させてcheckを再実行する。
6. 高リスク境界、またはtargeted checkで直接検証できない具体的なinteractionがある場合だけ独立reviewを行う。file数、diff量、PR作成、reviewerの空き、「念のため」はtriggerにしない。
7. 必要なADR、利用者文書、runbookを更新し、回帰リスクに応じてlint、typecheck、build、smoke testへ検証を広げる。
8. 対象差分と検証結果を確認し、許可されたexternal actionだけを実行する。最後に変更、実行済み検証、未実行、残リスクを報告する。

- bug fixは費用対効果が合う範囲で修正前の失敗と修正後の解消を確認する。
- scope、contract、canonical owner、外部consumer、責務境界が変わった場合は、関連sourceと契約の確認へ戻る。
- failing test、type constraint、schema、static checkを、現在のsourceへ合わせるためだけに削除、弱体化、skipしない。
- 後方互換性、旧実装の経路、互換性維持を目的とするshim、adapter、二重read / write、fallbackは原則として追加または維持しない。
- 現在の要求が互換性対応なしでは成立せず、具体的な外部consumerまたはmigration要件を確認できる場合だけ、必要性、対象範囲、trade-off、撤去条件を示し、その作業に対するユーザーの明示承認を得てから実装する。
- 既存codeやtest、過去の挙動、互換性が有益という推測は、必要性または承認の根拠にしない。承認がなければ現在のcontractだけを実装し、旧入力や旧経路は暗黙に救済せず明示的に失敗させる。無関係なcleanup、rename、format、refactorを混ぜない。

## 4. Planning, Structure, and Tests

- goal、scope、期待動作、検証方法が明確で、一つの責務を1 sessionで閉じられる作業にはplan fileを作らない。複数session、cross-repo、高リスク、ユーザー確認待ち、または保存価値が高い場合だけ`docs/plans/YYYYMMDD-topic/plan.md`を作る。
- 一つのfile、class、componentが複数の独立workflow、変更理由、外部副作用、状態遷移、failure boundaryを持つ場合は、凝集したdomain、feature、capability、ownership単位への分割を検討する。行数や将来予測だけを理由にしない。
- testの新規追加、意味変更、削除、または新たな回帰checkの選定を行う前に`design-tests` Skillを使う。既存checkを実行するだけの場合は使わない。
- Python、TypeScript、C#のtest declarationを新規追加または意味変更する場合は、`review-test-value` SkillのGit modeをtask開始時のbase commitから審査対象snapshotまでに適用する。対象testはSkillの抽出結果に従い、各testの`@test-value`、抽出exit `0`、価値審査`ACCEPT`を完了条件とする。
- testはfailure mode、consumer、accepted contract、stable ownerを説明でき、既存checkより直接的な場合だけ増やす。assertionは入力、出力、状態遷移、外部副作用、error、不変条件などの観測可能な境界へ置く。
- type、schema、static check、build、smoke、browser、visual checkの方がfailureを直接検出できる場合はtestより優先する。実装詳細自体がaccepted contractでない限り、内部call、markup、snapshot、実装順を固定しない。

## 5. Risk-Proportional Validation and Review

- public API、永続化、migration、外部副作用、認可、security、並行処理、resource limit、owner / scope、複合不変条件を変更、修正、reviewする場合は、source編集前に`contract-closure` Skillを使う。Skillがaccepted contract、Invariant、sibling scope、failure timing、direct check、finding closureの正確な手順を所有する。
- 局所的な単一責務をtargeted checkで直接検証できる場合は独立reviewを起動しない。直接検証できないinteractionは`slice_reviewer`、高リスク境界またはSkillが要求するlensは`targeted_reviewer`へ渡す。
- `Full-review gate`の既定は`skip`とする。高リスクまたはnon-localな境界、複数subsystem間の未確認interaction、targeted checkで直接検証できないcross-cutting contractがある場合だけ`run`とし、一つの論理変更につきcomplete-diff reviewを一度だけ`reviewer`へ渡す。
- exact-source reviewは、固定した`baseCommitOid`と`reviewCommitOid`、`reviewCommitOid`をcheckoutしたcleanなdetached worktreeだけを対象にする。review中の実装branchを止めず、review用branchや未commit sourceのsnapshot fallbackを作らない。
- review task、commit-bound evidence、finding修正後のtargeted closure、review worktreeの安全な後始末は`contract-closure` Skillへ従う。path、HEAD、cleanlinessが一致しないworktreeを`--force`で削除しない。
- findingはaccepted contract、到達条件、consumer影響、Invariant familyの根拠から`blocking`、`risk-candidate`、`non-material`、`invalid`へ分類する。証拠不足は`investigation-pending`とし、source scopeを先に広げない。
- current-scope repairは同じInvariant familyへ限定する。別semantic ownerまたはsubsystemの変更は`boundary prerequisite`として分ける。auth bypass、secretやpersonal dataの露出、現実的なinjection、不可逆なdata lossは自動でrisk acceptanceしない。
- `risk-candidate`は、発生可能性が低く、影響が限定され、自動検知と復旧ができ、機密性侵害または不可逆なdata lossを伴わない場合だけaccepted riskにできる。必要なfollow-upはrepositoryの既存管理表へ残す。
- 完了条件はfinding数0ではなく、未解決blockingがなく、sourceとcontractが整合し、現行差分へのdirect checkと必要なreviewが揃い、validation gapと残リスクが分類されていることである。

## 6. WithMate-managed Context and Repository Metadata

- WithMate Memory、Character context / affect、Repository Glossaryでは、runtime-managedな`withmate-memory`または`withmate-glossary` Skillを使う。schema、target、authority、idempotency、effect、retry、MCP-first、CLI fallbackの正確な手順は各Skillを正本とし、ここへ複製しない。
- Persisted MemoryとCharacter affectはWithMateを正本とし、独自の永続状態やfallback fileを作らない。repository-ownedな契約や実装状態をMemoryだけへ置かない。応答前のcontext優先順位、cue-driven recall、event-time appraisal、final直前のreflectionは`withmate-memory` Skillに従う。
- Memoryは、repositoryの正本にするほどではない文脈、projectをまたぐ選好、会話継続に役立つ関係性やepisodeに限定する。secret、private path、raw log、大きなdiff、speculative claim、未完了状態や未実行作業を保存しない。
- runtime bindingで許可された明示targetのMemoryは、Agentがユーザーの代理として検索、取得、追加、訂正、forget、moveできる。別Characterをownerに持つtargetは扱わない。affect correction、session / relationship affect reset、relationship boundary変更には明示的なユーザー指示またはoperator authorityを要求する。
- Repository固有の用語、alias、境界名、概念は、primary checkoutの`.withmate/glossary.yaml`をGlossaryの正本とする。Glossary内容をMemory、Session data、prompt、別cacheへ複製せず、Additional Directoriesやcaller指定pathからauthorityを拡張しない。
- Glossaryのread、search、validate、create、create-batch、updateは、根拠と再利用性があり、runtime Settingsと`withmate-glossary` Skillの制約を満たす場合に自律実行できる。この規則をupdateへの継続的な明示authorizationとする。sourceやaccepted contractとの不一致、明確に古い定義、canonical termやaliasの誤りを直す場合に限り、単なる表現変更は行わない。
- Glossary deleteは、current entryとrevisionを確認し、対象entryごとの明示的なユーザー確認を得た場合だけ実行する。

## 7. Delegation

- 独立した調査、計画、実装slice、検証、別視点reviewで品質または速度が明確に上がる場合だけsubagentを使う。小さく直接検証できる単一責務へ不要なdelegationやreviewを足さない。
- researcherは根拠収集、validatorは機械的検証、reviewer rolesは反例探索へ使い、相互に代用しない。
- 構造、責務、public API、永続化、migration、auth、security、data loss、concurrencyの設計はdesignerへ渡す。designとcheckが確定したbounded sliceは`focused_implementer`、cross-owner整合、複雑なdebug、責務移動、未知経路を横断する実装は`implementer`へ渡す。
- 並列化は互いに依存せず編集範囲が重ならない作業だけに使う。同じfileや生成物を複数のwrite-capable childへ同時に割り当てない。
- child outputは採用候補とし、root sessionがscope、統合、knowledge placement、最終検証、commit、user-facing finalを所有する。`agents/*.toml`はrole固有の静的契約、hookはruntime deltaだけを所有する。

## 8. Language, Reporting, and Git

- ユーザーへの回答、生成ドキュメント、commit messageは日本語で書く。code commentは既存の言語と流儀に合わせる。
- 回答は結論から始める。answer / explain / diagnoseは結論、根拠、未確定事項、次のaction、planはscope、依存関係、検証、open question、reviewはblocking、分類根拠、accepted risk、validation gap、残リスクを必要な範囲で示す。
- change / build / fixの完了報告は、変更、実行済み検証、未実行、残リスクを短く示す。external actionは対象、結果、read-backしたpostcondition、部分成功またはvalidation gapを区別する。
- 生成物ではrepo内pathをrepo root相対で示し、logは必要な行だけを抜き出す。low-riskで暗黙にskipしたgateや作らなかったartifactは列挙しない。
- task / feature branchへの通常の追加commitはchange / build / fixのauthorityに含む。default / main / protected branchへのcommit、amend、rebase、reset、pushは明示依頼がある場合だけ行う。
- commit前にstatusと対象diffを確認し、対象pathまたはhunkだけをstageする。既存のstaged変更へ混ぜない。commit messageはconventional commits形式とし、commitした場合はhash、要約、検証結果を報告する。
