[CmdletBinding()]
param(
    [string]$Ref = "main",
    [switch]$Check
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$upstreamUrl = "https://github.com/coji/natural-japanese.git"
$upstreamSkillPath = "skills/natural-japanese"
$expectedLicenseBlobOid = "56950aa7c7db5662b10027ba4deb34787ee24b0e"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$skillsRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "skills"))
$destination = [IO.Path]::GetFullPath((Join-Path $skillsRoot "natural-japanese"))
$lockPath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot ".natural-japanese.sync.lock"))
$operationId = [Guid]::NewGuid().ToString("N")
$checkoutRoot = [IO.Path]::GetFullPath((Join-Path $skillsRoot ".natural-japanese.checkout-$operationId"))
$staging = [IO.Path]::GetFullPath((Join-Path $skillsRoot ".natural-japanese.staging-$operationId"))
$backup = [IO.Path]::GetFullPath((Join-Path $skillsRoot ".natural-japanese.backup-$operationId"))

function Assert-ChildPath {
    param(
        [Parameter(Mandatory)] [string]$Parent,
        [Parameter(Mandatory)] [string]$Child
    )

    $parentPrefix = $Parent.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $Child.StartsWith($parentPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing filesystem operation outside $Parent`: $Child"
    }
}

function Invoke-Git {
    param(
        [Parameter(Mandatory)] [string[]]$Arguments,
        [switch]$AllowFailure
    )

    & git @Arguments
    $exitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $exitCode"
    }
    return $exitCode
}

function Get-SkillManifest {
    param([Parameter(Mandatory)] [string]$Root)

    $manifest = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
    $strictUtf8 = [Text.UTF8Encoding]::new($false, $true)
    $normalizedUtf8 = [Text.UTF8Encoding]::new($false)

    foreach ($file in Get-ChildItem -LiteralPath $Root -Recurse -File -Force) {
        $relativePath = [IO.Path]::GetRelativePath($Root, $file.FullName).Replace("\", "/")
        if ($relativePath -match "(^|/)__pycache__/" -or $file.Extension -in @(".pyc", ".pyo")) {
            continue
        }

        $bytes = [IO.File]::ReadAllBytes($file.FullName)
        try {
            $text = $strictUtf8.GetString($bytes).Replace("`r`n", "`n")
            $bytes = $normalizedUtf8.GetBytes($text)
        }
        catch [Text.DecoderFallbackException] {
            # Keep non-UTF-8 assets as bytes so binary changes remain observable.
        }

        $manifest[$relativePath] = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))
    }

    return $manifest
}

function Compare-SkillManifests {
    param(
        [Parameter(Mandatory)] $Actual,
        [Parameter(Mandatory)] $Expected
    )

    $allPaths = @($Actual.Keys) + @($Expected.Keys) | Sort-Object -Unique
    foreach ($path in $allPaths) {
        if (-not $Actual.ContainsKey($path)) {
            "A`t$path"
        }
        elseif (-not $Expected.ContainsKey($path)) {
            "D`t$path"
        }
        elseif ($Actual[$path] -ne $Expected[$path]) {
            "M`t$path"
        }
    }
}

Assert-ChildPath -Parent $skillsRoot -Child $destination
Assert-ChildPath -Parent $skillsRoot -Child $checkoutRoot
Assert-ChildPath -Parent $skillsRoot -Child $staging
Assert-ChildPath -Parent $skillsRoot -Child $backup
$repositoryPrefix = $repositoryRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $lockPath.StartsWith($repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use a sync lock outside $repositoryRoot`: $lockPath"
}

$syncLock = $null
try {
    if (-not $Check) {
        try {
            $syncLock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        }
        catch [IO.IOException] {
            throw "Another natural-japanese synchronization is already running."
        }
    }

    New-Item -ItemType Directory -Path $checkoutRoot | Out-Null
    Invoke-Git -Arguments @("-C", $checkoutRoot, "init", "--quiet") | Out-Null
    Invoke-Git -Arguments @("-C", $checkoutRoot, "fetch", "--quiet", "--depth", "1", $upstreamUrl, $Ref) | Out-Null
    Invoke-Git -Arguments @("-C", $checkoutRoot, "checkout", "--quiet", "--detach", "FETCH_HEAD") | Out-Null

    $revision = (& git -C $checkoutRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $revision -notmatch "^[0-9a-f]{40}$") {
        throw "Could not resolve the fetched upstream revision."
    }

    $source = [IO.Path]::GetFullPath((Join-Path $checkoutRoot $upstreamSkillPath))
    Assert-ChildPath -Parent $checkoutRoot -Child $source
    if (-not (Test-Path -LiteralPath (Join-Path $source "SKILL.md") -PathType Leaf)) {
        throw "Upstream skill not found at $upstreamSkillPath for ref $Ref."
    }

    $upstreamLicensePath = Join-Path $checkoutRoot "LICENSE"
    if (-not (Test-Path -LiteralPath $upstreamLicensePath -PathType Leaf)) {
        throw "The upstream LICENSE file is missing. Review the upstream change before synchronizing."
    }
    $actualLicenseBlobOid = (& git -C $checkoutRoot rev-parse "HEAD:LICENSE").Trim()
    if ($LASTEXITCODE -ne 0 -or $actualLicenseBlobOid -ne $expectedLicenseBlobOid) {
        throw "The upstream LICENSE no longer matches the reviewed MIT license. Review the upstream change before synchronizing."
    }

    Copy-Item -LiteralPath $source -Destination $staging -Recurse
    Copy-Item -LiteralPath $upstreamLicensePath -Destination (Join-Path $staging "LICENSE")

    $skillDefinitionPath = Join-Path $staging "SKILL.md"
    $skillDefinition = Get-Content -LiteralPath $skillDefinitionPath -Raw
    $argumentHintPattern = "(?m)^argument-hint:.*\r?\n"
    $frontmatter = [regex]::Match($skillDefinition, "\A---\r?\n.*?\r?\n---\r?\n", [Text.RegularExpressions.RegexOptions]::Singleline)
    $argumentHintMatches = [regex]::Matches($skillDefinition, $argumentHintPattern)
    if (-not $frontmatter.Success -or $argumentHintMatches.Count -ne 1 -or $argumentHintMatches[0].Index -ge $frontmatter.Length) {
        throw "Expected exactly one argument-hint entry inside upstream SKILL.md frontmatter. Review the upstream change before synchronizing."
    }
    $upstreamRouting = "技術文書の章構成やMarkdownフォーマットの整形自体（一文一行化・引用ブロック・脚注記法など）は対象外——それは別スキルの領域であり、本スキルは文章の自然さ・読みやすさ・わかりやすさに特化する。"
    $routingMatches = [regex]::Matches($skillDefinition, [regex]::Escape($upstreamRouting))
    if ($routingMatches.Count -ne 1) {
        throw "Expected exactly one upstream technical-writing routing statement. Review the upstream change before synchronizing."
    }

    $skillDefinition = @'
---
name: natural-japanese
description: 一般的な業務文書、議事録、メール、ブログ、エッセイを自然で読みやすい日本語で作成・リライトし、文章のAIっぽさや自然さを診断・採点するときに使用する。通常の短いチャット回答、進捗・完了報告、単純なコマンド結果には使用しない。技術文書の論証・構成・Markdown表記は japanese-tech-writing-review を使用する。
license: MIT
---

# natural-japanese

一般・業務文書を自然で読みやすい日本語に整える。短いチャット回答や作業報告は通常の会話・報告規則で書き、このSkillを起動しない。

技術文書でも、文章の自然さだけを直す依頼にはこのSkillを使う。論証、章構成、Markdown表記を扱う場合は `japanese-tech-writing-review` を使う。両方が必要なら担当を分け、同じ観点を二重にレビューしない。

## workflowを選ぶ

依頼を次のどちらかへ分け、選んだ参照だけを読む。

- **write**: 新規作成、リライト、自然さ・読みやすさの改善、文体プロファイル作成。最初に [references/write.md](references/write.md) を読む。
- **score**: AIっぽさや自然さの診断・採点。最初に [references/diagnose.md](references/diagnose.md) を読み、文書は変更しない。診断後にリライトを提案してよいが、依頼されるまで実行しない。

`/natural-japanese [quick|full] <対象>` はwriteまたはリライト、`/natural-japanese write [quick|full] <対象>` は新規作成、`/natural-japanese score [quick|full|exp] <ファイル>` は診断として扱う。自然言語の依頼も同じ基準で分ける。

## writeのmodeを選ぶ

**quickを既定**にする。対象文書の種類に対応するdoctypeがあれば一つだけ読み、lint、スケルトン通読、最終通読まで行う。対象文書では、短くてもlintを省略しない。

**full**は、次のいずれかに該当するときに選ぶ。

- ユーザーが `full` または同等の品質工程を明示する。
- 対外公開、経営判断、規制・契約上の利用など、誤りの具体的な失敗コストが高い。
- 構造、読みやすさ、doctype適合など、複数の独立した品質観点による検証が成果物に必要である。

「ちゃんと」「しっかり」「結論から」などの強調語や文字数だけを根拠にfullを選ばない。長さは、独立した検証観点が必要かを判断する材料の一つとして扱う。

fullではlintに加え、構造の機械的確認と必要に応じた用語確認、成果物に必要な独立review、判断台帳、収束確認を行う。reviewer数を固定せず、発見すべき欠陥と独立性が必要な観点から決める。明示されたfullや特定の品質工程は、実行途中の都合で省略しない。

## 完了条件

- writeは、選択したmodeの検査を行い、findingを「直す」「根拠をもって残す」に仕分け、修正による新しいfindingがなく、最終通読を終えている。
- scoreは、`references/diagnose.md` の算式と出力契約に従い、元文書を変更していない。
- 作業中のlint出力、判断台帳、下書きなどを成果物と同じ場所へ残さない。ユーザーが明示した成果物だけを残す。
'@
    $skillDefinition = $skillDefinition.Replace("`r`n", "`n").Replace("`n", [Environment]::NewLine)
    Set-Content -LiteralPath $skillDefinitionPath -Value $skillDefinition -Encoding utf8NoBOM

    $writeWorkflow = @'
# Write workflow

一般・業務文書の新規作成、リライト、自然さ・読みやすさの改善に使う。ユーザーが指定した文体やCharacterを優先し、事実、引用、数値、固有名詞、JSONやschema、CLI token、test metadata、API名など機械が読む文字列を文体調整で変えない。

## 設計する

1. 読者、目的、読み終えた後に起きてほしいことを特定する。不明点が結果を変える場合だけ確認する。
2. 文書タイプが定まったら、対応する型を一つ読む。
   - 議事録: [doctypes/minutes.md](doctypes/minutes.md)
   - 調査・分析レポート: [doctypes/report.md](doctypes/report.md)
   - 社内ガイド・マニュアル: [doctypes/guide.md](doctypes/guide.md)
   - リサーチメモ・企画書・ディスカッションペーパー: [doctypes/memo.md](doctypes/memo.md)
   - スライド構成: [doctypes/slide.md](doctypes/slide.md)
3. 主メッセージを一文にし、見出しだけで論旨が追えるスケルトンを作る。主メッセージを決められない場合は、[revision-guide.md](revision-guide.md) の「素材集め」に戻る。
4. 重要な節を厚く、軽い節を短くする。全節を同じ構成や分量に揃えない。

既存の `style-profile.md` があれば読む。ユーザーが文体の学習を求めた場合だけ、[../assets/style-profile-template.md](../assets/style-profile-template.md) を使って過去文章から傾向を抽出する。個別の指摘を一般的な禁止語へ拡張しない。

## 執筆する

[writing-constitution.md](writing-constitution.md) を読み、結論と主メッセージを先に置く。説明は地の文を基本とし、並列項目、手順、比較にだけリストや表を使う。固有名詞、数値、実例で主張を接地し、事実、推定、意見、限界を区別する。

リライトでは、元の事実と意図を保つ。同じ修正を全項目へ一律に当てず、読者に価値を足す箇所だけを直す。

## quickで検査する

quickでもlintを省略しない。Skill rootを基準に次を実行する。

```text
uv run <skill-root>/scripts/lint.py --json <file>
```

文書のジャンルが明確なら `--genre essay|tech|business` を指定する。lintを実行できない環境では [manual-checklist.md](manual-checklist.md) を使い、未実行理由を明示する。

lintのfindingを文脈に照らして「直す」「残す」に仕分ける。見出しと各段落の先頭文を自分で読み、論旨、見出し、反復、濃淡、結びを確認する。findingがなければ一周で終えてよい。

## fullで検査する

fullではquickの工程に加え、次の機械的確認と独立reviewを行う。

```text
uv run <skill-root>/scripts/outline.py <file>
uv run <skill-root>/scripts/terms.py <file>
uv run <skill-root>/scripts/lint.py --reading-load <file>
```

`terms.py` は専門用語の確認が必要な文書で使う。review観点は成果物に生じ得る欠陥から選ぶ。

- 構造: 論旨、見出し、反復、濃淡、結びを確認する。
- 読みやすさ: 語順、係り受け、主述の距離、否定、列挙、専門語の負荷を確認する。
- doctype適合: 選んだ型の必須要素と用途への適合を確認する。

すべての文書に三つのreviewerを固定しない。複数の独立した観点が必要なら、その独立性を保てる担当へ分ける。一人の独立reviewerが関連する複数観点をまとめてもよい。執筆者は所見を判断台帳へ統合し、直すか残すかを決める。明示されたreview観点は省略しない。

読みやすさの判断が必要なら [readability-principles.md](readability-principles.md) と [readability-antipatterns.md](readability-antipatterns.md) を読む。lint findingの判断に迷ったカテゴリだけ [revision-guide.md](revision-guide.md)、[forbidden-patterns.md](forbidden-patterns.md)、[translationese.md](translationese.md)、[genre-notes.md](genre-notes.md) を読む。全referenceを一括で読み込まない。

`scripts/semantic.py` は重量級の実験的なopt-in検出器であり、fullの必須工程ではない。ユーザーが深層検出を求め、初回の大きなdownloadを許可し、環境が対応するときだけ使う。

## 収束して片付ける

修正後はlintを再実行し、直前のJSONを `--baseline` に渡してresolved / new / persistingを確認する。すべてのfindingを仕分け、修正による新しいfindingがなくなるまで繰り返す。同じfindingが再発する場合は [revision-guide.md](revision-guide.md) の「発散ガード」を使う。

最後に初見の読者として通読し、主メッセージ、事実保持、読みやすさ、リズムを確認する。作業中の判断台帳、lint JSON、下書きのbackupは削除し、ユーザーが求めた完成物だけを残す。
'@
    $writeWorkflow = $writeWorkflow.Replace("`r`n", "`n").Replace("`n", [Environment]::NewLine)
    Set-Content -LiteralPath (Join-Path $staging "references/write.md") -Value $writeWorkflow -Encoding utf8NoBOM

    $diagnosePath = Join-Path $staging "references/diagnose.md"
    $diagnoseDefinition = Get-Content -LiteralPath $diagnosePath -Raw
    $diagnoseReplacements = @(
        [pscustomobject]@{
            From = '診断モードは文書を一切書き換えない。返すのは3点だけ。スコアと、その根拠と、直すなら何からか。「この文章、AIっぽい？」「どれくらいAI臭いか採点して」という依頼に答えるためのモードで、リライトを求められたら通常の工程（SKILL.md §1〜7）へ切り替える。'
            To = '診断モードは文書を一切書き換えない。返すのは3点だけ。スコアと、その根拠と、直すなら何からか。「この文章、AIっぽい？」「どれくらいAI臭いか採点して」という依頼に答えるためのモードで、リライトを求められたら [write.md](write.md) の工程へ切り替える。'
        },
        [pscustomobject]@{
            From = '診断の quick / full は、実行モード（SKILL.md「実行モード」）と同じ思想の深さ指定である。書き換え工程がないぶん中身は次のように読み替える。矛盾したら実行モード側でなくこの節に従う。'
            To = '診断の quick / full は、[SKILL.md](../SKILL.md) のwrite modeと同じ品質の深さを表す。書き換え工程がないぶん中身は次のように読み替える。矛盾したらwrite側でなくこの節に従う。'
        },
        [pscustomobject]@{
            From = '- **full**: quick に加えて `outline.py` / `terms.py` を実行し、構造レビュー・読みやすさレビュー・doctype照合（SKILL.md §4 と同じ三観点）を判断に織り込む。実行モードのフルと同様に並列サブエージェントへ委譲してよいが、診断では収束ループは回さない（1周の評価で完結する）。数分'
            To = '- **full**: quick に加えて `outline.py` と、用語評価が必要な文書では `terms.py` を実行する。構造・読みやすさと、文書タイプが定まる場合はdoctype適合を判断に織り込む。独立reviewが必要なら、reviewer数は必要な観点と独立性から決め、三人に固定しない。診断では収束ループを回さず、1周の評価で完結する。数分'
        }
    )
    foreach ($replacement in $diagnoseReplacements) {
        $matches = [regex]::Matches($diagnoseDefinition, [regex]::Escape($replacement.From))
        if ($matches.Count -ne 1) {
            throw "Expected exactly one upstream diagnosis workflow statement. Review the upstream change before synchronizing."
        }
        $diagnoseDefinition = $diagnoseDefinition.Replace($replacement.From, $replacement.To)
    }
    $diagnoseDefinition = $diagnoseDefinition.Replace("`r`n", "`n").Replace("`n", [Environment]::NewLine)
    Set-Content -LiteralPath $diagnosePath -Value $diagnoseDefinition -Encoding utf8NoBOM -NoNewline

    $referenceAdaptations = @(
        [pscustomobject]@{
            Path = "references/revision-guide.md"
            From = '打ち手は単純で、SKILL.md の§4のとおり、その周でヒットしたカテゴリに対応する節をそのつど読み直す。内面化は一度の理解では終わらない。同じ場所に何度も戻ることで少しずつ進む。参考記事（[note.com/art_reflection](https://note.com/art_reflection/n/ncdb00d92bbde)）も同じ点を指摘している。基準を読んだと申告しながら出力で基準を破る現象は、要約記憶だけで作業しているときによく起きる。'
            To = '打ち手は単純で、[write.md](write.md) の検査工程のとおり、その周でヒットしたカテゴリに対応する節をそのつど読み直す。内面化は一度の理解では終わらない。同じ場所に何度も戻ることで少しずつ進む。参考記事（[note.com/art_reflection](https://note.com/art_reflection/n/ncdb00d92bbde)）も同じ点を指摘している。基準を読んだと申告しながら出力で基準を破る現象は、要約記憶だけで作業しているときによく起きる。'
        },
        [pscustomobject]@{
            Path = "references/revision-guide.md"
            From = 'lint と並行して毎周回行う「読みやすさレビュー」（SKILL.md §4）は、何を見るかが周回ごとに変わる。全観点を一度に見ようとすると総花的になり、結局どれも深く見ないまま流れてしまう。'
            To = 'lint と並行して毎周回行う読みやすさレビュー（[write.md](write.md) の「fullで検査する」）は、何を見るかが周回ごとに変わる。全観点を一度に見ようとすると総花的になり、結局どれも深く見ないまま流れてしまう。'
        },
        [pscustomobject]@{
            Path = "references/manual-checklist.md"
            From = '`scripts/outline.py` が使えない環境では、見出しと各段落の先頭文を手で拾って並べる「スケルトン通読」（SKILL.md §4「構造レビュー」参照）も同様に手動で代替する。'
            To = '`scripts/outline.py` が使えない環境では、見出しと各段落の先頭文を手で拾って並べる「スケルトン通読」（[write.md](write.md) の「fullで検査する」参照）も同様に手動で代替する。'
        },
        [pscustomobject]@{
            Path = "references/doctypes/slide.md"
            From = 'スケルトン通読(→ `SKILL.md` の構造レビュー節)がスライドにもっとも強く効く検査法になる。メッセージラインだけを最初から最後まで順に読み、(1)論旨が通るか (2)各ラインが本当に結論を言っているか (3)同じ文型が続いていないか (4)重要なスライドとそうでないスライドの扱いに差があるか (5)最後のスライドが次のアクションに接続しているか、の5点を確認する。この通読で筋が通らなければ、根拠の中身をどれだけ整えてもストーリーは伝わらない。'
            To = 'スケルトン通読（[../write.md](../write.md) の「fullで検査する」参照）がスライドにもっとも強く効く検査法になる。メッセージラインだけを最初から最後まで順に読み、(1)論旨が通るか (2)各ラインが本当に結論を言っているか (3)同じ文型が続いていないか (4)重要なスライドとそうでないスライドの扱いに差があるか (5)最後のスライドが次のアクションに接続しているか、の5点を確認する。この通読で筋が通らなければ、根拠の中身をどれだけ整えてもストーリーは伝わらない。'
        },
        [pscustomobject]@{
            Path = "references/readability-antipatterns.md"
            From = 'だからこのカタログは**検出器の代用ではなく、目視レビューの着眼点**として使う。lint が沈黙していても、ここに並ぶ問題は普通に残る。`SKILL.md` の収束ループでは毎周回これを当てる。'
            To = 'だからこのカタログは**検出器の代用ではなく、目視レビューの着眼点**として使う。lint が沈黙していても、ここに並ぶ問題は普通に残る。[write.md](write.md) の収束ループでは毎周回これを当てる。'
        },
        [pscustomobject]@{
            Path = "scripts/outline.py"
            From = '# SKILL.md §4 の構造レビュー（スケルトン通読）への入力として使う。'
            To = '# references/write.md のfull構造レビュー（スケルトン通読）への入力として使う。'
        },
        [pscustomobject]@{
            Path = "scripts/outline.py"
            From = '行う。SKILL.md §4 の構造レビュー（スケルトン通読）への入力として使う。'
            To = '行う。references/write.md のfull構造レビュー（スケルトン通読）への入力として使う。'
        }
    )
    foreach ($adaptation in $referenceAdaptations) {
        $adaptationPath = Join-Path $staging $adaptation.Path
        $adaptationContent = Get-Content -LiteralPath $adaptationPath -Raw
        $matches = [regex]::Matches($adaptationContent, [regex]::Escape($adaptation.From))
        if ($matches.Count -ne 1) {
            throw "Expected exactly one upstream reference to the original SKILL.md workflow in $($adaptation.Path). Review the upstream change before synchronizing."
        }
        $adaptationContent = $adaptationContent.Replace($adaptation.From, $adaptation.To)
        $adaptationContent = $adaptationContent.Replace("`r`n", "`n").Replace("`n", [Environment]::NewLine)
        Set-Content -LiteralPath $adaptationPath -Value $adaptationContent -Encoding utf8NoBOM -NoNewline
    }

    $notice = @"
natural-japanese

Source: https://github.com/coji/natural-japanese
Upstream path: $upstreamSkillPath
Revision: $revision
License: MIT (see LICENSE)

This directory is synchronized by scripts/sync-natural-japanese.ps1.
Codex adaptations: removes the unsupported argument-hint frontmatter entry,
routes technical-document structure and Markdown formatting to japanese-tech-writing-review,
and provides a concise write/score router with local write and score workflow adjustments.
Local edits under this directory are replaced during synchronization.
"@
    $notice = $notice.Replace("`r`n", "`n").Replace("`n", [Environment]::NewLine)
    Set-Content -LiteralPath (Join-Path $staging "NOTICE") -Value $notice -Encoding utf8NoBOM

    if ($Check) {
        $actualManifest = Get-SkillManifest -Root $destination
        $expectedManifest = Get-SkillManifest -Root $staging
        $differences = @(Compare-SkillManifests -Actual $actualManifest -Expected $expectedManifest)

        if (-not $differences) {
            Write-Output "natural-japanese is synchronized with $revision."
            exit 0
        }

        $differences | Write-Output
        Write-Error "natural-japanese differs from $upstreamUrl at $revision. Run this script without -Check to synchronize it."
        exit 1
    }

    $preMoveManifest = Get-SkillManifest -Root $destination
    $targetStatus = & git -C $repositoryRoot status --porcelain=v1 --untracked-files=all -- $destination
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect local changes under $destination."
    }
    if ($targetStatus) {
        throw "Refusing to replace natural-japanese because it has uncommitted changes:`n$($targetStatus -join [Environment]::NewLine)"
    }

    if (Test-Path -LiteralPath $destination) {
        Move-Item -LiteralPath $destination -Destination $backup
    }

    try {
        Move-Item -LiteralPath $staging -Destination $destination
    }
    catch {
        if ((Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $destination)) {
            Move-Item -LiteralPath $backup -Destination $destination
        }
        throw
    }

    if (Test-Path -LiteralPath $backup) {
        $backupManifest = Get-SkillManifest -Root $backup
        $concurrentChanges = @(Compare-SkillManifests -Actual $backupManifest -Expected $preMoveManifest)
        if ($concurrentChanges) {
            try {
                Move-Item -LiteralPath $destination -Destination $staging
                Move-Item -LiteralPath $backup -Destination $destination
            }
            catch {
                throw "The previous skill changed during synchronization and could not be restored automatically. Preserved paths: $destination and $backup"
            }
            throw "The previous skill changed during synchronization. The new copy was discarded and the previous skill was restored."
        }
        Remove-Item -LiteralPath $backup -Recurse -Force
    }

    $trackedSkillPaths = @(& git -C $repositoryRoot ls-files -- $destination)
    if ($LASTEXITCODE -eq 0 -and $trackedSkillPaths) {
        & git -C $repositoryRoot update-index --refresh -- $trackedSkillPaths *> $null
    }

    Write-Output "Synchronized natural-japanese from $upstreamUrl at $revision."
}
finally {
    if ($null -ne $syncLock) {
        $syncLock.Dispose()
    }
    foreach ($temporaryPath in @($checkoutRoot, $staging)) {
        Assert-ChildPath -Parent $skillsRoot -Child $temporaryPath
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Recurse -Force
        }
    }
}
