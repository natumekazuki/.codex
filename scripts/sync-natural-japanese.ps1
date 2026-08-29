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
    $skillDefinition = $skillDefinition -replace $argumentHintPattern, ""

    $upstreamRouting = "技術文書の章構成やMarkdownフォーマットの整形自体（一文一行化・引用ブロック・脚注記法など）は対象外——それは別スキルの領域であり、本スキルは文章の自然さ・読みやすさ・わかりやすさに特化する。"
    $codexRouting = "技術文書の章構成やMarkdownフォーマットの整形自体（一文一行化・引用ブロック・脚注記法など）は対象外であり、japanese-tech-writing-review を使用する。本スキルは文章の自然さ・読みやすさ・わかりやすさに特化する。"
    $routingMatches = [regex]::Matches($skillDefinition, [regex]::Escape($upstreamRouting))
    if ($routingMatches.Count -ne 1) {
        throw "Expected exactly one upstream technical-writing routing statement. Review the upstream change before synchronizing."
    }
    $skillDefinition = $skillDefinition.Replace($upstreamRouting, $codexRouting)
    $skillDefinition = $skillDefinition.Replace("`r`n", "`n").Replace("`n", [Environment]::NewLine)
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
