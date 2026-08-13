#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent

$removedSkills = @(
    'session-handoff',
    'session-resume',
    'task-brief',
    'validation-report',
    'knowledge-placement'
)

foreach ($skill in $removedSkills) {
    $skillPath = Join-Path $repoRoot "skills/$skill"
    if (Test-Path -LiteralPath $skillPath) {
        $remainingFiles = @(Get-ChildItem -LiteralPath $skillPath -Recurse -File -ErrorAction SilentlyContinue)
        if ($remainingFiles.Count -gt 0) {
            throw "Removed skill still has files: $skill"
        }
    }
}

$activePolicyPaths = @(
    'AGENTS.md',
    'README.md',
    'docs/architecture/instruction-governance.md',
    'docs/architecture/subagent-workspace.md',
    'skills/contract-closure/SKILL.md'
)

foreach ($relativePath in $activePolicyPaths) {
    $text = Get-Content -LiteralPath (Join-Path $repoRoot $relativePath) -Raw
    foreach ($skill in $removedSkills) {
        if ($text -match [regex]::Escape("skills/$skill") -or
            $text -match [regex]::Escape("``$skill``")) {
            throw "$relativePath still references removed skill $skill"
        }
    }
}

foreach ($adr in Get-ChildItem -LiteralPath (Join-Path $repoRoot 'docs/adr') -Filter '*.md' -File) {
    $text = Get-Content -LiteralPath $adr.FullName -Raw
    foreach ($skill in $removedSkills) {
        if ($text -match [regex]::Escape("skills/$skill")) {
            throw "$($adr.Name) still has an active file pointer to removed skill $skill"
        }
    }
}

$agentsText = Get-Content -LiteralPath (Join-Path $repoRoot 'AGENTS.md') -Raw
$contractSkillText = Get-Content -LiteralPath (Join-Path $repoRoot 'skills/contract-closure/SKILL.md') -Raw
foreach ($required in @(
    'targeted checkがaccepted contractを直接検証できるsliceは独立reviewを起動しない',
    'high-riskまたはnon-localな独立reviewでexact source stateの固定が必要な場合だけ',
    '一つの論理変更につきcomplete-diff holistic reviewを一度だけ',
    '変更内容、実行した検証、未実行の検証、残リスク'
)) {
    if ($agentsText -notmatch [regex]::Escape($required)) {
        throw "AGENTS.md is missing standard workflow contract: $required"
    }
}
foreach ($required in @(
    'candidate_snapshot.py create --candidate-id <id> --target <repo> --base-ref <ref> --include . --mode manifest-digest --artifact-dir <artifact-dir> --output <candidate.json>',
    'candidate_snapshot.py verify --candidate <candidate.json>',
    'python -X utf8 <skill-creator>/scripts/quick_validate.py skills/contract-closure'
)) {
    if ($contractSkillText -notmatch [regex]::Escape($required)) {
        throw "contract-closure documents a command that does not match the supported CLI: $required"
    }
}
if ($contractSkillText -match '`targeted_reviewer`へ') {
    throw 'contract-closure duplicates concrete role routing owned by AGENTS.md'
}

foreach ($required in @(
    'Accepted contract / exact anchor',
    'Sibling Sweep',
    'failure timing',
    'Finding Promotion',
    'review cycle、session expiry、review contract freshnessを証明しない'
)) {
    if ($contractSkillText -notmatch [regex]::Escape($required)) {
        throw "contract-closure is missing core responsibility: $required"
    }
}

foreach ($role in @('slice_reviewer', 'targeted_reviewer', 'reviewer')) {
    $roleText = Get-Content -LiteralPath (Join-Path $repoRoot "agents/$role.toml") -Raw
    foreach ($duplicatedSchemaTerm in @(
        'candidateVerificationInput',
        'Candidate Definition',
        'Candidate preflight',
        'Evidence Ledger',
        'raw diff digest'
    )) {
        if ($roleText -match [regex]::Escape($duplicatedSchemaTerm)) {
            throw "$role duplicates review-cycle schema term: $duplicatedSchemaTerm"
        }
    }
}

$targetedReviewerText = Get-Content -LiteralPath (Join-Path $repoRoot 'agents/targeted_reviewer.toml') -Raw
foreach ($riskField in @('occurrence conditions and likelihood', 'impact', 'detectability', 'recoverability', 'follow-up need')) {
    if ($targetedReviewerText -notmatch [regex]::Escape($riskField)) {
        throw "targeted_reviewer output is missing accepted-risk evidence: $riskField"
    }
}

Write-Host 'OK: workflow policy is minimal, proportional, and free of removed Skill references'
