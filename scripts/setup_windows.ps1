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
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed"
}

& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "requirements installation failed"
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
if (
    -not (Test-Path (Join-Path $Root "email_recipients.txt")) -and
    (Test-Path (Join-Path $Root "email_recipients.example.txt"))
) {
    Copy-Item (Join-Path $Root "email_recipients.example.txt") (Join-Path $Root "email_recipients.txt")
}

Write-Host "Setup complete for $DisplayName."
Write-Host "Next steps:"
Write-Host "1. Review $Root\\email_recipients.txt"
Write-Host "2. Confirm desktop Outlook is installed, signed in, and able to send from this Windows user"
Write-Host "3. Run scripts\\build_latest.bat for a validation build"
Write-Host "4. Run RUN_EIA_SUMMARY_DASHBOARD.bat on release morning, or scripts\\install_windows_task.bat to install the $DailyTaskTimeEastern Eastern release gate task ($DailyTaskTimeLocal local on this computer)"
Write-Host "5. Optional: run scripts\\send_test_email.bat for a live Outlook email test"
Write-Host "6. Optional: run scripts\\refresh_release_schedule.bat to cache the current EIA release calendar"
