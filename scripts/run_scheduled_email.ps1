Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "windows_common.ps1")

$Root = Get-ProjectRoot
$Config = Get-ProjectConfig
$TaskName = $Config["WINDOWS_TASK_NAME"]
if (-not $TaskName) {
    $TaskName = "EIA Summary Dashboard"
}
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir "scheduled_email_windows.log"

function Write-Log {
    param([string]$Message)
    "[$(Get-Date -Format o)] $Message" | Out-File -FilePath $LogPath -Append -Encoding utf8
}

function Get-OutputField {
    param(
        [string[]]$Lines,
        [string]$Name
    )

    $line = $Lines | Where-Object { $_ -like "$Name=*" } | Select-Object -Last 1
    if (-not $line) {
        return $null
    }
    return ($line -split "=", 2)[1]
}

Set-Location $Root
Import-ProjectEnvironment
Write-Log "starting DOE summary dashboard email"

$result = Invoke-ProjectPythonOutput @(
    "build.py",
    "--refresh-eia-latest",
    "--week",
    "latest",
    "--send-email",
    "--email-mode",
    "outlook"
)
$result.Lines | ForEach-Object { $_ | Out-File -FilePath $LogPath -Append -Encoding utf8 }
if ($result.ExitCode -ne 0) {
    throw "build.py Outlook send failed with exit code $($result.ExitCode)"
}

$week = Get-OutputField -Lines $result.Lines -Name "validated_week"
$sentMode = Get-OutputField -Lines $result.Lines -Name "email_sent_mode"
if ($sentMode -eq "skipped_duplicate") {
    Write-Log "skipped duplicate $TaskName email for $week"
    return
}
if ($sentMode -ne "outlook") {
    throw "expected Outlook email mode, got '$sentMode'"
}

Write-Log "sent $TaskName email for $week through Outlook"
