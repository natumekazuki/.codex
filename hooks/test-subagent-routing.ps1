#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot 'subagent-routing.ps1'

function Invoke-SubagentRoutingHookRaw {
    param(
        [AllowEmptyString()][string]$InputText,
        [string]$Mode = '',
        [string]$StatePath = ''
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'pwsh'
    $startInfo.ArgumentList.Add('-NoProfile')
    $startInfo.ArgumentList.Add('-ExecutionPolicy')
    $startInfo.ArgumentList.Add('Bypass')
    $startInfo.ArgumentList.Add('-File')
    $startInfo.ArgumentList.Add($scriptPath)
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    if (-not [string]::IsNullOrWhiteSpace($Mode)) {
        $startInfo.Environment['CODEX_SUBAGENT_SPARK_MODE'] = $Mode
    } else {
        $startInfo.Environment.Remove('CODEX_SUBAGENT_SPARK_MODE') | Out-Null
    }
    if (-not [string]::IsNullOrWhiteSpace($StatePath)) {
        $startInfo.Environment['CODEX_SUBAGENT_ROUTING_STATE_PATH'] = $StatePath
    } else {
        $startInfo.Environment.Remove('CODEX_SUBAGENT_ROUTING_STATE_PATH') | Out-Null
    }

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $process.StandardInput.Write($InputText)
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    if ($process.ExitCode -ne 0) {
        throw "Hook process exited with code $($process.ExitCode): $stderr"
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        throw "Hook wrote stderr: $stderr"
    }

    return $stdout | ConvertFrom-Json -ErrorAction Stop
}

function Invoke-SubagentRoutingHook {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Event,
        [string]$Mode = '',
        [string]$StatePath = ''
    )

    $json = $Event | ConvertTo-Json -Depth 5 -Compress
    return Invoke-SubagentRoutingHookRaw -InputText $json -Mode $Mode -StatePath $StatePath
}

function Assert-RoutingContextOnly {
    param([Parameter(Mandatory = $true)][string]$Context)

    $legacyContractFragments = @(
        'Role reminder',
        'Add or update tests',
        'Do not edit files',
        'public API',
        'persistence',
        'migration',
        'auth/permissions',
        'data loss',
        'payment/billing',
        'concurrency',
        'async orchestration'
    )
    foreach ($fragment in $legacyContractFragments) {
        if ($Context -match [regex]::Escape($fragment)) {
            throw "Hook context duplicated static role contract text: $fragment"
        }
    }
}

$agentNames = @(
    'researcher',
    'planner',
    'designer',
    'implementer',
    'focused_implementer',
    'validator',
    'reviewer',
    'targeted_reviewer',
    'slice_reviewer',
    'fast_researcher',
    'fast_planner',
    'fast_implementer',
    'fast_validator',
    'fast_reviewer'
)

function Assert-SameNames {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string[]]$Expected,
        [Parameter(Mandatory = $true)][string[]]$Actual
    )

    if (($Expected -join "`n") -ne ($Actual -join "`n")) {
        throw "$Label mismatch. Expected: $($Expected -join ', '); actual: $($Actual -join ', ')"
    }
}

$sparkRoles = @('fast_researcher', 'fast_planner', 'fast_implementer', 'fast_validator', 'fast_reviewer')
$modes = @('balanced', 'spark-first', 'standard-only')

foreach ($standardRole in @('focused_implementer', 'slice_reviewer', 'targeted_reviewer', 'reviewer')) {
    if ($sparkRoles -contains $standardRole) {
        throw "$standardRole must remain a standard role"
    }
}

$exampleConfigPath = Join-Path (Split-Path $PSScriptRoot -Parent) 'config/agents.example.toml'
$exampleConfigText = Get-Content -LiteralPath $exampleConfigPath -Raw
if ($exampleConfigText -notmatch '(?m)^max_concurrent_threads_per_session\s*=\s*5\s*$') {
    throw 'config/agents.example.toml did not use max_concurrent_threads_per_session'
}
if ($exampleConfigText -match '(?m)^max_threads\s*=') {
    throw 'config/agents.example.toml still uses the legacy max_threads alias'
}

$repoRoot = Split-Path $PSScriptRoot -Parent
foreach ($standardRole in @('focused_implementer', 'slice_reviewer', 'targeted_reviewer', 'reviewer')) {
    $escapedRole = [regex]::Escape($standardRole)
    if ($exampleConfigText -notmatch "(?ms)^\[agents\.$escapedRole\]\s*\r?\nconfig_file\s*=\s*`"agents/$escapedRole\.toml`"") {
        throw "config/agents.example.toml did not register $standardRole with its canonical role file"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "agents/$standardRole.toml") -PathType Leaf)) {
        throw "$standardRole role file is missing"
    }
}

$registeredRoles = @([regex]::Matches($exampleConfigText, '(?m)^\[agents\.([^\]]+)\]') | ForEach-Object { $_.Groups[1].Value } | Sort-Object)
$hooksConfig = Get-Content -LiteralPath (Join-Path $repoRoot 'hooks.json') -Raw | ConvertFrom-Json -ErrorAction Stop
$subagentStartMatcher = [string]$hooksConfig.hooks.SubagentStart[0].matcher
if ($subagentStartMatcher -notmatch '^\^\((?<roles>[^)]*)\)\$$') {
    throw 'hooks.json SubagentStart matcher does not use the expected explicit role alternation'
}
$matchedRoles = @($Matches.roles -split '\|' | Sort-Object)
Assert-SameNames -Label 'production SubagentStart matcher coverage' -Expected $registeredRoles -Actual $matchedRoles

$focusedText = Get-Content -LiteralPath (Join-Path $repoRoot 'agents/focused_implementer.toml') -Raw
if ($focusedText -notmatch '(?m)^model\s*=\s*"gpt-5\.6-luna"\s*$' -or
    $focusedText -notmatch '(?m)^model_reasoning_effort\s*=\s*"medium"\s*$' -or
    $focusedText -notmatch '(?m)^sandbox_mode\s*=\s*"workspace-write"\s*$') {
    throw 'focused_implementer model, effort, or sandbox contract drifted'
}

$researcherText = Get-Content -LiteralPath (Join-Path $repoRoot 'agents/researcher.toml') -Raw
if ($researcherText -notmatch '(?m)^model\s*=\s*"gpt-5\.6-luna"\s*$' -or
    $researcherText -notmatch '(?m)^model_reasoning_effort\s*=\s*"medium"\s*$' -or
    $researcherText -notmatch '(?m)^sandbox_mode\s*=\s*"read-only"\s*$') {
    throw 'researcher model, effort, or sandbox contract drifted'
}
if ($researcherText -match 'Suggested next agent' -or
    $researcherText -notmatch 'Do not recommend a fix, design, routing choice, or next agent' -or
    $researcherText -notmatch 'Decision boundary and unresolved questions') {
    throw 'researcher is not closed to evidence-only output'
}

$designerText = Get-Content -LiteralPath (Join-Path $repoRoot 'agents/designer.toml') -Raw
if ($designerText -match 'recommended agent_type' -or
    $designerText -notmatch 'Implementation slices with scope and settled design state') {
    throw 'designer still selects a model-specific implementation role'
}

$roleDecisionText = Get-Content -LiteralPath (Join-Path $repoRoot 'docs/adr/0014-bounded-role-and-runtime-routing-separation.md') -Raw
if ($roleDecisionText -match '非自明な実装・複数file整合' -or
    $roleDecisionText -notmatch '関連する複数fileを含めて独立検証できるbounded slice') {
    throw 'ADR-0014 contradicts focused_implementer multi-file eligibility'
}

$sliceReviewerText = Get-Content -LiteralPath (Join-Path $repoRoot 'agents/slice_reviewer.toml') -Raw
if ($sliceReviewerText -notmatch '(?m)^model\s*=\s*"gpt-5\.6-luna"\s*$' -or
    $sliceReviewerText -notmatch '(?m)^model_reasoning_effort\s*=\s*"high"\s*$' -or
    $sliceReviewerText -notmatch '(?m)^sandbox_mode\s*=\s*"read-only"\s*$') {
    throw 'slice_reviewer model, effort, or sandbox contract drifted'
}

$targetedReviewerText = Get-Content -LiteralPath (Join-Path $repoRoot 'agents/targeted_reviewer.toml') -Raw
if ($sliceReviewerText -notmatch 'one completed implementation slice' -or
    $sliceReviewerText -notmatch 'Do not inspect or request the complete diff' -or
    $sliceReviewerText -notmatch 'targeted checks cannot directly verify' -or
    $sliceReviewerText -notmatch 'local, single-responsibility slice whose targeted check directly verifies' -or
    $targetedReviewerText -notmatch 'Local, single-responsibility slices whose targeted checks directly verify' -or
    $targetedReviewerText -notmatch 'Specialist review' -or
    $targetedReviewerText -notmatch 'Targeted closure') {
    throw 'slice_reviewer and targeted_reviewer responsibilities overlap or are incomplete'
}

$agentsPolicyText = Get-Content -LiteralPath (Join-Path $repoRoot 'AGENTS.md') -Raw
foreach ($policyFragment in @(
    '局所的・単一責務でtargeted checkがaccepted contractを直接検証できるsliceは独立reviewを起動しない',
    'targeted checkでは直接検証できない具体的なinteractionは`slice_reviewer`',
    '高リスク境界を持つsliceまたは`contract-closure`が要求するtargeted reviewは`targeted_reviewer`',
    'finding修正後に同じscopeの探索reviewまたはcomplete-diff reviewを再開しない',
    '`Full-review gate=run`で許可された一度のcomplete-diff holistic reviewだけは`reviewer`'
)) {
    if ($agentsPolicyText -notmatch [regex]::Escape($policyFragment)) {
        throw "AGENTS.md review routing contract is missing: $policyFragment"
    }
}

foreach ($plannerName in @('planner', 'fast_planner')) {
    $plannerText = Get-Content -LiteralPath (Join-Path $repoRoot "agents/$plannerName.toml") -Raw
    if ($plannerText -notmatch 'Use slice_reviewer only when a concrete non-high-risk interaction cannot be directly verified by targeted checks' -or
        $plannerText -notmatch 'Do not plan independent review for a local, single-responsibility slice whose targeted check directly verifies the accepted contract') {
        throw "$plannerName does not preserve the proportional review trigger"
    }
}

$fastReviewerText = Get-Content -LiteralPath (Join-Path $repoRoot 'agents/fast_reviewer.toml') -Raw
if ($fastReviewerText -notmatch 'only when the user explicitly requests `fast_reviewer`' -or
    $fastReviewerText -notmatch 'Never recommend or start this role automatically') {
    throw 'fast_reviewer can still be selected automatically for local low-risk work'
}

foreach ($roleName in @('planner', 'fast_planner', 'designer', 'implementer', 'researcher', 'focused_implementer', 'slice_reviewer')) {
    $roleText = Get-Content -LiteralPath (Join-Path $repoRoot "agents/$roleName.toml") -Raw
    if ($roleText -notmatch 'Obey the current routing mode supplied by the parent session') {
        throw "$roleName does not defer runtime routing to the parent session"
    }
    foreach ($forbidden in @('quota is healthy', 'quota is constrained', 'while Spark quota')) {
        if ($roleText -match [regex]::Escape($forbidden)) {
            throw "$roleName statically inferred runtime quota state: $forbidden"
        }
    }
}

foreach ($plannerName in @('planner', 'fast_planner')) {
    $plannerText = Get-Content -LiteralPath (Join-Path $repoRoot "agents/$plannerName.toml") -Raw
    if ($plannerText -notmatch 'focused_implementer.*takes precedence' -or
        $plannerText -notmatch 'Use implementer only when a specific condition makes the slice unsuitable for focused_implementer' -or
        $plannerText -notmatch 'After the root session accepts the design, apply the normal focused_implementer / implementer eligibility rules above' -or
        $plannerText -match 'then an implementer slice after the root session accepts the design') {
        throw "$plannerName does not define mutually exclusive focused and Sol implementer eligibility"
    }
}
$implementerText = Get-Content -LiteralPath (Join-Path $repoRoot 'agents/implementer.toml') -Raw
if ($implementerText -notmatch 'Do not use for:' -or
    $implementerText -notmatch 'merely because it spans multiple coherent files') {
    throw 'implementer does not exclude design-settled focused slices'
}
Write-Host 'OK: standard roles, current thread setting, and static role contracts are registered'

foreach ($mode in $modes) {
    $prompt = Invoke-SubagentRoutingHook -Event @{
        hook_event_name = 'UserPromptSubmit'
        turn_id = 'test-turn'
        prompt = 'Implement this feature'
        model = 'gpt-5.6'
        permission_mode = 'default'
        cwd = (Get-Location).Path
    } -Mode $mode
    $promptContext = [string]$prompt.hookSpecificOutput.additionalContext
    if ($prompt.hookSpecificOutput.hookEventName -ne 'UserPromptSubmit') {
        throw "UserPromptSubmit event mismatch in $mode mode"
    }
    if ($promptContext -notmatch "Current Spark routing mode: $([regex]::Escape($mode))") {
        throw "UserPromptSubmit context did not include $mode mode"
    }
    if ($mode -eq 'standard-only') {
        if ($promptContext -notmatch 'automatic role selection' -or $promptContext -notmatch 'explicitly requests that exact fast role') {
            throw 'standard-only context did not define the automatic-selection rule and exact-role exception'
        }
        if ($promptContext -match 'quota (as |is )?exhausted') {
            throw 'standard-only context asserted an exhausted quota instead of describing the active mode'
        }
    }
    Assert-RoutingContextOnly -Context $promptContext

    foreach ($agentName in $agentNames) {
        $parsed = Invoke-SubagentRoutingHook -Event @{
            hook_event_name = 'SubagentStart'
            turn_id = 'test-turn'
            agent_id = "agent-$agentName"
            agent_type = $agentName
            model = 'test-model'
            permission_mode = 'default'
            cwd = (Get-Location).Path
        } -Mode $mode
        $context = [string]$parsed.hookSpecificOutput.additionalContext
        if ($parsed.hookSpecificOutput.hookEventName -ne 'SubagentStart') {
            throw "SubagentStart event mismatch for $agentName in $mode mode"
        }
        if ($context -notmatch "Current Spark routing mode: $([regex]::Escape($mode))") {
            throw "SubagentStart context did not include $mode mode for $agentName"
        }
        Assert-RoutingContextOnly -Context $context

        $hasFallbackReminder = $context -match 'Spark exception condition'
        $expectsFallbackReminder = ($mode -eq 'standard-only' -and $sparkRoles -contains $agentName)
        if ($hasFallbackReminder -ne $expectsFallbackReminder) {
            throw "Unexpected Spark fallback reminder state for $agentName in $mode mode"
        }
    }
    Write-Host "OK: UserPromptSubmit and all SubagentStart roles in $mode mode"
}

$emptyInput = Invoke-SubagentRoutingHookRaw -InputText '' -Mode 'balanced'
if (-not $emptyInput.continue -or $null -ne $emptyInput.hookSpecificOutput) {
    throw 'Empty stdin did not fail open without hook-specific output'
}
Write-Host 'OK: empty stdin fail-open'

$malformedInput = Invoke-SubagentRoutingHookRaw -InputText '{not-json' -Mode 'balanced'
if (-not $malformedInput.continue -or $null -ne $malformedInput.hookSpecificOutput) {
    throw 'Malformed JSON did not fail open without hook-specific output'
}
Write-Host 'OK: malformed JSON fail-open'

$unknownEvent = Invoke-SubagentRoutingHook -Event @{ hook_event_name = 'UnknownEvent' } -Mode 'balanced'
if (-not $unknownEvent.continue -or $null -ne $unknownEvent.hookSpecificOutput) {
    throw 'Unknown event did not fail open without hook-specific output'
}
Write-Host 'OK: unknown event fail-open'

$invalidModePrompt = Invoke-SubagentRoutingHook -Event @{ hook_event_name = 'UserPromptSubmit' } -Mode 'retired-mode'
if ($invalidModePrompt.hookSpecificOutput.additionalContext -notmatch 'Current Spark routing mode: balanced') {
    throw 'Invalid routing mode did not fall back to balanced'
}
Assert-RoutingContextOnly -Context ([string]$invalidModePrompt.hookSpecificOutput.additionalContext)
Write-Host 'OK: invalid mode fallback'

$stateTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "codex-routing-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $stateTestRoot | Out-Null
try {
    $statePath = Join-Path $stateTestRoot 'routing-state.json'
    $event = @{ hook_event_name = 'UserPromptSubmit' }

    $missingState = Invoke-SubagentRoutingHook -Event $event -StatePath $statePath
    if ($missingState.hookSpecificOutput.additionalContext -notmatch 'Current Spark routing mode: balanced') {
        throw 'Missing local state did not fall back to balanced'
    }
    Write-Host 'OK: missing local state fallback'

    Set-Content -LiteralPath $statePath -Value '{not-json' -Encoding UTF8
    $malformedState = Invoke-SubagentRoutingHook -Event $event -StatePath $statePath
    if ($malformedState.hookSpecificOutput.additionalContext -notmatch 'Current Spark routing mode: balanced') {
        throw 'Malformed local state did not fall back to balanced'
    }

    @{ sparkMode = 'retired-mode' } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    $invalidState = Invoke-SubagentRoutingHook -Event $event -StatePath $statePath
    if ($invalidState.hookSpecificOutput.additionalContext -notmatch 'Current Spark routing mode: balanced') {
        throw 'Invalid local state did not fall back to balanced'
    }
    Write-Host 'OK: malformed and invalid local state fallback'

    @{ sparkMode = 'spark-first' } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    $localState = Invoke-SubagentRoutingHook -Event $event -StatePath $statePath
    if ($localState.hookSpecificOutput.additionalContext -notmatch 'Current Spark routing mode: spark-first') {
        throw 'Valid local state was not applied'
    }
    $envOverride = Invoke-SubagentRoutingHook -Event $event -Mode 'standard-only' -StatePath $statePath
    if ($envOverride.hookSpecificOutput.additionalContext -notmatch 'Current Spark routing mode: standard-only') {
        throw 'Environment mode did not take precedence over local state'
    }
    Write-Host 'OK: environment mode precedence over local state'

    $setterPath = Join-Path $PSScriptRoot 'set-spark-routing.ps1'
    & $setterPath balanced -StatePath $statePath | Out-Null
    $writtenState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ($writtenState.sparkMode -ne 'balanced') {
        throw 'set-spark-routing.ps1 did not write the requested mode'
    }
    $stateProperties = @($writtenState.PSObject.Properties.Name | Sort-Object)
    Assert-SameNames -Label 'routing state properties' -Expected @('sparkMode', 'updatedAt') -Actual $stateProperties
    $parsedTimestamp = [datetimeoffset]::MinValue
    if (-not [datetimeoffset]::TryParse([string]$writtenState.updatedAt, [ref]$parsedTimestamp)) {
        throw 'set-spark-routing.ps1 did not write a valid updatedAt timestamp'
    }
    Write-Host 'OK: set-spark-routing output format in isolated state path'
} finally {
    Remove-Item -LiteralPath $stateTestRoot -Recurse -Force
}
