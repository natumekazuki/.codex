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
if ($arguments.Contains('fork_turns')) {
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
