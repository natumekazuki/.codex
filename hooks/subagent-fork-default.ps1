#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'
$event = [Console]::In.ReadToEnd() | ConvertFrom-Json -AsHashtable
if ($event.hook_event_name -ne 'PreToolUse' -or $event.tool_name -notin @('spawn_agent', 'Agent')) {
    exit 0
}
$arguments = $event.tool_input
if ($arguments -isnot [System.Collections.IDictionary]) {
    throw 'Expected spawn_agent arguments to be a JSON object.'
}
$isAstraParent = $event.model -match '^gpt-6-astra(?:-|$)'
$isAstraTarget = $arguments.agent_type -eq 'general_astra' -or $arguments.model -match '^gpt-6-astra(?:-|$)'
if ($isAstraParent -and $isAstraTarget) {
    @{
        hookSpecificOutput = @{
            hookEventName = 'PreToolUse'
            permissionDecision = 'deny'
            permissionDecisionReason = 'An Astra parent must not spawn an Astra child. Use Luna or Sol.'
        }
    } | ConvertTo-Json -Depth 100 -Compress
    exit 0
}
$arguments['fork_turns'] = 'none'
@{
    hookSpecificOutput = @{
        hookEventName = 'PreToolUse'
        permissionDecision = 'allow'
        updatedInput = $arguments
    }
} | ConvertTo-Json -Depth 100 -Compress
