---
name: review-test-value
description: Python、TypeScript、C#の変更testをGit差分から決定論的に抽出し、構造化された@test-value metadataとtest本文を通常のread-onlyサブエージェント審査へ渡す。runtime test collectionや動的生成caseの展開には使わない。
---

# Review Test Value

このSkillは、変更されたtestの選定と構造化recordの抽出を決定論的なscriptへ任せ、意味判断を親エージェントと通常の`general_luna`へ委譲する。対象の選定、metadataの構文、test declarationとsource範囲の対応付けはscriptの結果を正本とし、親がrecordを都合よく選び直したりmetadataを補完したりしない。

## Workflow

1. repository instructionとtask開始時のbase commitを確認する。
2. 対象言語の宣言範囲と対応形式を[Source Adapters](references/source-adapters-v1.md)で確認する。コメント形式を追加・修正する場合は[Test Value Comment](references/comment-format-v2.md)を読む。
3. 新規・意味変更・削除・移設されたtestは、baseから対象snapshotまでのGit差分で抽出する。対象pathやline rangeを手で選ばない。Python、TypeScript、C#は言語ごとに呼び出す。

```powershell
python -X utf8 skills/review-test-value/scripts/extract_test_values.py `
  --root <repository-root> `
  --changed-from <task-base-commit> `
  --language python
```

working treeが既定で、indexだけを対象にする場合は`--staged`、commitへ固定する場合は`--head <commit>`を追加する。[Git選択契約](references/git-selection-v1.md)のsnapshot semanticsを維持する。

4. exit `0`のJSONを読み、`tests`と`transitions`の全recordを確認する。exit `1`は抽出結果にdiagnosticがあるため、sourceまたはmetadataを直して再抽出する。exit `2`はCLI、adapter、I/Oなどの失敗であり、部分結果をレビューへ渡さない。
5. 親エージェントは、相互に独立して扱えるrecordまたは小さなbatchごとに、利用できるサブエージェント枠の範囲で通常の`general_luna`へreviewを委譲する。並列に委譲できない場合は親の判断で順次扱う。
6. 各review依頼には、repository root、task baseと対象snapshotまたは現在のdiff、対象fileとlocator、抽出recordのmetadataとtest source、対象scope、read-onlyであること、下記のreview観点と適用される統合基準を含める。production codeやfixtureを親が事前に収集せず、`general_luna`自身が対象testから必要な範囲をrepository内で探索する。
7. 親エージェントは自然言語のreview結果を読み、共通`AGENTS.md`の「統合優先・修正分離」に従って各指摘の扱いと完了可否を判断する。必須確認や統合判定に必要なcontext不足、ブロッカー修正、新たな変更の確認に限り、対象recordへ追加contextや`general_sol`などの追加reviewを依頼できる。非ブロッカーの解消や同じ入力でのvarianceを期待する自動retryは行わない。

reviewerの起動失敗、内容のない応答、対象recordを確認していない応答はreview済みとして扱わない。親が原因と不足内容を確認し、必要なら対象recordだけへ追加contextまたは別reviewを依頼する。

削除・移設では`transitions`の`DELETED.before`、`ADDED.after`、`SURVIVED.after`を漏れなく確認する。削除だけで過去のreview義務が解消したとみなさず、現在の契約に対して保持、移設、削除の根拠を親が判断する。

## 変更完了確認と恒久保持

今回の変更で削除・非表示にした処理や表示内容が存在しないことだけを確認するために追加したtestは、恒久testとして扱わない。必要なら実装中に一時検証として実行し、確認と修正が完了したらそのtestを削除する。`lifecycle = "ephemeral"`を付けた場合も、`remove_when`の条件を満たしたら削除し、metadataを残すこと自体を恒久保持の根拠にしない。

旧挙動の不在自体が現在の公開契約、security、privacy、accessibilityなどで継続して要求される場合は、恒久testの候補として評価する。「回帰対策」「以前壊れたから」だけでは保持理由にならない。保持するには、次の内容をreviewで明記する。

- 現在も有効な要求または契約と、反証可能なfailure mode
- 違反したときの利用者、データ、主要機能などへの具体的な影響
- 既存test、type、schema、static、build、smoke、policy checkなどで代替できない理由
- CI実行時間と保守負担を継続して負う価値

metadataを使う場合は、既存の`impact`に影響、`distinction`に既存checkとの差を記載できる。これらのfieldや新しいschemaを、恒久保持の理由を隠すために追加・補完しない。

## 一回のreviewで確認する観点

`general_luna`には三つの観点を一つの依頼で渡す。観点ごとに別の依頼や専用agentへ分割しない。

### metadata

- claimが具体的で反証可能なfailure modeを示すか。
- fault、observable、observation boundary、oracle、scope、lifecycleが自己完結しているか。
- testで検証すべき内容か、type、schema、static、build、smoke、policyなど別のcheckが直接担うべき内容ではないか。
- 曖昧な主張、循環した期待値、実装詳細を正当化する記述がないか。

test sourceやproduction codeからmetadataに書かれていない意味を補完しない。oracleの参照先が入力されていない場合、その存在や妥当性を確認済みと扱わない。

### metadataとtest本文

- assertionがmetadataのfailure modeとobservableを直接検出するか。
- setup、action、assertionがmetadataのscopeとobservation boundaryに対応するか。
- metadataより弱い確認、別の挙動の確認、常に成功するoracleになっていないか。
- private wiring、内部順序、現在のclass構成などaccepted contractでない実装詳細へ過剰結合していないか。
- 既存testやtype、schema、static、build、smoke checkと実質的に重複していないか。

### test本文とproduction code

`general_luna`はtest sourceからproduction code、fixture、helper、mock、oracle、SUT、契約を自分で辿る。

- testが意図したproduction pathを実際に通るか。
- mock、fixture、helperが欠陥を隠したりproduction behaviorを迂回したりしていないか。
- 欠陥を入れたときassertionまで観測が伝播するか。
- production contractに対して保持価値があるか。今回の変更完了確認だけならtemporaryとして削除し、現在のcontractやpolicyを守るtestなら保持理由と継続コストを確認する。削除、移設、再設計が適切な場合はその判断も示す。
- supplied contextだけでは判断できない具体的事項があるか。

通常の自然言語reviewで、結論、理由、具体的な問題、統合への影響、判断に足りないcontextが分かるよう依頼する。停止を提案する場合は適用する統合基準と根拠を示し、testの改善価値だけで全指摘をブロッカーにしない。返答のJSON schema、必須field、固定verdict、識別子の復唱を応答契約にしない。

## 完了判断

親エージェントは次を確認してreviewを完了する。review完了と、指摘の全件修正・統合可否は分ける。

- extractorが成功し、Git差分から得た全対象recordを確認できている。
- `general_luna`のreview結果を全recordまたは明示したbatchについて読んでいる。
- 各指摘の扱いが決まり、非ブロッカーはプロジェクトで定義した管理先へ引き継いでいる。現diffへの全件反映は要求しない。
- context不足は、必須確認・統合判定を妨げるものと、後追い調査に分離できるものを区別し、未確認の範囲と影響を明示している。
- 追加reviewを実施した場合は、対象と結果、未完了の確認を区別している。

統合へ進むにはブロッカーの解消と必須条件の成立が必要であり、未実施の審査や失敗したcheckを後追い扱いで免除しない。抽出・全recordのreview・必要なtest実行・契約を弱めないことは維持する。

抽出scriptは抽出とdiagnosticの生成だけを行い、reviewerの起動や判断を管理しない。Git commit IDは差分範囲の指定にだけ使い、追加の同一性証明をreviewの入力、出力、完了条件にしない。

## Validation

抽出器、parser、Git選択を変更した場合は、Pythonと多言語の決定論的回帰testを実行する。

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values_multilang.py
python -X utf8 -m py_compile skills/review-test-value/scripts/extract_test_values.py
python -X utf8 -m py_compile skills/review-test-value/scripts/git_diff_selection.py
```

Skillのfrontmatter、相対参照、未完了placeholderを確認する場合は、skill-creatorが提供するvalidatorを実行する。

```powershell
python -X utf8 <skill-creator>/scripts/quick_validate.py skills/review-test-value
```
