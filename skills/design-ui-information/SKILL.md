---
name: design-ui-information
description: UIを少ない視覚語彙と一貫した意味対応でシンプルに設計し、既存実装を盲目的に踏襲せず、cardや常設説明を必要な場合だけ使う。UIの設計・実装・レビューで、design language、token、primitive、card、panel、container、角丸surface、画面端の余白、icon-only control、常設説明、loading表示、spinner、skeleton、progress bar、視覚階層、情報密度、progressive disclosure、基本的なkeyboard・accessibility対応を判断するときに使う。
---

# Design UI Information

UIを構成する視覚的な概念を最小限にし、各要素へ一つの明確な役割を持たせる。主要タスクと現在状態を、まず形、配置、icon、色、motionで伝える。文字は、視覚設計だけでは意味が一意にならない場合、または安全、回復、アクセシビリティ、法令上必要な場合にだけ使う。情報量の少なさを保ちながら、理解、安全、回復可能性を損なわない。

## Design authority

表現を選ぶときは、次の順で根拠を評価する。

1. 明示された利用者要求とproduct要件
2. 意味、安全、回復、accessibilityの原則
3. 承認済みのdesign system、token、semantic primitive
4. 妥当性を確認できた既存画面とcomponent
5. 単に頻出している既存実装

既存実装は採用候補であって権威ではない。頻出していることだけを根拠に表現を複製しない。Consistencyは見た目を一律に揃えることではなく、同じ意味を同じ表現へ対応させることとして扱う。原則に反する既存patternはdesign debtとして識別し、新しい画面へ伝播させない。局所変更で全面修正できない場合も、既存の誤りを増やさず、境界の不整合を報告する。

## 視覚語彙とcomposition

装飾前のsemantic structureから始める。見出し、本文、操作、状態を通常のflowと配置で組み、groupingは次の弱い手段から順に使う。

1. 近接と余白
2. Alignment
3. Typography
4. Dividerまたは弱い背景差
5. 独立surface

前の手段だけで意味が伝わるなら、次の手段を追加しない。Spacing、type scale、color、radius、border、shadow、motionは既存tokenへ寄せ、任意値を増やさない。既存systemがない場合は、今回必要な最小の語彙だけを定義する。異なるsemantic roleを説明できない新しいtokenやvariantを追加しない。

Flatな単一surfaceを既定にする。画面全体、page本文、dialog本文を「とりあえず角丸card」で包まない。主要surfaceは原則としてviewportまたは親領域の端まで届かせ、外周の角丸によって背景色や白い空白が四隅へ偶発的に露出しないようにする。

Cardは、独立して選択、並べ替え、移動、展開、反復できるsemantic unitであり、周囲から分離することが操作理解に必要な場合だけ使う。単なるgrouping、余白確保、装飾、情報量への不安を理由にcardを追加しない。Sectionはまず余白、alignment、typography、divider、背景色の弱い変化で分ける。Cardを使う場合も入れ子を避け、border、shadow、radiusを重ねない。

浮いたsurfaceが必要なpopover、menu、dialog、drag対象などは、背面とのz軸関係をshadow、overlay、motionで示す。意図的なframed layoutを採る場合は、外側のbackdropも設計し、四隅やsafe areaにdefault背景が漏れないことを確認する。

実装では、汎用的な`Card`や装飾containerより、意味を持つ少数のprimitiveを優先する。たとえばshell、toolbar、content、section、stack、row、divider、button、icon button、dialog、popover、spinner、progress、skeletonとして責務を表す。独立操作が必要なsurfaceは、`SelectableItem`や`DraggableItem`のように用途を名前へ出す。要素を除いたときに意味、操作、安全、accessibilityのいずれも失われないなら除く。

## 手順

1. **主要タスクと通常状態を特定する。** 利用者、目的、現在状態、次の操作、不可逆または高コストな影響を整理する。正常系だけでなく、空、読込中、成功、エラー、権限不足、部分データの状態も対象にする。

2. **既存のdesign languageを監査する。** Token、primitive、代表画面、componentを調べ、承認済みの規則、妥当なpattern、単なる反復、design debtを分ける。既存箇所の多さを正当性の代用にしない。

3. **最小の表現手段を選ぶ。** Surfaceを増やす前に、単一surface上の階層で表現できるか確認する。次の順で意味を伝えられるか判定し、上位の手段だけで初見の利用者が誤認なく判断できるなら下位を追加しない。
   1. 形、配置、余白、色、motion、既知のicon
   2. 短いlabel
   3. 補足文またはtooltip
   4. 長い説明

   Icon-only controlは、対象利用者に意味が一意に伝わり、同一画面の他のiconと区別できる場合だけ使う。Visible labelを省いてもaccessible nameは必ず残す。色だけを唯一の手掛かりにしない。

4. **表示情報を棚卸しする。** 各label、文、tooltip、badge、icon、statusを次へ分類する。
   - `task`: 今できること
   - `state`: 起きたこと、または現在の状態
   - `action`: 操作名、affordance、移動先
   - `safety`: 影響、対象範囲、確認、回復方法
   - `error`: 原因、影響、回復可能な次の操作
   - `accessibility`: accessible name、説明、focus順、非視覚的な代替
   - `legal`: 同意、適格性、policy、常に参照可能であるべき開示
   - `supplemental`: 理由、履歴、例、定義、まれな例外

5. **意味ではなく重複を削る。** 視覚階層、control label、状態表現、空間的なgroupingですでに伝わる事実は、重ねて説明せず削るか短くする。未知の操作、曖昧な状態、安全境界、エラー回復、アクセシビリティ、法令対応に必要な文言は残す。抽象的な安心表現より、具体的な動詞と結果を使う。

6. **Loadingを文字ではなく状態表現で設計する。** 処理の範囲と進捗の性質に合う表示を選ぶ。
   - 部分的で短い待機: 対象controlまたは領域だけにspinnerを置く。
   - Content取得: 最終layoutに近いskeletonを使い、layout shiftを抑える。
   - 進捗を測定できる処理: Progress barを使い、数値が利用者の判断に役立つ場合だけ割合や残量を表示する。
   - Background処理: 操作を妨げない小さなstatus indicatorで示す。
   - 利用者の入力、判断、再試行が必要: 必要なactionを短い文字で示す。

   Spinner、skeleton、progress barだけで待機状態が明確なら、「読み込み中です」「しばらくお待ちください」のようなvisible copyを重ねない。Visible copyを省いても、screen reader向けのstatus通知、busy state、進捗値は提供する。長時間化、停止、失敗では、待機表現のまま放置せず、原因または現在状態と回復可能な次の操作を示す。

7. **Progressive disclosureを適用する。** `task`、`state`、`action`、`safety`、エラー回復、必須のアクセシビリティ・法令情報は必要な時点で利用可能にする。理由、履歴、例、定義、まれな例外は、明示的な詳細表示、secondary view、tooltip、後続stepへ移す。先送りした情報は発見可能かつ支援技術から到達可能にし、利用者が今判断すべき内容を隠さない。

8. **密度と階層を調整する。** Grouping、余白、typography、alignment、divider、段階表示によって優先度を見せる。弱い階層を説明文やcardの追加で補わず、先に階層を直す。一方、一覧性、比較、翻訳、localization、弱視、認知負荷、支援技術を損なう場合は無理に圧縮しない。

9. **安全、エラー、基本accessibilityを守る。** 破壊的または重大な操作では、確定前に対象範囲と影響を示し、利用可能な取消、undo、回復方法を明確にする。エラーでは失敗した対象、保持された状態、回復可能な次の操作を示す。Native control、visible focus、accessible name、論理的なfocus順、contrast、status通知、色以外の手掛かりを維持する。Hoverだけで利用できる操作を作らず、一時surfaceはplatform慣習に沿って閉じられるようにする。

   全機能のkeyboard完遂、複合widgetの矢印key操作、厳密なfocus管理、shortcut体系、keyboard E2E testは常時必須にしない。明示要件、業務・生産性tool、keyboard中心の利用者、custom widgetがある場合にだけKeyboard UX contractとして追加する。

10. **描画結果と一貫性を検証する。** 実装後、代表的なviewportと状態でscreenshotまたはlive renderを確認する。通常、空・読込中、成功、エラー、狭幅・mobile、必要に応じてzoom・文字拡大を含める。主要タスクが目立つこと、同じ意味が同じ表現になっていること、不要なtoken、variant、card、入れ子surfaceがないこと、画面端・四隅・safe areaに意図しない背景が露出しないこと、icon-only controlが一意に判別できること、loading表示の範囲と進捗が分かること、詳細が発見可能なこと、重要情報が欠けないことを確認する。視覚確認できない状態は記録し、DOM、accessibility、interactionの直接checkで代替する。

## 判断チェック

- 初見の利用者が長い説明を読まず、現在状態と安全な次の操作を特定できるか。
- 既存画面の頻出patternではなく、要求、意味、承認済みtoken・primitiveを根拠に表現を選んだか。
- 同じ意味を同じ表現へ対応させ、原則に反する既存patternを新しい画面へ伝播させていないか。
- Semantic structureを先に作り、近接、余白、alignment、typographyで解けるgroupingへ強い装飾を加えていないか。
- 新しいtoken、variant、surfaceは、既存語彙と異なる役割を説明できるか。
- Page全体や主要領域を理由なくcard化せず、単一surfaceと視覚階層で構成できているか。
- Cardは独立したsemantic unitに限定され、単なるgroupingや装飾のために使われていないか。
- 外周の角丸、margin、safe areaによって、画面端や四隅に意図しない背景色・白い空白が露出していないか。
- Cardの入れ子や、border、shadow、radiusの重複を避けているか。
- 文字を加える前に、形、配置、icon、motionで同じ意味を一意に伝えられないか確認したか。
- Icon-only controlはvisible labelなしでも意味が明確で、accessible nameを持つか。
- Loadingは処理範囲と進捗に合うspinner、skeleton、progress bar、status indicatorで示し、重複するvisible copyを置いていないか。
- 各表示文が`task`、`state`、`action`、`safety`、`error`、`accessibility`、`legal`のいずれかに必要か。
- 先送りした詳細が任意情報であり、役立つ時点で発見できるか。
- 説明文が重複していた情報を、視覚階層で伝えられているか。
- 安全、回復、アクセシビリティ、localization、法令上の開示を維持したか。
- Native control、visible focus、accessible name、hover以外の経路という軽量baselineを維持したか。
- 強いKeyboard UX contractが必要なproductかを判定し、不要な場合に重い要件を一律適用していないか。
- 情報の優先度が変わる状態とviewportをscreenshotまたはlive checkで確認したか。
