Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "windows_common.ps1")

$Root = Get-ProjectRoot
Import-ProjectEnvironment
$ExitCode = Invoke-ProjectPython @("build.py", "--refresh-eia-latest", "--week", "latest", "--validate", "--skip-email")
if ($ExitCode -ne 0) {
    throw "build.py failed with exit code $ExitCode"
}

Write-Host "Build complete. Latest PDF: $Root\output\latest.pdf"
