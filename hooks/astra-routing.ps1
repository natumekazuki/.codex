#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Older hosts may not allow changing console encodings. Continue anyway.
}

$astraRoles = @('astra_consultant', 'astra_reviewer')
$astraModel = 'gpt-6-astra'

function New-ContextOutput {
    param([string]$EventName, [string]$Context)

    [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName = $EventName
            additionalContext = $Context
        }
    } | ConvertTo-Json -Depth 8 -Compress
}

function New-DenyOutput {
    param([string]$Reason)

    [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName = 'PreToolUse'
            permissionDecision = 'deny'
            permissionDecisionReason = $Reason
        }
    } | ConvertTo-Json -Depth 8 -Compress
}

function Get-Sha256Text {
    param([string]$Text)

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $hash = [System.Security.Cryptography.SHA256]::HashData($bytes)
    return [Convert]::ToHexString($hash).ToLowerInvariant()
}

function Get-StateDirectory {
    $configured = [string]$env:CODEX_ASTRA_ROUTING_STATE_DIR
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        return $configured
    }
    return (Join-Path $PSScriptRoot '.astra-routing-state')
}

function Get-StatePath {
    param([string]$SessionId)

    return (Join-Path (Get-StateDirectory) "$(Get-Sha256Text -Text $SessionId).json")
}

function Get-RoutingMode {
    $mode = [string]$env:CODEX_ASTRA_ROUTING_MODE
    if ([string]::IsNullOrWhiteSpace($mode)) {
        $configPath = [string]$env:CODEX_ASTRA_ROUTING_CONFIG_PATH
        if ([string]::IsNullOrWhiteSpace($configPath)) {
            $configPath = Join-Path $PSScriptRoot 'astra-routing.local.json'
        }
        if (Test-Path -LiteralPath $configPath) {
            try {
                $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json -ErrorAction Stop
                $mode = [string]$config.mode
            } catch {
                return 'off'
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($mode)) {
        return 'manual'
    }
    $normalized = $mode.Trim().ToLowerInvariant()
    if (@('conditional', 'manual', 'off') -contains $normalized) {
        return $normalized
    }
    return 'off'
}

function New-State {
    param([string]$SessionId, [string]$TurnId, [string]$Mode, [bool]$Healthy = $true)

    [ordered]@{
        version = 1
        sessionId = $SessionId
        currentTurnId = $TurnId
        automaticRemaining = $(if ($Healthy -and $Mode -eq 'conditional') { 1 } else { 0 })
        recoveryRequired = -not $Healthy
        pendingAstra = $null
        activeAstra = $null
        knownAstraAgents = @()
        manualGrant = $null
        updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function Test-JsonObjectShape {
    param($Value, [string[]]$PropertyNames)

    if ($null -eq $Value -or $Value -isnot [pscustomobject]) {
        return $false
    }
    $actualNames = @($Value.PSObject.Properties.Name | Sort-Object)
    $expectedNames = @($PropertyNames | Sort-Object)
    return (($actualNames -join "`n") -ceq ($expectedNames -join "`n"))
}

function Test-JsonIntegerInRange {
    param($Value, [long]$Minimum, [long]$Maximum)

    $integerTypes = @(
        [byte], [sbyte], [int16], [uint16], [int32], [uint32], [int64], [uint64]
    )
    if (-not ($integerTypes | Where-Object { $Value -is $_ })) {
        return $false
    }
    try {
        $number = [decimal]$Value
        return ($number -ge $Minimum -and $number -le $Maximum)
    } catch {
        return $false
    }
}

function Test-RoundTripTimestamp {
    param($Value)

    if ($Value -is [DateTime]) {
        return $Value.Kind -eq [DateTimeKind]::Utc
    }
    if ($Value -is [DateTimeOffset]) {
        return $Value.Offset -eq [TimeSpan]::Zero
    }
    if ($Value -isnot [string] -or [string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }
    $parsed = [DateTimeOffset]::MinValue
    return [DateTimeOffset]::TryParseExact(
        $Value,
        'o',
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind,
        [ref]$parsed
    )
}

function Test-AstraAgentRecord {
    param($Value)

    if (-not (Test-JsonObjectShape -Value $Value -PropertyNames @('agentId', 'taskName', 'role'))) {
        return $false
    }
    return (
        $Value.agentId -is [string] -and
        -not [string]::IsNullOrWhiteSpace($Value.agentId) -and
        $Value.taskName -is [string] -and
        $Value.role -is [string] -and
        $astraRoles -contains $Value.role
    )
}

function Test-AstraRoutingState {
    param($State, [string]$SessionId)

    $rootProperties = @(
        'version', 'sessionId', 'currentTurnId', 'automaticRemaining', 'recoveryRequired',
        'pendingAstra', 'activeAstra', 'knownAstraAgents', 'manualGrant', 'updatedAt'
    )
    if (-not (Test-JsonObjectShape -Value $State -PropertyNames $rootProperties)) {
        return $false
    }
    if (-not (Test-JsonIntegerInRange -Value $State.version -Minimum 1 -Maximum 1)) {
        return $false
    }
    if ($State.sessionId -isnot [string] -or $State.sessionId -cne $SessionId) {
        return $false
    }
    if ($State.currentTurnId -isnot [string] -or [string]::IsNullOrWhiteSpace($State.currentTurnId)) {
        return $false
    }
    if (-not (Test-JsonIntegerInRange -Value $State.automaticRemaining -Minimum 0 -Maximum 1)) {
        return $false
    }
    if ($State.recoveryRequired -isnot [bool] -or -not (Test-RoundTripTimestamp -Value $State.updatedAt)) {
        return $false
    }
    if ($State.knownAstraAgents -isnot [array]) {
        return $false
    }

    $knownAgentIds = @{}
    foreach ($known in $State.knownAstraAgents) {
        if (-not (Test-AstraAgentRecord -Value $known) -or $knownAgentIds.ContainsKey($known.agentId)) {
            return $false
        }
        $knownAgentIds[$known.agentId] = $known
    }

    if ($null -ne $State.activeAstra) {
        if (-not (Test-AstraAgentRecord -Value $State.activeAstra)) {
            return $false
        }
        $activeId = $State.activeAstra.agentId
        if (-not $knownAgentIds.ContainsKey($activeId)) {
            return $false
        }
        $knownActive = $knownAgentIds[$activeId]
        if ($knownActive.taskName -cne $State.activeAstra.taskName -or $knownActive.role -cne $State.activeAstra.role) {
            return $false
        }
    }

    if ($null -ne $State.pendingAstra) {
        $pendingProperties = @('toolUseId', 'action', 'role', 'taskName', 'turnId')
        if (-not (Test-JsonObjectShape -Value $State.pendingAstra -PropertyNames $pendingProperties)) {
            return $false
        }
        if (
            $State.pendingAstra.toolUseId -isnot [string] -or [string]::IsNullOrWhiteSpace($State.pendingAstra.toolUseId) -or
            $State.pendingAstra.action -isnot [string] -or @('spawn', 'followup') -notcontains $State.pendingAstra.action -or
            $State.pendingAstra.role -isnot [string] -or $astraRoles -notcontains $State.pendingAstra.role -or
            $State.pendingAstra.taskName -isnot [string] -or [string]::IsNullOrWhiteSpace($State.pendingAstra.taskName) -or
            $State.pendingAstra.turnId -isnot [string] -or [string]::IsNullOrWhiteSpace($State.pendingAstra.turnId)
        ) {
            return $false
        }
    }
    if ($null -ne $State.activeAstra -and $null -ne $State.pendingAstra) {
        return $false
    }

    if ($null -ne $State.manualGrant) {
        $grantProperties = @('turnId', 'roles', 'remaining', 'updatedAt')
        if (-not (Test-JsonObjectShape -Value $State.manualGrant -PropertyNames $grantProperties)) {
            return $false
        }
        if (
            $State.manualGrant.turnId -isnot [string] -or $State.manualGrant.turnId -cne $State.currentTurnId -or
            $State.manualGrant.roles -isnot [array] -or $State.manualGrant.roles.Count -lt 1 -or
            -not (Test-JsonIntegerInRange -Value $State.manualGrant.remaining -Minimum 0 -Maximum ([int]::MaxValue)) -or
            -not (Test-RoundTripTimestamp -Value $State.manualGrant.updatedAt)
        ) {
            return $false
        }
        $grantRoles = @($State.manualGrant.roles)
        if (@($grantRoles | Where-Object { $_ -isnot [string] -or $astraRoles -notcontains $_ }).Count -gt 0) {
            return $false
        }
    }

    if ([bool]$State.recoveryRequired -and (
        [int]$State.automaticRemaining -ne 0 -or
        $null -ne $State.pendingAstra -or
        $null -ne $State.activeAstra -or
        $State.knownAstraAgents.Count -ne 0 -or
        $null -ne $State.manualGrant
    )) {
        return $false
    }
    return $true
}

function Read-State {
    param([string]$Path, [string]$SessionId)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        $state = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop
        if (-not (Test-AstraRoutingState -State $state -SessionId $SessionId)) {
            throw 'State schema or invariant mismatch.'
        }
        return $state
    } catch {
        return $false
    }
}

function Write-State {
    param([string]$Path, $State)

    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $State.updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    $temporaryPath = Join-Path $directory ".$([System.IO.Path]::GetFileName($Path)).$([guid]::NewGuid().ToString('N')).tmp"
    try {
        $State | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporaryPath -Encoding UTF8
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Invoke-WithStateLock {
    param([string]$StatePath, [scriptblock]$Action)

    $mutexName = "codex-astra-routing-$(Get-Sha256Text -Text ([System.IO.Path]::GetFullPath($StatePath)))"
    $mutex = [System.Threading.Mutex]::new($false, $mutexName)
    $acquired = $false
    try {
        $acquired = $mutex.WaitOne([TimeSpan]::FromSeconds(5))
        if (-not $acquired) {
            throw 'Timed out waiting for Astra routing state lock.'
        }
        & $Action
    } finally {
        if ($acquired) {
            $mutex.ReleaseMutex()
        }
        $mutex.Dispose()
    }
}

function Get-PolicyContext {
    param([string]$Mode, $State, [string]$SessionId, [string]$TurnId)

    $remaining = if ($null -ne $State -and $State -ne $false) { [int]$State.automaticRemaining } else { 0 }
    $executionState = if ($null -ne $State -and $State -ne $false -and $null -ne $State.activeAstra) {
        'active'
    } elseif ($null -ne $State -and $State -ne $false -and $null -ne $State.pendingAstra) {
        'reserved'
    } else {
        'idle'
    }
    $lines = @(
        "Current Astra routing mode: $Mode.",
        '- Normal work uses the configured Sol and Luna roles. Astra is limited to astra_consultant and astra_reviewer.',
        '- Automatic Astra selection is allowed only for an important unresolved design trade-off, a contradiction remaining after concrete investigation, or a difficult counterexample inside an already-required review.',
        '- Diff size, file count, a single command failure, missing authorization or information, model availability, and just-in-case confirmation are not triggers.',
        '- One parent user turn has at most one Astra work dispatch across both roles; follow-up and retry consume it, while wait, status, result retrieval, and termination do not.',
        '- After one Astra response, continue with Sol or Luna. Extra Astra work requires explicit scope and count.'
    )
    $lines += "Current Astra execution state: $executionState."
    if ($Mode -eq 'conditional') {
        $lines += "Automatic Astra dispatches remaining for the recorded parent turn: $remaining."
    } elseif ($Mode -eq 'manual') {
        $lines += 'Astra requires an exact session-and-turn manual grant before spawn or follow-up.'
        $recordedTurnId = if (-not [string]::IsNullOrWhiteSpace($TurnId)) { $TurnId } elseif ($null -ne $State -and $State -ne $false) { [string]$State.currentTurnId } else { '' }
        if (-not [string]::IsNullOrWhiteSpace($SessionId) -and -not [string]::IsNullOrWhiteSpace($recordedTurnId)) {
            $lines += "Manual grant target: session_id=$SessionId turn_id=$recordedTurnId."
        }
    } else {
        $lines += 'Astra dispatch is disabled.'
    }
    return ($lines -join "`n")
}

function Get-AstraRequest {
    param([string]$ToolName, $ToolInput, $State)

    if ($ToolName -eq 'spawn_agent') {
        $role = [string]$ToolInput.agent_type
        $model = [string]$ToolInput.model
        $isAstra = ($astraRoles -contains $role) -or ($model -eq $astraModel)
        if (-not $isAstra) {
            return $null
        }
        return [ordered]@{
            action = 'spawn'
            role = $role
            model = $model
            target = [string]$ToolInput.task_name
        }
    }

    if ($ToolName -eq 'followup_task' -and $null -ne $State -and $State -ne $false) {
        $target = [string]$ToolInput.target
        foreach ($known in @($State.knownAstraAgents)) {
            $taskName = [string]$known.taskName
            $matchesTaskName = $target -eq $taskName -or (-not [string]::IsNullOrWhiteSpace($taskName) -and $target.EndsWith("/$taskName", [System.StringComparison]::Ordinal))
            if ($target -eq [string]$known.agentId -or $matchesTaskName) {
                return [ordered]@{
                    action = 'followup'
                    role = [string]$known.role
                    model = $astraModel
                    target = $target
                }
            }
        }
    }
    return $null
}

function Test-AndConsumeAllowance {
    param($State, [string]$Mode, [string]$TurnId, [string]$Role)

    if ([bool]$State.recoveryRequired) {
        return 'Astra routing state requires recovery after confirming that no Astra agent is active.'
    }
    if ([string]$State.currentTurnId -ne $TurnId) {
        return 'Astra dispatch denied because the current parent user turn is not recorded.'
    }
    if ($null -ne $State.activeAstra -or $null -ne $State.pendingAstra) {
        return 'Astra dispatch denied because another Astra dispatch is active or reserved in this root session.'
    }
    if ($Mode -eq 'off') {
        return 'Astra dispatch is disabled by the current routing mode.'
    }
    if ($Mode -eq 'conditional') {
        if ([int]$State.automaticRemaining -lt 1) {
            return 'Astra dispatch denied because this parent user turn already used its shared Astra dispatch.'
        }
        $State.automaticRemaining = [int]$State.automaticRemaining - 1
        return $null
    }
    if ($Mode -eq 'manual') {
        $grant = $State.manualGrant
        if ($null -eq $grant -or [string]$grant.turnId -ne $TurnId -or [int]$grant.remaining -lt 1 -or -not (@($grant.roles) -contains $Role)) {
            return 'Astra dispatch requires an explicit manual grant for this session, turn, role, and count.'
        }
        $grant.remaining = [int]$grant.remaining - 1
        return $null
    }
    return 'Astra dispatch denied because the routing mode is invalid.'
}

$stdinText = [Console]::In.ReadToEnd()
try {
    if ([string]::IsNullOrWhiteSpace($stdinText)) {
        exit 0
    }
    $payload = $stdinText | ConvertFrom-Json -ErrorAction Stop
} catch {
    exit 0
}

$eventName = [string]$payload.hook_event_name
$sessionId = [string]$payload.session_id
$turnId = [string]$payload.turn_id
$mode = Get-RoutingMode

if ([string]::IsNullOrWhiteSpace($sessionId)) {
    if ($eventName -eq 'PreToolUse') {
        if ([string]$payload.tool_name -eq 'followup_task') {
            New-DenyOutput -Reason 'Agent follow-up denied because its target model cannot be verified without the root session identity.'
            exit 0
        }
        $request = Get-AstraRequest -ToolName ([string]$payload.tool_name) -ToolInput $payload.tool_input -State $null
        if ($null -ne $request) {
            New-DenyOutput -Reason 'Astra dispatch denied because the root session identity is missing.'
        }
    }
    exit 0
}

$statePath = Get-StatePath -SessionId $sessionId

if ($eventName -eq 'UserPromptSubmit') {
    if ([string]::IsNullOrWhiteSpace($turnId)) {
        exit 0
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$payload.agent_id)) {
        $state = Read-State -Path $statePath -SessionId $sessionId
        New-ContextOutput -EventName 'UserPromptSubmit' -Context (Get-PolicyContext -Mode $mode -State $state -SessionId $sessionId -TurnId '')
        exit 0
    }
    $script:eventState = $null
    Invoke-WithStateLock -StatePath $statePath -Action {
        $loaded = Read-State -Path $statePath -SessionId $sessionId
        if ($loaded -eq $false) {
            $script:eventState = New-State -SessionId $sessionId -TurnId $turnId -Mode $mode -Healthy $false
        } elseif ($null -eq $loaded) {
            $script:eventState = New-State -SessionId $sessionId -TurnId $turnId -Mode $mode
        } else {
            $script:eventState = $loaded
            if ([string]$script:eventState.currentTurnId -ne $turnId) {
                $script:eventState.currentTurnId = $turnId
                $script:eventState.automaticRemaining = $(if ([bool]$script:eventState.recoveryRequired) { 0 } elseif ($mode -eq 'conditional') { 1 } else { 0 })
                $script:eventState.manualGrant = $null
            }
        }
        Write-State -Path $statePath -State $script:eventState
    }
    New-ContextOutput -EventName 'UserPromptSubmit' -Context (Get-PolicyContext -Mode $mode -State $script:eventState -SessionId $sessionId -TurnId $turnId)
    exit 0
}

if ($eventName -eq 'SessionStart') {
    $state = Read-State -Path $statePath -SessionId $sessionId
    New-ContextOutput -EventName 'SessionStart' -Context (Get-PolicyContext -Mode $mode -State $state -SessionId $sessionId -TurnId '')
    exit 0
}

if ($eventName -eq 'PreToolUse') {
    $toolName = [string]$payload.tool_name
    if (@('spawn_agent', 'followup_task') -notcontains $toolName) {
        exit 0
    }
    $script:dispatchDecision = $null
    Invoke-WithStateLock -StatePath $statePath -Action {
        $state = Read-State -Path $statePath -SessionId $sessionId
        if ($toolName -eq 'followup_task' -and ($state -eq $false -or $null -eq $state -or [bool]$state.recoveryRequired)) {
            $script:dispatchDecision = 'Agent follow-up denied because its target model cannot be verified while Astra routing state is missing, invalid, or requires recovery.'
            return
        }
        $request = Get-AstraRequest -ToolName $toolName -ToolInput $payload.tool_input -State $state
        if ($null -eq $request) {
            return
        }
        if ($state -eq $false -or $null -eq $state) {
            $script:dispatchDecision = 'Astra dispatch denied because its per-session routing state is missing or invalid.'
            return
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$payload.agent_id)) {
            $script:dispatchDecision = 'Astra dispatch denied because subagents may not start or continue Astra work.'
            return
        }
        if ($astraRoles -notcontains [string]$request.role) {
            $script:dispatchDecision = 'Astra dispatch denied because only astra_consultant and astra_reviewer may use gpt-6-astra.'
            return
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$request.model) -and [string]$request.model -ne $astraModel) {
            $script:dispatchDecision = 'Astra role dispatch denied because the explicit model does not match gpt-6-astra.'
            return
        }
        $requestedEffort = [string]$payload.tool_input.reasoning_effort
        if (-not [string]::IsNullOrWhiteSpace($requestedEffort) -and $requestedEffort -ne 'medium') {
            $script:dispatchDecision = 'Astra role dispatch denied because its reasoning effort is fixed to medium.'
            return
        }
        $script:dispatchDecision = Test-AndConsumeAllowance -State $state -Mode $mode -TurnId $turnId -Role ([string]$request.role)
        if ($null -eq $script:dispatchDecision) {
            $state.pendingAstra = [ordered]@{
                toolUseId = [string]$payload.tool_use_id
                action = [string]$request.action
                role = [string]$request.role
                taskName = [string]$request.target
                turnId = $turnId
            }
            Write-State -Path $statePath -State $state
        }
    }
    if ($null -ne $script:dispatchDecision) {
        New-DenyOutput -Reason $script:dispatchDecision
    }
    exit 0
}

if ($eventName -eq 'SubagentStart' -and $astraRoles -contains [string]$payload.agent_type) {
    $script:startContext = $null
    Invoke-WithStateLock -StatePath $statePath -Action {
        $state = Read-State -Path $statePath -SessionId $sessionId
        if ($state -eq $false -or $null -eq $state) {
            $script:startContext = 'Astra started without valid routing state. Return one read-only response and do not continue or delegate.'
            return
        }
        $pending = $state.pendingAstra
        $taskName = if ($null -ne $pending) { [string]$pending.taskName } else { '' }
        $known = @($state.knownAstraAgents | Where-Object { [string]$_.agentId -ne [string]$payload.agent_id })
        $known += [ordered]@{
            agentId = [string]$payload.agent_id
            taskName = $taskName
            role = [string]$payload.agent_type
        }
        $state.knownAstraAgents = $known
        $state.activeAstra = [ordered]@{
            agentId = [string]$payload.agent_id
            taskName = $taskName
            role = [string]$payload.agent_type
        }
        $unreserved = ($null -eq $pending -or [string]$pending.role -ne [string]$payload.agent_type)
        if ($unreserved) {
            $state.automaticRemaining = 0
            $state.manualGrant = $null
        }
        $state.pendingAstra = $null
        Write-State -Path $statePath -State $state
        $script:startContext = Get-PolicyContext -Mode $mode -State $state -SessionId $sessionId -TurnId $turnId
        if ($unreserved) {
            $script:startContext += "`nThis Astra start was not matched to a guard reservation. Return one read-only response and report the routing validation gap."
        }
    }
    New-ContextOutput -EventName 'SubagentStart' -Context $script:startContext
    exit 0
}

if ($eventName -eq 'SubagentStop' -and $astraRoles -contains [string]$payload.agent_type) {
    Invoke-WithStateLock -StatePath $statePath -Action {
        $state = Read-State -Path $statePath -SessionId $sessionId
        if ($state -eq $false -or $null -eq $state) {
            return
        }
        if ($null -ne $state.activeAstra -and [string]$state.activeAstra.agentId -eq [string]$payload.agent_id) {
            $state.activeAstra = $null
        }
        if ($null -ne $state.pendingAstra -and [string]$state.pendingAstra.action -eq 'followup') {
            $pendingTarget = [string]$state.pendingAstra.taskName
            $known = @($state.knownAstraAgents | Where-Object { [string]$_.agentId -eq [string]$payload.agent_id }) | Select-Object -First 1
            $knownTaskName = if ($null -ne $known) { [string]$known.taskName } else { '' }
            $matchesTaskName = $pendingTarget -eq $knownTaskName -or (-not [string]::IsNullOrWhiteSpace($knownTaskName) -and $pendingTarget.EndsWith("/$knownTaskName", [System.StringComparison]::Ordinal))
            if ($pendingTarget -eq [string]$payload.agent_id -or $matchesTaskName) {
                $state.pendingAstra = $null
            }
        }
        Write-State -Path $statePath -State $state
    }
    exit 0
}

exit 0
