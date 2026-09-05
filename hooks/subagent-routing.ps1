#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Older hosts may not allow changing console encodings. Continue anyway.
}

$stdinText = [Console]::In.ReadToEnd()
$eventName = $null
$agentType = $null
$sparkMode = $null
$inputValid = $false

try {
    if (-not [string]::IsNullOrWhiteSpace($stdinText)) {
        $payload = $stdinText | ConvertFrom-Json -ErrorAction Stop
        $eventName = [string]$payload.hook_event_name
        $agentType = [string]$payload.agent_type
        $inputValid = -not [string]::IsNullOrWhiteSpace($eventName)
    }
} catch {
    # If Codex changes the hook input shape, fail open without event-specific output.
    $eventName = $null
    $agentType = $null
}

function New-AdditionalContextOutput {
    param(
        [Parameter(Mandatory = $true)][string]$HookEventName,
        [Parameter(Mandatory = $true)][string]$AdditionalContext
    )

    $output = [ordered]@{
        continue = $true
        hookSpecificOutput = [ordered]@{
            hookEventName = $HookEventName
            additionalContext = $AdditionalContext
        }
    }

    $output | ConvertTo-Json -Depth 8 -Compress
}

function New-ContinueOutput {
    $output = [ordered]@{
        continue = $true
    }
    $output | ConvertTo-Json -Depth 4 -Compress
}

function Get-SparkRoutingMode {
    $mode = [string]$env:CODEX_SUBAGENT_SPARK_MODE

    if ([string]::IsNullOrWhiteSpace($mode)) {
        $localStatePath = [string]$env:CODEX_SUBAGENT_ROUTING_STATE_PATH
        if ([string]::IsNullOrWhiteSpace($localStatePath)) {
            $localStatePath = Join-Path $PSScriptRoot 'subagent-routing.local.json'
        }
        if (Test-Path -LiteralPath $localStatePath) {
            try {
                $state = Get-Content -LiteralPath $localStatePath -Raw | ConvertFrom-Json -ErrorAction Stop
                $mode = [string]$state.sparkMode
            } catch {
                $mode = ''
            }
        }
    }

    return (ConvertTo-CanonicalSparkRoutingMode -Mode $mode)
}

function ConvertTo-CanonicalSparkRoutingMode {
    param([string]$Mode)

    if ([string]::IsNullOrWhiteSpace($Mode)) {
        return 'balanced'
    }

    $normalized = $Mode.Trim().ToLowerInvariant()
    if (@('spark-first', 'balanced', 'standard-only') -contains $normalized) {
        return $normalized
    }

    return 'balanced'
}

function Get-SparkModeContext {
    param([Parameter(Mandatory = $true)][string]$Mode)

    switch ($Mode) {
        'spark-first' {
            $lines = @(
                'Current Spark routing mode: spark-first.',
                '- Prefer Spark roles for work their agents/*.toml contracts accept; this is a manually selected mode, not a quota measurement.',
                '- Use configured standard roles when the applicable role contract or task risk requires them.'
            )
            ($lines -join "`n")
            break
        }
        'standard-only' {
            $lines = @(
                'Current Spark routing mode: standard-only.',
                '- Use configured standard roles for automatic role selection.',
                '- Start a Spark role only when the user explicitly requests that exact fast role.'
            )
            ($lines -join "`n")
            break
        }
        default {
            $lines = @(
                'Current Spark routing mode: balanced.',
                '- Balance Spark and configured standard roles according to the applicable agents/*.toml role contract.'
            )
            ($lines -join "`n")
            break
        }
    }
}

function Get-GlobalRoutingContext {
    param([Parameter(Mandatory = $true)][string]$Mode)

    return (Get-SparkModeContext -Mode $Mode)
}

function Get-SubagentStartContext {
    param(
        [string]$AgentType,
        [Parameter(Mandatory = $true)][string]$Mode
    )

    $sparkRoles = @('fast_researcher', 'fast_planner', 'fast_implementer', 'fast_validator', 'fast_reviewer')
    $modeContext = Get-SparkModeContext -Mode $Mode
    if (($sparkRoles -contains $AgentType) -and $Mode -eq 'standard-only') {
        $modeContext += "`nSpark exception condition: this fast role may run only when the user explicitly requested this exact role. If it was selected automatically, use the matching configured standard role instead."
    }

    return $modeContext
}

if (-not $inputValid) {
    New-ContinueOutput
    exit 0
}

$sparkMode = Get-SparkRoutingMode

if ($eventName -eq 'UserPromptSubmit') {
    New-AdditionalContextOutput -HookEventName 'UserPromptSubmit' -AdditionalContext (Get-GlobalRoutingContext -Mode $sparkMode)
    exit 0
}

if ($eventName -eq 'SubagentStart') {
    New-AdditionalContextOutput -HookEventName 'SubagentStart' -AdditionalContext (Get-SubagentStartContext -AgentType $agentType -Mode $sparkMode)
    exit 0
}

New-ContinueOutput
