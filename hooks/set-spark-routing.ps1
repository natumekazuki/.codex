#!/usr/bin/env pwsh

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('spark-first', 'balanced', 'standard-only')]
    [string]$Mode,

    [string]$StatePath = (Join-Path $PSScriptRoot 'subagent-routing.local.json')
)

$ErrorActionPreference = 'Stop'

$state = [ordered]@{
    sparkMode = $Mode
    updatedAt = (Get-Date).ToUniversalTime().ToString('o')
}

$state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StatePath -Encoding UTF8
Write-Host "Spark routing mode set to $Mode"
