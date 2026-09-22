Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "windows_common.ps1")

$Root = Get-ProjectRoot
$Config = Get-ProjectConfig
$TaskName = $Config["WINDOWS_TASK_NAME"]
if (-not $TaskName) {
    $TaskName = "EIA Summary Dashboard"
}
$DisplayName = $Config["PROJECT_DISPLAY_NAME"]
if (-not $DisplayName) {
    $DisplayName = "EIA Summary Dashboard"
}
$DailyTaskTimeEastern = Get-WindowsTaskScheduleTimeEastern
$DailyTaskTime = Get-WindowsTaskScheduleTimeLocal
$Runner = Join-Path $Root "scripts\run_daily_release_gate.ps1"

if (-not (Test-Path $Runner)) {
    throw "Runner not found at $Runner"
}

& (Join-Path $PSScriptRoot "setup_windows.ps1")

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" `
    -WorkingDirectory $Root

$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyTaskTime
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel LeastPrivilege
$Settings = New-ScheduledTaskSettingsSet -Compatibility Win8 -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Runs the once-daily EIA release gate for $DisplayName, using Eastern release times from the official EIA schedule." `
    -Force | Out-Null

Write-Host "Installed scheduled task '$TaskName' to run daily at $DailyTaskTime local time."
Write-Host "Configured release gate start: $DailyTaskTimeEastern New York/Eastern time."
Write-Host "The runner uses the EIA release schedule in Eastern time and exits immediately on non-release days."
Write-Host "On release days it waits until the official release time, polls every few seconds for up to two minutes, then sends through Outlook as soon as the expected week is live."
Write-Host "Duplicate Outlook sends are skipped for the same week and recipient list."
Write-Host "Recipients are read from: $Root\email_recipients.txt"
Write-Host "Manual release run: $Root\RUN_EIA_SUMMARY_DASHBOARD.bat"
