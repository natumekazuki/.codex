#!/usr/bin/env pwsh

[CmdletBinding(DefaultParameterSetName = 'Mode')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Mode')]
    [ValidateSet('conditional', 'manual', 'off')]
    [string]$Mode,

    [Parameter(Mandatory = $true, ParameterSetName = 'Grant')]
    [string]$SessionId,

    [Parameter(Mandatory = $true, ParameterSetName = 'Grant')]
    [string]$TurnId,

    [Parameter(ParameterSetName = 'Grant')]
    [ValidateSet('astra_consultant', 'astra_reviewer')]
    [string[]]$Role = @('astra_consultant', 'astra_reviewer'),

    [Parameter(ParameterSetName = 'Grant')]
    [ValidateRange(1, 2147483647)]
    [int]$Count = 1,

    [string]$ConfigPath = (Join-Path $PSScriptRoot 'astra-routing.local.json'),

    [string]$StateDirectory = (Join-Path $PSScriptRoot '.astra-routing-state')
)

$ErrorActionPreference = 'Stop'
$stateVersion = 2

function Get-Sha256Text {
    param([string]$Text)

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $hash = [System.Security.Cryptography.SHA256]::HashData($bytes)
    return [Convert]::ToHexString($hash).ToLowerInvariant()
}

function Write-JsonAtomically {
    param([string]$Path, $Value)

    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporaryPath = Join-Path $directory ".$([System.IO.Path]::GetFileName($Path)).$([guid]::NewGuid().ToString('N')).tmp"
    try {
        $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporaryPath -Encoding UTF8
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

if ($PSCmdlet.ParameterSetName -eq 'Mode') {
    $config = [ordered]@{
        version = 1
        mode = $Mode
        updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    }
    Write-JsonAtomically -Path $ConfigPath -Value $config
    Write-Host "Astra routing mode set to $Mode"
    exit 0
}

$statePath = Join-Path $StateDirectory "$(Get-Sha256Text -Text $SessionId).json"
if (-not (Test-Path -LiteralPath $statePath)) {
    throw 'Astra routing state does not exist for the requested session. Submit a user prompt in that session first.'
}

Invoke-WithStateLock -StatePath $statePath -Action {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ([int]$state.version -ne $stateVersion -or [string]$state.sessionId -ne $SessionId) {
        throw 'Astra routing state identity is invalid.'
    }
    if ([string]$state.currentTurnId -ne $TurnId) {
        throw 'The requested turn is not the current recorded user turn.'
    }

    $state.manualGrant = [ordered]@{
        turnId = $TurnId
        roles = @($Role)
        remaining = $Count
        updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    }
    $state.updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    Write-JsonAtomically -Path $statePath -Value $state
}
Write-Host "Granted $Count manual Astra dispatch(es) for $($Role -join ', ') in the requested turn"
