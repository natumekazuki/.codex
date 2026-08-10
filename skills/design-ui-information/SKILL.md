---
name: design-ui-information
description: UIを形、配置、icon、motionからシンプルに設計し、安全、エラー回復、アクセシビリティに必要な場合だけ文字を使う。UIの設計・実装・レビューで、icon-only control、常設説明、ヘルプ文、loading表示、spinner、skeleton、progress bar、視覚階層、情報密度、progressive disclosureを判断するときに使う。
---

# Design UI Information

主要タスクと現在状態を、まず形、配置、icon、色、motionで伝える。文字は、視覚設計だけでは意味が一意にならない場合、または安全、回復、アクセシビリティ、法令上必要な場合にだけ使う。情報量の少なさを保ちながら、理解、安全、回復可能性を損なわない。

## 手順

1. **主要タスクと通常状態を特定する。** 利用者、目的、現在状態、次の操作、不可逆または高コストな影響を整理する。正常系だけでなく、空、読込中、成功、エラー、権限不足、部分データの状態も対象にする。

2. **最小の表現手段を選ぶ。** 次の順で意味を伝えられるか判定し、上位の手段だけで初見の利用者が誤認なく判断できるなら下位を追加しない。
   1. 形、配置、余白、色、motion、既知のicon
   2. 短いlabel
   3. 補足文またはtooltip
   4. 長い説明

   Icon-only controlは、対象利用者に意味が一意に伝わり、同一画面の他のiconと区別できる場合だけ使う。Visible labelを省いてもaccessible nameは必ず残す。色だけを唯一の手掛かりにしない。

3. **表示情報を棚卸しする。** 各label、文、tooltip、badge、icon、statusを次へ分類する。
   - `task`: 今できること
   - `state`: 起きたこと、または現在の状態
   - `action`: 操作名、affordance、移動先
   - `safety`: 影響、対象範囲、確認、回復方法
   - `error`: 原因、影響、回復可能な次の操作
   - `accessibility`: accessible name、説明、focus順、非視覚的な代替
   - `legal`: 同意、適格性、policy、常に参照可能であるべき開示
   - `supplemental`: 理由、履歴、例、定義、まれな例外

4. **意味ではなく重複を削る。** 視覚階層、control label、状態表現、空間的なgroupingですでに伝わる事実は、重ねて説明せず削るか短くする。未知の操作、曖昧な状態、安全境界、エラー回復、アクセシビリティ、法令対応に必要な文言は残す。抽象的な安心表現より、具体的な動詞と結果を使う。

5. **Loadingを文字ではなく状態表現で設計する。** 処理の範囲と進捗の性質に合う表示を選ぶ。
   - 部分的で短い待機: 対象controlまたは領域だけにspinnerを置く。
   - Content取得: 最終layoutに近いskeletonを使い、layout shiftを抑える。
   - 進捗を測定できる処理: Progress barを使い、数値が利用者の判断に役立つ場合だけ割合や残量を表示する。
   - Background処理: 操作を妨げない小さなstatus indicatorで示す。
   - 利用者の入力、判断、再試行が必要: 必要なactionを短い文字で示す。

   Spinner、skeleton、progress barだけで待機状態が明確なら、「読み込み中です」「しばらくお待ちください」のようなvisible copyを重ねない。Visible copyを省いても、screen reader向けのstatus通知、busy state、進捗値は提供する。長時間化、停止、失敗では、待機表現のまま放置せず、原因または現在状態と回復可能な次の操作を示す。

6. **Progressive disclosureを適用する。** `task`、`state`、`action`、`safety`、エラー回復、必須のアクセシビリティ・法令情報は必要な時点で利用可能にする。理由、履歴、例、定義、まれな例外は、明示的な詳細表示、secondary view、tooltip、後続stepへ移す。先送りした情報は発見可能かつkeyboard・screen readerから到達可能にし、利用者が今判断すべき内容を隠さない。

7. **密度と階層を調整する。** Grouping、余白、typography、alignment、段階表示によって優先度を見せる。弱い階層を説明文で補わず、先に階層を直す。一方、一覧性、比較、翻訳、localization、弱視、認知負荷、支援技術を損なう場合は無理に圧縮しない。

8. **安全、エラー、アクセスを守る。** 破壊的または重大な操作では、確定前に対象範囲と影響を示し、利用可能な取消、undo、回復方法を明確にする。エラーでは失敗した対象、保持された状態、回復可能な次の操作を示す。Accessible name、操作説明、focus順、contrast、status通知、色以外の手掛かりを維持する。

9. **描画結果を検証する。** 実装後、代表的なviewportと状態でscreenshotまたはlive renderを確認する。通常、空・読込中、成功、エラー、狭幅・mobile、必要に応じてzoom・文字拡大を含める。主要タスクが目立つこと、icon-only controlが一意に判別できること、loading表示の範囲と進捗が分かること、詳細が発見可能なこと、重要情報が欠けないこと、密度による操作・アクセシビリティ回帰がないことを確認する。視覚確認できない状態は記録し、DOM、accessibility、interactionの直接checkで代替する。

## 判断チェック

- 初見の利用者が長い説明を読まず、現在状態と安全な次の操作を特定できるか。
- 文字を加える前に、形、配置、icon、motionで同じ意味を一意に伝えられないか確認したか。
- Icon-only controlはvisible labelなしでも意味が明確で、accessible nameを持つか。
- Loadingは処理範囲と進捗に合うspinner、skeleton、progress bar、status indicatorで示し、重複するvisible copyを置いていないか。
- 各表示文が`task`、`state`、`action`、`safety`、`error`、`accessibility`、`legal`のいずれかに必要か。
- 先送りした詳細が任意情報であり、役立つ時点で発見できるか。
- 説明文が重複していた情報を、視覚階層で伝えられているか。
- 安全、回復、アクセシビリティ、localization、法令上の開示を維持したか。
- 情報の優先度が変わる状態とviewportをscreenshotまたはlive checkで確認したか。
