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

$agentsText = Get-Content -LiteralPath (Join-Path $repoRoot 'AGENTS.md') -Raw
$agentsContracts = @(
    @{ Label = 'Git commit review source'; Pattern = 'Git管理されたrepositoryのcommit済みsource' },
    @{ Label = 'immutable base OID'; Pattern = 'baseCommitOid' },
    @{ Label = 'immutable review OID'; Pattern = 'reviewCommitOid' },
    @{ Label = 'explicit detached review target'; Pattern = 'detached worktree.+reviewTarget' },
    @{ Label = 'commit-bound check evidence'; Pattern = 'executedOnCommitOid' },
    @{ Label = 'non-Git review gap'; Pattern = 'Git未管理または未commit.+validation gap' },
    @{ Label = 'repair commit closure'; Pattern = 'A\.\.B.+targeted closure' },
    @{ Label = 'single holistic review'; Pattern = '一つの論理変更につきcomplete-diff holistic reviewを一度だけ' },
    @{ Label = 'ordinary feature-branch commit authority'; Pattern = 'task / feature branchへの通常の追加commit' },
    @{ Label = 'protected branch boundary'; Pattern = 'default / main / protected branchへのcommit' },
    @{ Label = 'history rewrite boundary'; Pattern = 'amend / rebase / reset' },
    @{ Label = 'push boundary'; Pattern = 'push.+明示' },
    @{ Label = 'pre-commit status and diff'; Pattern = 'commit前にstatusと対象diff' },
    @{ Label = 'existing staged change protection'; Pattern = '既存のstaged変更' },
    @{ Label = 'semantic owner consolidation'; Pattern = 'semantic ownerの分散' },
    @{ Label = 'responsibility consolidation'; Pattern = '独立責務の混在' },
    @{ Label = 'dependency direction consolidation'; Pattern = 'canonical boundaryの迂回' }
)

foreach ($contract in $agentsContracts) {
    if ($agentsText -notmatch $contract.Pattern) {
        throw "AGENTS.md is missing workflow contract: $($contract.Label)"
    }
}

$contractSkillText = Get-Content -LiteralPath (Join-Path $repoRoot 'skills/contract-closure/SKILL.md') -Raw
foreach ($required in @(
    'Accepted contract / exact anchor',
    'Closure Map',
    'Sibling Sweep',
    'failure timing',
    'Finding Promotion',
    'baseCommitOid',
    'reviewCommitOid',
    'executedOnCommitOid',
    'python -X utf8 <skill-creator>/scripts/quick_validate.py skills/contract-closure'
)) {
    if ($contractSkillText -notmatch [regex]::Escape($required)) {
        throw "contract-closure is missing core responsibility: $required"
    }
}

$commitNoteText = Get-Content -LiteralPath (Join-Path $repoRoot 'skills/commit-note/SKILL.md') -Raw
foreach ($required in @(
    'task / feature branchへ通常の追加commit',
    'default / main / protected branchへのcommit',
    '対象pathまたはhunkだけをstage',
    '既存のstaged変更',
    'git push'
)) {
    if ($commitNoteText -notmatch [regex]::Escape($required)) {
        throw "commit-note is missing commit authority or staging contract: $required"
    }
}

if ($contractSkillText -match '`targeted_reviewer`へ') {
    throw 'contract-closure duplicates concrete role routing owned by AGENTS.md'
}

foreach ($role in @('slice_reviewer', 'targeted_reviewer', 'reviewer')) {
    $roleText = Get-Content -LiteralPath (Join-Path $repoRoot "agents/$role.toml") -Raw
    $roleContracts = @(
        @{ Label = 'read-only sandbox'; Pattern = 'sandbox_mode\s*=\s*"read-only"' },
        @{ Label = 'explicit target'; Pattern = 'reviewTarget' },
        @{ Label = 'base commit'; Pattern = 'baseCommitOid' },
        @{ Label = 'review commit'; Pattern = 'reviewCommitOid' },
        @{ Label = 'commit-bound checks'; Pattern = 'executedOnCommitOid' },
        @{ Label = 'HEAD identity'; Pattern = 'HEAD.+reviewCommitOid' },
        @{ Label = 'tracked and untracked cleanliness'; Pattern = 'tracked.+untracked.+clean' },
        @{ Label = 'commit object verification'; Pattern = 'OID.+commit object' },
        @{ Label = 'base ancestry'; Pattern = 'baseCommitOid.+ancestor.+reviewCommitOid' },
        @{ Label = 'fail-closed preflight'; Pattern = 'validation gap.+substantive review' }
    )
    foreach ($contract in $roleContracts) {
        if ($roleText -notmatch $contract.Pattern) {
            throw "$role is missing commit-bound read-only preflight: $($contract.Label)"
        }
    }

    foreach ($forbidden in @('Candidate Definition', 'Candidate preflight', 'Evidence Ledger', 'raw diff digest')) {
        if ($roleText -match [regex]::Escape($forbidden)) {
            throw "$role duplicates removed review artifact contract: $forbidden"
        }
    }
}

$targetedReviewerText = Get-Content -LiteralPath (Join-Path $repoRoot 'agents/targeted_reviewer.toml') -Raw
foreach ($riskField in @('occurrence conditions and likelihood', 'impact', 'detectability', 'recoverability', 'follow-up need')) {
    if ($targetedReviewerText -notmatch [regex]::Escape($riskField)) {
        throw "targeted_reviewer output is missing accepted-risk evidence: $riskField"
    }
}
foreach ($closureContract in @(
    @{ Label = 'repair checks bound to B'; Pattern = 'B-bound direct checks' },
    @{ Label = 'repair delta range'; Pattern = 'A\.\.B' },
    @{ Label = 'finding-family delta scope'; Pattern = 'finding family.+resulting delta' },
    @{ Label = 'holistic evidence remains on A'; Pattern = 'holistic result.+A.+B' }
)) {
    if ($targetedReviewerText -notmatch $closureContract.Pattern) {
        throw "targeted_reviewer is missing repair-commit closure contract: $($closureContract.Label)"
    }
}

$ciText = Get-Content -LiteralPath (Join-Path $repoRoot '.github/workflows/ci.yml') -Raw
if ($ciText -notmatch [regex]::Escape('tests/test-workflow-policy.ps1')) {
    throw 'CI does not run the workflow policy executable contract'
}

$adrPath = Join-Path $repoRoot 'docs/adr/0019-commit-bound-review.md'
if (-not (Test-Path -LiteralPath $adrPath)) {
    throw 'Commit-bound review ADR is missing'
}
$adrText = Get-Content -LiteralPath $adrPath -Raw
foreach ($required in @('Status: accepted', 'Candidate snapshot', 'Git未管理または未commit', 'baseCommitOid', 'reviewCommitOid', 'executedOnCommitOid', 'Supersedes: ADR-0006, ADR-0008')) {
    if ($adrText -notmatch [regex]::Escape($required)) {
        throw "Commit-bound review ADR is missing decision context: $required"
    }
}

Write-Host 'OK: workflow policy uses commit-bound review, protects evidence identity, and enforces commit authority boundaries'
