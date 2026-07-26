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
    'validator',
    'reviewer',
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
