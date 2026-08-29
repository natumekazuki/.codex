[CmdletBinding()]
param(
    [string]$Ref = "main",
    [switch]$Check
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$upstreamUrl = "https://github.com/coji/natural-japanese.git"
$upstreamSkillPath = "skills/natural-japanese"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$skillsRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "skills"))
$destination = [IO.Path]::GetFullPath((Join-Path $skillsRoot "natural-japanese"))
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

Assert-ChildPath -Parent $skillsRoot -Child $destination
Assert-ChildPath -Parent $skillsRoot -Child $checkoutRoot
Assert-ChildPath -Parent $skillsRoot -Child $staging
Assert-ChildPath -Parent $skillsRoot -Child $backup

try {
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

    Copy-Item -LiteralPath $source -Destination $staging -Recurse
    Copy-Item -LiteralPath (Join-Path $checkoutRoot "LICENSE") -Destination (Join-Path $staging "LICENSE")

    $skillDefinitionPath = Join-Path $staging "SKILL.md"
    $skillDefinition = Get-Content -LiteralPath $skillDefinitionPath -Raw
    $argumentHintPattern = "(?m)^argument-hint:.*\r?\n"
    if ($skillDefinition -notmatch $argumentHintPattern) {
        throw "The expected upstream argument-hint frontmatter entry was not found. Review the upstream change before synchronizing."
    }
    $skillDefinition = $skillDefinition -replace $argumentHintPattern, ""

    $upstreamRouting = "技術文書の章構成やMarkdownフォーマットの整形自体（一文一行化・引用ブロック・脚注記法など）は対象外——それは別スキルの領域であり、本スキルは文章の自然さ・読みやすさ・わかりやすさに特化する。"
    $codexRouting = "技術文書の章構成やMarkdownフォーマットの整形自体（一文一行化・引用ブロック・脚注記法など）は対象外であり、japanese-tech-writing-review を使用する。本スキルは文章の自然さ・読みやすさ・わかりやすさに特化する。"
    if (-not $skillDefinition.Contains($upstreamRouting)) {
        throw "The expected upstream technical-writing routing text was not found. Review the upstream change before synchronizing."
    }
    $skillDefinition = $skillDefinition.Replace($upstreamRouting, $codexRouting)
    Set-Content -LiteralPath $skillDefinitionPath -Value $skillDefinition -Encoding utf8NoBOM -NoNewline

    $notice = @"
natural-japanese

Source: https://github.com/coji/natural-japanese
Upstream path: $upstreamSkillPath
Revision: $revision
License: MIT (see LICENSE)

This directory is synchronized by scripts/sync-natural-japanese.ps1.
Codex adaptations: removes the unsupported argument-hint frontmatter entry and
routes technical-document structure and Markdown formatting to japanese-tech-writing-review.
Local edits under this directory are replaced during synchronization.
"@
    Set-Content -LiteralPath (Join-Path $staging "NOTICE") -Value $notice -Encoding utf8NoBOM

    if ($Check) {
        & git -c core.autocrlf=false diff --no-index --quiet --ignore-space-at-eol -- $destination $staging
        $diffExitCode = $LASTEXITCODE
        if ($diffExitCode -eq 0) {
            Write-Output "natural-japanese is synchronized with $revision."
            exit 0
        }
        if ($diffExitCode -eq 1) {
            & git -c core.autocrlf=false diff --no-index --name-status --ignore-space-at-eol -- $destination $staging
            Write-Error "natural-japanese differs from $upstreamUrl at $revision. Run this script without -Check to synchronize it."
            exit 1
        }
        throw "git diff --no-index failed with exit code $diffExitCode"
    }

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
        Remove-Item -LiteralPath $backup -Recurse -Force
    }

    Write-Output "Synchronized natural-japanese from $upstreamUrl at $revision."
}
finally {
    foreach ($temporaryPath in @($checkoutRoot, $staging)) {
        Assert-ChildPath -Parent $skillsRoot -Child $temporaryPath
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Recurse -Force
        }
    }
}
