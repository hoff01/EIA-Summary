Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "windows_common.ps1")

$Root = Get-ProjectRoot
Set-Location $Root
Import-ProjectEnvironment

$ExitCode = Invoke-ProjectPython @("run_release_gate.py", "--refresh-schedule-only", "--force-schedule-refresh")
if ($ExitCode -ne 0) {
    throw "run_release_gate.py failed with exit code $ExitCode"
}
