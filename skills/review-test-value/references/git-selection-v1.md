# Git Selection v1

## Purpose

Git差分へ含まれる新規・意味変更・削除・移設testを抽出し、変更していない既存testへ`@test-value`の一括導入を要求しない。

## Invocation

working treeをtask baseと比較する。

```powershell
python -X utf8 <skill-dir>/scripts/extract_test_values.py `
  --root <repository-root> `
  --changed-from <task-base-commit> `
  --language python
```

`--language`は`python`、`typescript`、`csharp`のいずれか一つとする。複数言語を変更した場合は言語ごとに実行する。

比較対象をindexへ限定する場合は`--staged`、commitへ固定する場合は`--head <commit>`を追加する。両方は同時に指定しない。省略時はworking treeを使う。

## Snapshot Semantics

- working tree: base以降のcommit、staged、unstaged、non-ignored untracked fileを含む。sourceはfilesystemから読む。
- staged: baseとindexを比較し、sourceはindexから読む。
- head: baseと指定commitを比較し、sourceは指定commitから読む。

baseとheadは直接比較する。CLIはmerge-base、upstream、task開始commitを推測しない。

working treeのsource pathがsymlinkなどによってrepository root外へ解決される場合は、外部内容を読まず`SOURCE_OUTSIDE_ROOT`を返す。stagedとheadはGit objectから読み、working treeのsymlinkを追跡しない。

## Selection

- 対象言語の変更fileはGit差分から自動発見する。個別pathやline rangeは受け取らない。
- test declarationのrange、または直接隣接する`@test-value` blockへdiff hunkのold-sideかnew-sideが交差したsurviving recordを選ぶ。
- base側recordのdeclaration startをnew側へ投影する。開始境界を削除した場合は削除anchorの直後へ対応付け、先頭decoratorやattributeだけを削除して開始行が変わったsurviving recordも選ぶ。
- zero-count insertionはold anchorの直後へ挿入されるため、anchor行自体の投影位置は動かさない。宣言前のmetadata追加と宣言直後の本文追加を分けて扱う。
- test本文だけ、構造化コメントだけを変更した場合も選ぶ。
- metadata markerや隣接関係を壊してnew-sideでblockを結合できなくなった場合も、base側のrecord対応からsurviving testとdiagnosticを選ぶ。
- surviving testの本文行または隣接する`@test-value` blockを削除した場合は、new-sideの削除anchorから対応recordを選ぶ。test declaration全体またはtest file全体の削除はbase snapshotのrecordを`DELETED.before`へ保持する。
- 対応sourceはGit属性の`-diff`やtext conversionを適用せず、raw textとしてhunkを取得する。LFとCRLFの相互変換だけではrecordを選ばず、同じfileで同時に行われた内容変更は選択対象に残す。
- 変更していないrecordと、そのrecordだけに属するmetadata diagnosticは結果から除外する。
- pure renameは選ばず、空の`tests`と`transitions`を返す。renameと同時に内容を変更した場合は変更recordを選ぶ。
- Git modeは変更recordごとに`ADDED`、`SURVIVED`、`DELETED`のtransitionを返す。file pair内で`source_text`と解析済み`metadata`の直接比較、およびhunkから投影したdeclaration位置を照合し、symbol名だけでは対応付けない。内容一致と位置が別recordを指すなど根拠が競合する場合や、以下の削除・置換条件にも該当せず対応を確定できない場合は`RECORD_TRANSITION_UNRESOLVED`で停止する。
- 遷移未解決の`message`には、旧宣言のpath・symbol・行範囲、内容一致・開始行投影・開始行の置換hunkそれぞれの候補と絞込み後候補、保持された旧行から現行行への投影と交差する選択済み宣言を示す。一貫した対応根拠が不足していることと、全件審査が未完了であることを明記する。診断の文面は固定schemaではなく、明示した削除・置換条件の外で曖昧な対応を救済しない。
- 宣言開始行の置換hunkに複数の現行宣言があり、未変更の旧宣言行に空白・閉じ区切り以外の本文が残る場合は、その行範囲を投影し、その全範囲を内包する宣言へ位置候補を絞る。一意で一貫した対応があれば旧本文と現行本文を`SURVIVED`へ保持する。
- 宣言開始行が削除・置換され、内容一致候補も絞込み後の位置候補もなく、保持された旧宣言行のすべてが未対応の選択済み現行宣言内へ投影され、その所属先が複数宣言に分かれる場合は、一対多の置換として旧recordを`DELETED.before`へ保持する。新recordはこの旧recordの対応先として消費せず、他の旧recordとの一意な対応もなければそれぞれ`ADDED.after`へ保持する。本文行と閉じ行の分散もこの条件に含めるが、関数名や行の業務上の意味から存続関係を推測しない。宣言外への投影や内容・位置の競合等、この条件を満たさない未解決は診断を維持する。
- 一対多の`DELETED`／`ADDED`は宣言の審査単位を表し、機能の廃止や業務契約の変更を承認しない。旧・新の全文、source位置、metadataを欠落なく審査へ渡し、reviewerが現在の契約に対する保持・置換・削除理由を判断する。抽出成功をreview完了へ読み替えない。
- 宣言開始行が削除・置換された旧recordは、未変更の旧宣言行が同じ現行宣言に属する場合だけ位置による対応を認める。metadataや閉じ行が隣接recordと共通でも、それだけで存続を確定しない。対応先の宣言がなく、開始行の変更hunkにも現行宣言がなければ`DELETED`として旧recordを保持する。
- 宣言開始行が削除・置換され、未変更の旧宣言行が空白と閉じ区切り（`}`、`)`、`]`、`;`）だけの場合、別recordの対応先に入る等で候補が残らなければ`DELETED`として旧recordを保持する。内容一致候補がなく、開始行の置換hunkに未対応の現行宣言候補が複数ある場合も、閉じ行だけで一つへ絞らず`DELETED`とする。閉じ行間への新しい行・宣言の挿入でも同じである。内容一致や単一の置換hunk候補による一意な対応は維持し、上記の一対多置換条件外の曖昧な対応と内容・位置の競合は引き続き診断する。
- metadataはschema検証を通った文字列、文字列配列、辞書だけを含み、解析失敗時は`null`となる。辞書のキー順は比較へ影響せず、配列の順序は保持する。削除済みv1の解析成功は`metadata`の非nullで判定する。
- `ADDED`と`SURVIVED`の`after`集合は、順序を含めて`tests`と一致する。`DELETED`は`tests`へ含めない。
- `DELETED.before`は、metadataが正常なv1でも未付与でも歴史的な削除証拠として保持する。正常なv1のblock自身の`TEST_VALUE_V2_REQUIRED`と、削除前test自身の`TEST_VALUE_MISSING`だけを固定baseへ適用する現在の移行要求から除き、元version・metadata（未付与なら`null`）・本文を審査へ渡す。削除元の不正metadata、結合不明、未知versionなど他の診断は引き続き停止する。追加・surviving・明示pathの未付与／不正metadataと、新規・surviving・明示pathのv1には従来どおり診断を返す。
- TypeScriptの固定baseにある動的test titleは、対応call構文からタイトル式と宣言全文を一つのrecordへ保持する。`source.symbol`は式を`[title expression: <式のsource text>]`として表示し、式を評価したりloop・parameterized caseを展開したりしない。file全体の削除と個別宣言の削除の両方で`DELETED.before`を審査へ渡し、現行のstatic titleへ一意に対応する場合は`SURVIVED.before`へ保持する。現行snapshot・明示pathの動的title、削除元を含むsyntaxや不正metadata、その他の未対応構文の失敗条件は維持する。
- Gitが移設＋変更を`D`＋`A`へ分けた場合も、削除側と追加側を独立したtransitionとして保持する。pathやsymbol名だけでは`SURVIVED`を作らず、内容・位置で対応を一意に保証できない移設は`DELETED`＋`ADDED`として審査へ渡す。同一file pairには上記の対応・削除・置換条件を適用する。
- source全体の解析を信頼できなくするsyntax、decode、adapter failureは隠さない。
- 静的に識別した未対応test declarationは内部rangeで差分と対応付け、開始行以外の本文変更も`TEST_DECLARATION_UNSUPPORTED`として返す。内部rangeは公開diagnosticへ追加しない。
- 対象言語に変更recordがない場合は空の`tests`と`diagnostics`を返し、exit `0`とする。

明示pathを渡す従来modeは、既存file全体の審査やmigrationにだけ使う。新規・変更testの標準審査でGit modeをpath指定へ置き換えない。

明示path modeは比較snapshotを持たず、`transitions: null`で遷移が適用外であることを表す。Git modeで変更がない場合の空配列とは区別する。

## 統合履歴による審査

直比較が`RECORD_TRANSITION_UNRESOLVED`だけで停止した場合は、同じtask baseから対象snapshotまでのfirst-parent統合履歴を使い、全隣接差分を抽出・審査する別経路を利用できる。共通本文から作者の意図を推測せず、実在する削除・再追加等のcheckpointで証拠を分ける。直比較の失敗はそのまま記録し、この経路の成立を直比較のexit `0`と呼ばない。CLI・result schema・metadata v2は変更しない。

### 範囲と抽出

1. 元のtask baseと対象modeを維持する。`head` modeでは指定commit、`staged`／workingでは開始時の`HEAD`を履歴の終点とし、baseと終点を`git rev-parse --verify <revision>^{commit}`でcommitへ解決する。
2. `git rev-list --first-parent <終点SHA>`に元baseが含まれることを確認する。次のcommandで全区間を古い順に列挙する。各行の先頭がcommit、次が第一親であり、最初の第一親が元base、以後の第一親が直前のcommit、最後のcommitが終点であることを確認する。baseと終点が同一ならcommit区間は空になる。

   ```powershell
   git -C <repository-root> rev-list --first-parent --reverse --parents <元baseSHA>..<終点SHA>
   ```

   baseがfirst-parent鎖上にない、必要な履歴・objectを取得できない、区間が連続しない場合は、この経路を成立させない。merge-baseや別baseへ置き換えたり、成功するcommitだけを選んだりしない。mergeは第一親からmerge結果への全変更を対象とし、side branch内部だけに存在した途中状態は対象に含めない。

3. 全区間について、対象言語ごとに既存のGit modeを実行する。pathやline rangeを指定せず、各区間の`tests`・`transitions`全体を区間とともに保持する。

   ```powershell
   python -X utf8 <skill-dir>/scripts/extract_test_values.py `
     --root <repository-root> `
     --changed-from <第一親SHA> --head <commitSHA> --language <language>
   ```

4. `staged`／workingの場合は、履歴終点SHAを`--changed-from`に指定し、元modeの終端差分も抽出する。`staged`は`--staged`を付け、workingは`--head`も`--staged`も付けない。workingのnon-ignored untrackedも通常どおり含む。確認中に対象snapshotが変わった場合は、変化した範囲の抽出・審査を更新する。
5. 全区間・終端差分がexit `0`の場合だけ、その全出力を審査へ渡す。一区間でも遷移未解決・不正metadata・source解析失敗等が残れば抽出未完了とする。過去commitの追加・surviving testにも通常のmetadata条件を適用し、後の修正・削除で免除しない。削除beforeに対する既存の歴史的metadata例外はその範囲だけで維持する。

### 審査と完了

- reviewerへ元base・最終対象snapshotと、担当区間の両端・抽出recordを渡す。source、locator、契約は該当snapshotで確認し、途中版のpath・行を最終版のものとみなさない。
- 全区間の`tests`と`transitions`を審査する。途中追加後に削除したtestも含め、symbol名等で区間をまたぐrecordを間引かない。`DELETED.before`を落とさず、削除後の`ADDED`を一つの`SURVIVED`へ合成しない。
- 元baseの削除前testと最終testを含む証拠を参照し、最終対象の契約に対する保持・変更・削除・再追加の妥当性を判断する。区間内の抽出成功だけで元baseの要求が最終testに維持されたと推定しない。
- 全区間の抽出成功、全recordの独立審査、指摘の分類・必要な引継ぎを満たしたときに、元base・最終対象・履歴経路を明記して審査完了とする。抽出成功、審査完了、全件修正、統合可否は区別する。

各commit区間と終端差分にも上記の対応・削除・一対多置換条件を適用し、未解決の対応や解析・metadata診断が残れば停止する。履歴を作り直して成功させる経路ではなく、実在する統合履歴で全件審査できる場合だけを扱う。
