[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$RolloutPath,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputPath,

    [switch]$Force
)

$resolvedRolloutPath = (Resolve-Path -LiteralPath $RolloutPath -ErrorAction Stop).Path
$firstLine = Get-Content -LiteralPath $resolvedRolloutPath -TotalCount 1 -ErrorAction Stop

try {
    $record = $firstLine | ConvertFrom-Json -ErrorAction Stop
}
catch {
    throw "The first rollout record is not valid JSON: $resolvedRolloutPath"
}

if ($record.type -ne 'session_meta') {
    throw "The rollout does not start with a session_meta record: $resolvedRolloutPath"
}

$prompt = [string]$record.payload.base_instructions.text
if ([string]::IsNullOrWhiteSpace($prompt)) {
    throw "The rollout does not contain payload.base_instructions.text: $resolvedRolloutPath"
}

$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
if ((Test-Path -LiteralPath $resolvedOutputPath) -and -not $Force) {
    throw "Output already exists. Pass -Force to replace it: $resolvedOutputPath"
}

$outputDirectory = Split-Path -Parent $resolvedOutputPath
if ($outputDirectory -and -not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($resolvedOutputPath, $prompt, $utf8WithoutBom)

[pscustomobject]@{
    source = $resolvedRolloutPath
    output = $resolvedOutputPath
    characters = $prompt.Length
} | Format-List
