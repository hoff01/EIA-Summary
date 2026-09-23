param([switch]$IfNeeded)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "windows_common.ps1")

$Root = Get-ProjectRoot
$Config = Get-ProjectConfig
$DisplayName = $Config["PROJECT_DISPLAY_NAME"]
if (-not $DisplayName) {
    $DisplayName = "EIA Summary Dashboard"
}
$DailyTaskTimeEastern = Get-WindowsTaskScheduleTimeEastern
$DailyTaskTimeLocal = Get-WindowsTaskScheduleTimeLocal

$VenvPython = New-ProjectVenvIfMissing
$HashAlgorithm = [System.Security.Cryptography.SHA256]::Create()
try {
    $RequirementsHash = [BitConverter]::ToString($HashAlgorithm.ComputeHash(
        [System.IO.File]::ReadAllBytes((Join-Path $Root "requirements.txt"))
    )).Replace('-', '')
} finally {
    $HashAlgorithm.Dispose()
}
$RequirementsStamp = Join-Path $Root ".venv\.requirements.sha256"
if ($IfNeeded -and (Test-Path -LiteralPath $RequirementsStamp)) {
    if ((Get-Content -LiteralPath $RequirementsStamp -Raw).Trim() -eq $RequirementsHash) {
        Write-Host "EIA Summary environment is ready."
        exit 0
    }
}
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed"
}

& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "requirements installation failed"
}
$RequirementsHash | Set-Content -LiteralPath $RequirementsStamp -Encoding ascii

New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
if (
    -not (Test-Path (Join-Path $Root "email_recipients.txt")) -and
    (Test-Path (Join-Path $Root "email_recipients.example.txt"))
) {
    Copy-Item (Join-Path $Root "email_recipients.example.txt") (Join-Path $Root "email_recipients.txt")
}

Write-Host "Setup complete for $DisplayName."
Write-Host "Next steps:"
Write-Host "1. Confirm classic desktop Outlook is installed and signed in."
Write-Host "2. RUN_EIA_SUMMARY_DASHBOARD.bat handles the release workflow and asks for recipients once."
Write-Host "3. Optional preview without email: scripts\build_latest.bat"
Write-Host "4. Optional scheduled task: scripts\install_windows_task.bat ($DailyTaskTimeEastern Eastern; $DailyTaskTimeLocal local)"
