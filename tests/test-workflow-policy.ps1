#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent

$removedSkills = @(
    'session-handoff',
    'session-resume',
    'task-brief',
    'validation-report',
    'knowledge-placement',
    'consolidate-structure'
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

$removedReviewArtifacts = @(
    'skills/contract-closure/scripts/candidate_snapshot.py',
    'skills/contract-closure/scripts/review_brief.py',
    'skills/contract-closure/scripts/test_candidate_snapshot.py',
    'skills/contract-closure/scripts/test_review_brief.py'
)

foreach ($relativePath in $removedReviewArtifacts) {
    if (Test-Path -LiteralPath (Join-Path $repoRoot $relativePath)) {
        throw "Removed review artifact still exists: $relativePath"
    }
}

$activePolicyPaths = @(
    'AGENTS.md',
    'README.md',
    '.github/workflows/ci.yml',
    'docs/architecture/instruction-governance.md',
    'docs/architecture/subagent-workspace.md',
    'skills/commit-note/SKILL.md',
    'skills/contract-closure/SKILL.md',
    'agents/reviewer.toml',
    'agents/targeted_reviewer.toml',
    'agents/slice_reviewer.toml'
)

$removedActiveTerms = @(
    'candidate_snapshot.py',
    'review_brief.py',
    'Review Brief',
    'Candidate snapshot',
    '`consolidate-structure`'
)

foreach ($relativePath in $activePolicyPaths) {
    $text = Get-Content -LiteralPath (Join-Path $repoRoot $relativePath) -Raw
    foreach ($term in $removedActiveTerms) {
        if ($text -match [regex]::Escape($term)) {
            throw "$relativePath still references removed active review policy: $term"
        }
    }
}

$reviewFallbackProbe = '.agent-worktrees/reviews/review-probe'
git -C $repoRoot check-ignore --quiet --no-index $reviewFallbackProbe
if ($LASTEXITCODE -ne 0) {
    throw "Review worktree fallback is not ignored: $reviewFallbackProbe"
}

Write-Host 'OK: retired review resources remain absent and the repository fallback is ignored'
