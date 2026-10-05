param(
    [string]$TemporaryRoot = [System.IO.Path]::GetTempPath()
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows) {
    throw 'This test requires Windows.'
}

function Invoke-HookCommand {
    param($Hook, [string]$Shell, [string]$InputJson, [string]$ProfilePath, $CodexPath)

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    # Preserve output bytes for comparison regardless of the hidden shell's console code page.
    $startInfo.StandardOutputEncoding = [System.Text.Encoding]::Latin1
    $startInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $startInfo.Environment['USERPROFILE'] = $ProfilePath
    $startInfo.Environment.Remove('CODEX_HOME') | Out-Null
    if ($null -ne $CodexPath) {
        $startInfo.Environment['CODEX_HOME'] = $CodexPath
    }
    if ($Shell -eq 'cmd') {
        $startInfo.FileName = $env:COMSPEC
        $startInfo.Arguments = '/d /s /c "' + $Hook.commandWindows + '"'
    } else {
        $startInfo.FileName = (Get-Command pwsh).Source
        $startInfo.ArgumentList.Add('-NoProfile')
        $startInfo.ArgumentList.Add('-Command')
        $startInfo.ArgumentList.Add($Hook.commandWindows)
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        $process.Start() | Out-Null
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.Write($InputJson)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit($Hook.timeout * 1000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "Hook timed out through $Shell after $($Hook.timeout)s."
        }
        $output = $stdout.GetAwaiter().GetResult()
        $errors = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0 -or -not [string]::IsNullOrWhiteSpace($errors)) {
            throw "Hook failed through $Shell (exit $($process.ExitCode)): $errors"
        }
        return $output
    } finally {
        $process.Dispose()
    }
}

$repositoryRoot = Split-Path $PSScriptRoot -Parent
$hooks = (Get-Content -LiteralPath (Join-Path $repositoryRoot 'hooks.json') -Raw | ConvertFrom-Json -AsHashtable).hooks
$testRoot = Join-Path ([System.IO.Path]::GetFullPath($TemporaryRoot)) ('windows-hook-test-' + [guid]::NewGuid())
$profilePath = Join-Path $testRoot 'user profile'
$defaultCodexPath = Join-Path $profilePath '.codex'
$configuredCodexPath = Join-Path $testRoot 'configured codex home'
$checks = 0
try {
    foreach ($fixture in @($defaultCodexPath, $configuredCodexPath)) {
        $hookDirectory = Join-Path $fixture 'hooks'
        New-Item -ItemType Directory -Path $hookDirectory -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'implementation-restraint.ps1'), (Join-Path $PSScriptRoot 'subagent-fork-default.ps1') -Destination $hookDirectory
    }
    $directHook = @{
        commandWindows = 'pwsh -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'implementation-restraint.ps1') + '"'
        timeout = 5
    }
    $allowedInput = @{
        hook_event_name = 'PreToolUse'
        tool_name = 'spawn_agent'
        model = 'gpt-6.1-sol'
        tool_input = @{ agent_type = 'general_sol'; fork_turns = 'all'; message = 'safe input'; task_name = 'hook_test' }
    }
    foreach ($shell in @('cmd', 'pwsh')) {
        $expectedContext = Invoke-HookCommand $directHook $shell '{}' $profilePath $configuredCodexPath
        if (-not $expectedContext.StartsWith('Implementation restraint / delegation:')) {
            throw "Direct script invocation did not return context through $shell."
        }
        foreach ($codexPath in @($null, '', ' ', $configuredCodexPath)) {
            foreach ($eventName in @('UserPromptSubmit', 'SubagentStart', 'SessionStart', 'PreToolUse')) {
                $hook = $hooks[$eventName][0].hooks[0]
                $inputJson = if ($eventName -eq 'PreToolUse') { $allowedInput | ConvertTo-Json -Depth 10 -Compress } else { '{}' }
                $output = Invoke-HookCommand $hook $shell $inputJson $profilePath $codexPath
                if ($eventName -eq 'PreToolUse') {
                    $decision = ($output | ConvertFrom-Json -AsHashtable).hookSpecificOutput
                    $expectedArguments = $allowedInput.tool_input.Clone()
                    $expectedArguments.fork_turns = 'none'
                    $actualArguments = $decision.updatedInput
                    if ($decision.hookEventName -ne 'PreToolUse' -or $decision.permissionDecision -ne 'allow' -or
                        $actualArguments.Count -ne $expectedArguments.Count) {
                        throw "Invalid PreToolUse allow output through $shell."
                    }
                    foreach ($key in $expectedArguments.Keys) {
                        if ($actualArguments[$key] -cne $expectedArguments[$key]) {
                            throw "PreToolUse did not preserve $key through $shell."
                        }
                    }
                } elseif (-not [string]::Equals($output, $expectedContext, [System.StringComparison]::Ordinal)) {
                    throw "$eventName did not return the expected context through $shell."
                }
                $checks++
            }
        }
        foreach ($case in @(
            @{ Parent = 'gpt-6.1-sol'; Tool = 'Agent'; Arguments = @{ model = 'gpt-6.1-sol'; fork_turns = 'all' }; Decision = 'allow' },
            @{ Parent = 'gpt-6.1-sol'; Tool = 'spawn_agent'; Arguments = @{ model = 'gpt-6-luna' }; Decision = 'allow' },
            @{ Parent = 'gpt-6.1-sol'; Tool = 'spawn_agent'; Arguments = @{ model = 'gpt-6-astra' }; Decision = 'allow' },
            @{ Parent = 'gpt-6.1-sol'; Tool = 'spawn_agent'; Arguments = @{ model = 'gpt-5.6-sol' }; Decision = 'deny' },
            @{ Parent = 'gpt-6-astra'; Tool = 'spawn_agent'; Arguments = @{ agent_type = 'general_astra' }; Decision = 'deny' },
            @{ Parent = 'gpt-6-astra'; Tool = 'spawn_agent'; Arguments = @{ model = 'gpt-6-astra' }; Decision = 'deny' },
            @{ Parent = 'gpt-6-astra'; Tool = 'spawn_agent'; Arguments = @{ model = 'gpt-6.1-sol' }; Decision = 'allow' }
        )) {
            $inputJson = @{ hook_event_name = 'PreToolUse'; tool_name = $case.Tool; model = $case.Parent; tool_input = $case.Arguments } | ConvertTo-Json -Depth 10 -Compress
            $output = Invoke-HookCommand $hooks.PreToolUse[0].hooks[0] $shell $inputJson $profilePath $configuredCodexPath
            $decision = ($output | ConvertFrom-Json -AsHashtable).hookSpecificOutput
            if ($decision.permissionDecision -ne $case.Decision -or
                ($case.Decision -eq 'allow' -and $decision.updatedInput.fork_turns -ne 'none') -or
                ($case.Decision -eq 'deny' -and $decision.ContainsKey('updatedInput'))) {
                throw "Invalid model/fork_turns decision through $shell."
            }
            $checks++
        }
    }
    Write-Output "Windows hook launch checks passed: $checks"
} finally {
    $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
    $resolvedParent = [System.IO.Path]::GetFullPath($TemporaryRoot).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolvedTestRoot.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to remove a test directory outside TemporaryRoot.'
    }
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
