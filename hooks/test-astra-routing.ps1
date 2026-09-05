#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

$hookPath = Join-Path $PSScriptRoot 'astra-routing.ps1'
$setterPath = Join-Path $PSScriptRoot 'set-astra-routing.ps1'
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) "codex-astra-routing-$([guid]::NewGuid().ToString('N'))"
$stateDirectory = Join-Path $testRoot 'state'
$configPath = Join-Path $testRoot 'config.json'

function Invoke-HookRaw {
    param([string]$InputText, [string]$Mode)

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'pwsh'
    foreach ($argument in @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $hookPath)) {
        $startInfo.ArgumentList.Add($argument)
    }
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.Environment['CODEX_ASTRA_ROUTING_STATE_DIR'] = $stateDirectory
    $startInfo.Environment['CODEX_ASTRA_ROUTING_CONFIG_PATH'] = $configPath
    if ([string]::IsNullOrWhiteSpace($Mode)) {
        $startInfo.Environment.Remove('CODEX_ASTRA_ROUTING_MODE') | Out-Null
    } else {
        $startInfo.Environment['CODEX_ASTRA_ROUTING_MODE'] = $Mode
    }

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $process.StandardInput.Write($InputText)
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "Hook failed with exit $($process.ExitCode): $stderr"
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        throw "Hook wrote stderr: $stderr"
    }
    if ([string]::IsNullOrWhiteSpace($stdout)) {
        return $null
    }
    return $stdout | ConvertFrom-Json -ErrorAction Stop
}

function Start-HookProcess {
    param([string]$InputText, [string]$Mode)

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'pwsh'
    foreach ($argument in @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $hookPath)) {
        $startInfo.ArgumentList.Add($argument)
    }
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.Environment['CODEX_ASTRA_ROUTING_STATE_DIR'] = $stateDirectory
    $startInfo.Environment['CODEX_ASTRA_ROUTING_CONFIG_PATH'] = $configPath
    $startInfo.Environment['CODEX_ASTRA_ROUTING_MODE'] = $Mode
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $process.StandardInput.Write($InputText)
    $process.StandardInput.Close()
    return $process
}

function Invoke-Hook {
    param([hashtable]$Event, [string]$Mode = 'conditional')

    return Invoke-HookRaw -InputText ($Event | ConvertTo-Json -Depth 10 -Compress) -Mode $Mode
}

function Assert-Denied {
    param($Output, [string]$Pattern)

    if ($Output.hookSpecificOutput.permissionDecision -ne 'deny') {
        throw 'Expected PreToolUse denial.'
    }
    if ([string]$Output.hookSpecificOutput.permissionDecisionReason -notmatch $Pattern) {
        throw "Denial reason did not match '$Pattern': $($Output.hookSpecificOutput.permissionDecisionReason)"
    }
}

function New-PromptEvent {
    param([string]$SessionId, [string]$TurnId)
    return @{
        hook_event_name = 'UserPromptSubmit'
        session_id = $SessionId
        turn_id = $TurnId
        prompt = 'Investigate the bounded problem.'
    }
}

function New-SpawnEvent {
    param([string]$SessionId, [string]$TurnId, [string]$Role, [string]$Model = '', [string]$ReasoningEffort = '')
    $input = @{ agent_type = $Role; task_name = "task-$Role"; message = 'Bounded task.' }
    if (-not [string]::IsNullOrWhiteSpace($Model)) {
        $input.model = $Model
    }
    if (-not [string]::IsNullOrWhiteSpace($ReasoningEffort)) {
        $input.reasoning_effort = $ReasoningEffort
    }
    return @{
        hook_event_name = 'PreToolUse'
        session_id = $SessionId
        turn_id = $TurnId
        tool_name = 'spawn_agent'
        tool_use_id = "tool-$([guid]::NewGuid().ToString('N'))"
        tool_input = $input
    }
}

try {
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    foreach ($roleName in @('designer', 'reviewer', 'targeted_reviewer')) {
        $roleText = Get-Content -LiteralPath (Join-Path $repositoryRoot "agents/$roleName.toml") -Raw
        if ($roleText -notmatch '(?m)^model = "gpt-5\.6-sol"\r?$') {
            throw "$roleName is not pinned to gpt-5.6-sol."
        }
    }
    foreach ($roleName in @('astra_consultant', 'astra_reviewer')) {
        $roleText = Get-Content -LiteralPath (Join-Path $repositoryRoot "agents/$roleName.toml") -Raw
        foreach ($required in @(
            '(?m)^model = "gpt-6-astra"\r?$',
            '(?m)^model_reasoning_effort = "medium"\r?$',
            '(?m)^service_tier = "default"\r?$',
            '(?m)^sandbox_mode = "read-only"\r?$',
            '(?m)^fast_mode = false\r?$'
        )) {
            if ($roleText -notmatch $required) {
                throw "$roleName does not satisfy its pinned model, effort, service tier, or sandbox contract."
            }
        }
    }
    $astraProfile = Get-Content -LiteralPath (Join-Path $repositoryRoot 'config/astra.config.toml') -Raw
    if ($astraProfile -notmatch '(?m)^model = "gpt-6-astra"\r?$' -or $astraProfile -notmatch '(?m)^default_subagent_model = "gpt-5\.6-sol"\r?$') {
        throw 'The Astra root profile does not keep default children on gpt-5.6-sol.'
    }
    $registry = Get-Content -LiteralPath (Join-Path $repositoryRoot 'config/agents.example.toml') -Raw
    foreach ($roleName in @('astra_consultant', 'astra_reviewer')) {
        if ($registry -notmatch "(?m)^\[agents\.$roleName\]\r?$") {
            throw "$roleName is missing from the example agent registry."
        }
    }
    $hooksConfig = Get-Content -LiteralPath (Join-Path $repositoryRoot 'hooks.json') -Raw | ConvertFrom-Json -ErrorAction Stop
    foreach ($eventName in @('UserPromptSubmit', 'SessionStart', 'PreToolUse', 'SubagentStart', 'SubagentStop')) {
        $commands = @($hooksConfig.hooks.$eventName.hooks.command)
        if (-not ($commands | Where-Object { $_ -match 'astra-routing\.ps1' })) {
            throw "hooks.json does not register astra-routing.ps1 for $eventName."
        }
    }
    Write-Host 'OK: Sol defaults, dedicated Astra roles, profile inheritance, and hook registration'

    $session = 'session-conditional'
    $turn1 = 'turn-1'
    Invoke-Hook -Event (New-PromptEvent -SessionId $session -TurnId $turn1) | Out-Null

    $childBlockedSession = 'session-child-blocked'
    Invoke-Hook -Event (New-PromptEvent -SessionId $childBlockedSession -TurnId 'turn-child-blocked') | Out-Null
    $childSpawnEvent = New-SpawnEvent -SessionId $childBlockedSession -TurnId 'turn-child-blocked' -Role 'astra_consultant'
    $childSpawnEvent.agent_id = 'agent-standard-child'
    $childSpawnEvent.agent_type = 'researcher'
    $childBlocked = Invoke-Hook -Event $childSpawnEvent
    Assert-Denied -Output $childBlocked -Pattern 'subagents may not start or continue Astra work'
    Write-Host 'OK: child agents cannot dispatch or continue Astra work'

    $ordinary = Invoke-Hook -Event (New-SpawnEvent -SessionId $session -TurnId $turn1 -Role 'researcher')
    if ($null -ne $ordinary) {
        throw 'A non-Astra role was unexpectedly controlled by the Astra guard.'
    }

    $first = Invoke-Hook -Event (New-SpawnEvent -SessionId $session -TurnId $turn1 -Role 'astra_consultant')
    if ($null -ne $first) {
        throw 'The first conditional Astra dispatch was unexpectedly denied.'
    }

    $start = Invoke-Hook -Event @{
        hook_event_name = 'SubagentStart'
        session_id = $session
        turn_id = $turn1
        agent_id = 'agent-astra'
        agent_type = 'astra_consultant'
    }
    if ([string]$start.hookSpecificOutput.additionalContext -match 'not matched to a guard reservation') {
        throw 'A reserved Astra start was reported as unreserved.'
    }

    Invoke-Hook -Event @{
        hook_event_name = 'UserPromptSubmit'
        session_id = $session
        turn_id = 'child-turn-1'
        agent_id = 'agent-astra'
        agent_type = 'astra_consultant'
        prompt = 'Child continuation.'
    } | Out-Null

    $parallel = Invoke-Hook -Event (New-SpawnEvent -SessionId $session -TurnId $turn1 -Role 'astra_reviewer')
    Assert-Denied -Output $parallel -Pattern 'active or reserved'

    Invoke-Hook -Event @{
        hook_event_name = 'SubagentStop'
        session_id = $session
        turn_id = $turn1
        agent_id = 'agent-astra'
        agent_type = 'astra_consultant'
    } | Out-Null

    $compactContext = Invoke-Hook -Event @{
        hook_event_name = 'SessionStart'
        session_id = $session
        source = 'compact'
    }
    if ([string]$compactContext.hookSpecificOutput.additionalContext -notmatch 'remaining for the recorded parent turn: 0') {
        throw 'Compaction context did not preserve the consumed Astra allowance.'
    }
    Invoke-Hook -Event (New-PromptEvent -SessionId $session -TurnId $turn1) | Out-Null
    $sameTurnFollowup = Invoke-Hook -Event @{
        hook_event_name = 'PreToolUse'
        session_id = $session
        turn_id = $turn1
        tool_name = 'followup_task'
        tool_use_id = 'tool-followup-same-turn'
        tool_input = @{ target = 'agent-astra'; message = 'Continue.' }
    }
    Assert-Denied -Output $sameTurnFollowup -Pattern 'already used'

    $turn2 = 'turn-2'
    Invoke-Hook -Event (New-PromptEvent -SessionId $session -TurnId $turn2) | Out-Null
    $nextTurnFollowup = Invoke-Hook -Event @{
        hook_event_name = 'PreToolUse'
        session_id = $session
        turn_id = $turn2
        tool_name = 'followup_task'
        tool_use_id = 'tool-followup-next-turn'
        tool_input = @{ target = 'agent-astra'; message = 'Continue.' }
    }
    if ($null -ne $nextTurnFollowup) {
        throw 'A known Astra follow-up did not receive the next user turn allowance.'
    }
    Invoke-Hook -Event @{
        hook_event_name = 'SubagentStop'
        session_id = $session
        turn_id = $turn2
        agent_id = 'agent-astra'
        agent_type = 'astra_consultant'
    } | Out-Null
    Invoke-Hook -Event (New-PromptEvent -SessionId $session -TurnId 'turn-3') | Out-Null
    $followupAfterStop = Invoke-Hook -Event @{
        hook_event_name = 'PreToolUse'
        session_id = $session
        turn_id = 'turn-3'
        tool_name = 'followup_task'
        tool_use_id = 'tool-followup-after-stop'
        tool_input = @{ target = '/root/task-astra_consultant'; message = 'Continue again.' }
    }
    if ($null -ne $followupAfterStop) {
        throw 'SubagentStop did not release a follow-up reservation when no SubagentStart event occurred.'
    }
    Write-Host 'OK: conditional shared limit, concurrency, duplicate prompt, and follow-up accounting'

    $raceSession = 'session-race'
    $raceTurn = 'turn-race'
    Invoke-Hook -Event (New-PromptEvent -SessionId $raceSession -TurnId $raceTurn) | Out-Null
    $raceJson1 = (New-SpawnEvent -SessionId $raceSession -TurnId $raceTurn -Role 'astra_consultant') | ConvertTo-Json -Depth 10 -Compress
    $raceJson2 = (New-SpawnEvent -SessionId $raceSession -TurnId $raceTurn -Role 'astra_reviewer') | ConvertTo-Json -Depth 10 -Compress
    $raceProcesses = @(
        (Start-HookProcess -InputText $raceJson1 -Mode 'conditional'),
        (Start-HookProcess -InputText $raceJson2 -Mode 'conditional')
    )
    $raceOutputs = foreach ($process in $raceProcesses) {
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0 -or -not [string]::IsNullOrWhiteSpace($stderr)) {
            throw "Concurrent hook process failed: $stderr"
        }
        $stdout
    }
    if (@($raceOutputs | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -ne 1 -or @($raceOutputs | Where-Object { $_ -match 'permissionDecision' }).Count -ne 1) {
        throw 'Concurrent Astra reservations did not produce exactly one allowance and one denial.'
    }
    Write-Host 'OK: concurrent reservations share one atomic allowance'

    $pendingSession = 'session-pending'
    Invoke-Hook -Event (New-PromptEvent -SessionId $pendingSession -TurnId 'turn-pending-1') | Out-Null
    $pendingFirst = Invoke-Hook -Event (New-SpawnEvent -SessionId $pendingSession -TurnId 'turn-pending-1' -Role 'astra_consultant')
    if ($null -ne $pendingFirst) {
        throw 'The first pending reservation was unexpectedly denied.'
    }
    Invoke-Hook -Event (New-PromptEvent -SessionId $pendingSession -TurnId 'turn-pending-2') | Out-Null
    $pendingSecond = Invoke-Hook -Event (New-SpawnEvent -SessionId $pendingSession -TurnId 'turn-pending-2' -Role 'astra_reviewer')
    Assert-Denied -Output $pendingSecond -Pattern 'active or reserved'
    Write-Host 'OK: a new parent turn does not erase an unresolved reservation'

    $unreservedSession = 'session-unreserved'
    $unreservedTurn = 'turn-unreserved'
    Invoke-Hook -Event (New-PromptEvent -SessionId $unreservedSession -TurnId $unreservedTurn) | Out-Null
    $unreservedStart = Invoke-Hook -Event @{
        hook_event_name = 'SubagentStart'
        session_id = $unreservedSession
        turn_id = $unreservedTurn
        agent_id = 'agent-unreserved'
        agent_type = 'astra_reviewer'
    }
    if ([string]$unreservedStart.hookSpecificOutput.additionalContext -notmatch 'not matched to a guard reservation') {
        throw 'An unreserved Astra start did not report its routing validation gap.'
    }
    Invoke-Hook -Event @{
        hook_event_name = 'SubagentStop'
        session_id = $unreservedSession
        turn_id = $unreservedTurn
        agent_id = 'agent-unreserved'
        agent_type = 'astra_reviewer'
    } | Out-Null
    $afterUnreserved = Invoke-Hook -Event (New-SpawnEvent -SessionId $unreservedSession -TurnId $unreservedTurn -Role 'astra_consultant')
    Assert-Denied -Output $afterUnreserved -Pattern 'already used'
    Write-Host 'OK: an unreserved Astra start invalidates the remaining turn allowance'

    Invoke-Hook -Event (New-PromptEvent -SessionId 'session-explicit' -TurnId 'turn-1') | Out-Null
    $explicitModel = Invoke-Hook -Event (New-SpawnEvent -SessionId 'session-explicit' -TurnId 'turn-1' -Role 'researcher' -Model 'gpt-6-astra')
    Assert-Denied -Output $explicitModel -Pattern 'only astra_consultant and astra_reviewer'
    Invoke-Hook -Event (New-PromptEvent -SessionId 'session-effort' -TurnId 'turn-1') | Out-Null
    $highEffort = Invoke-Hook -Event (New-SpawnEvent -SessionId 'session-effort' -TurnId 'turn-1' -Role 'astra_consultant' -ReasoningEffort 'high')
    Assert-Denied -Output $highEffort -Pattern 'reasoning effort is fixed to medium'
    Write-Host 'OK: explicit Astra model and effort overrides cannot bypass dedicated role settings'

    $manualSession = 'session-manual'
    $manualTurn = 'turn-manual'
    $manualPrompt = Invoke-Hook -Event (New-PromptEvent -SessionId $manualSession -TurnId $manualTurn) -Mode 'manual'
    if ([string]$manualPrompt.hookSpecificOutput.additionalContext -notmatch "session_id=$manualSession turn_id=$manualTurn") {
        throw 'Manual mode did not expose the exact grant target to the parent context.'
    }
    $manualDenied = Invoke-Hook -Event (New-SpawnEvent -SessionId $manualSession -TurnId $manualTurn -Role 'astra_reviewer') -Mode 'manual'
    Assert-Denied -Output $manualDenied -Pattern 'explicit manual grant'

    & $setterPath -SessionId $manualSession -TurnId $manualTurn -Role astra_reviewer -Count 1 -ConfigPath $configPath -StateDirectory $stateDirectory | Out-Null
    $manualAllowed = Invoke-Hook -Event (New-SpawnEvent -SessionId $manualSession -TurnId $manualTurn -Role 'astra_reviewer') -Mode 'manual'
    if ($null -ne $manualAllowed) {
        throw 'An exact manual grant did not allow the requested Astra role.'
    }
    Write-Host 'OK: manual mode requires and consumes an exact grant'

    $offSession = 'session-off'
    Invoke-Hook -Event (New-PromptEvent -SessionId $offSession -TurnId 'turn-off') -Mode 'off' | Out-Null
    $offDenied = Invoke-Hook -Event (New-SpawnEvent -SessionId $offSession -TurnId 'turn-off' -Role 'astra_consultant') -Mode 'off'
    Assert-Denied -Output $offDenied -Pattern 'disabled'
    Write-Host 'OK: off mode denies Astra without affecting ordinary roles'

    $corruptSession = 'session-corrupt'
    Invoke-Hook -Event (New-PromptEvent -SessionId $corruptSession -TurnId 'turn-a') | Out-Null
    $stateFile = Get-ChildItem -LiteralPath $stateDirectory -Filter '*.json' | Where-Object {
        try { (Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json).sessionId -eq $corruptSession } catch { $false }
    } | Select-Object -First 1
    Set-Content -LiteralPath $stateFile.FullName -Value '{broken' -Encoding UTF8
    Invoke-Hook -Event (New-PromptEvent -SessionId $corruptSession -TurnId 'turn-b') | Out-Null
    $corruptDenied = Invoke-Hook -Event (New-SpawnEvent -SessionId $corruptSession -TurnId 'turn-b' -Role 'astra_consultant')
    Assert-Denied -Output $corruptDenied -Pattern 'requires recovery'
    $ordinaryAfterCorruption = Invoke-Hook -Event (New-SpawnEvent -SessionId $corruptSession -TurnId 'turn-b' -Role 'validator')
    if ($null -ne $ordinaryAfterCorruption) {
        throw 'Corrupt Astra state blocked a non-Astra role.'
    }
    Invoke-Hook -Event (New-PromptEvent -SessionId $corruptSession -TurnId 'turn-c') | Out-Null
    $stillCorrupt = Invoke-Hook -Event (New-SpawnEvent -SessionId $corruptSession -TurnId 'turn-c' -Role 'astra_consultant')
    Assert-Denied -Output $stillCorrupt -Pattern 'requires recovery'
    Write-Host 'OK: corrupt state remains fail-closed across turns while ordinary roles stay available'

} finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
