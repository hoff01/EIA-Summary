param(
    [switch]$ForceSend,
    [int]$PollSeconds = 0,
    [int]$MaxWaitMinutes = 0,
    [switch]$NoWait,
    [switch]$ShowDecision
)

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
$LogPath = Join-Path $LogDir "daily_release_gate_windows.log"
$SendStatePath = Join-Path $LogDir "last_successful_outlook_send.json"

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

function Get-EmailRecipients {
    $recipientsPath = Join-Path $Root "email_recipients.txt"
    if (-not (Test-Path $recipientsPath)) {
        throw "Recipients file not found at $recipientsPath"
    }
    $recipients = Get-Content $recipientsPath |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") }
    if (-not $recipients -or $recipients.Count -eq 0) {
        throw "No recipients found in $recipientsPath"
    }
    return @($recipients)
}

function Get-RecipientFingerprint {
    param([string[]]$Recipients)

    $normalized = ($Recipients |
        ForEach-Object { $_.Trim().ToLowerInvariant() } |
        Where-Object { $_ } |
        Sort-Object) -join "`n"
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($normalized)
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Get-LastSuccessfulSend {
    if (-not (Test-Path $SendStatePath)) {
        return $null
    }
    try {
        return Get-Content $SendStatePath -Raw | ConvertFrom-Json
    } catch {
        Write-Log "ignoring unreadable send state file: $_"
        return $null
    }
}

function Save-LastSuccessfulSend {
    param(
        [string]$Week,
        [string]$Fingerprint,
        [string[]]$Recipients
    )

    $payload = [ordered]@{
        week_ending = $Week
        recipient_fingerprint = $Fingerprint
        recipients = $Recipients
        sent_at_local = (Get-Date).ToString("o")
        task_name = $TaskName
    }
    $payload | ConvertTo-Json -Depth 4 | Out-File -FilePath $SendStatePath -Encoding utf8
}

function Send-LatestOutlookMail {
    param(
        [string]$ExpectedWeek,
        [switch]$ForceEmail
    )

    $sendArgs = @(
        "build.py",
        "--week",
        $ExpectedWeek,
        "--send-email",
        "--email-mode",
        "outlook"
    )
    if ($ForceEmail) {
        $sendArgs += "--force-email"
    }

    $result = Invoke-ProjectPythonOutput $sendArgs
    $result.Lines | ForEach-Object { $_ | Out-File -FilePath $LogPath -Append -Encoding utf8 }
    if ($result.ExitCode -ne 0) {
        throw "build.py Outlook send failed with exit code $($result.ExitCode)"
    }

    $validatedWeek = Get-OutputField -Lines $result.Lines -Name "validated_week"
    if ($validatedWeek -ne $ExpectedWeek) {
        throw "validated week '$validatedWeek' did not match release gate week '$ExpectedWeek'"
    }
    $sentMode = Get-OutputField -Lines $result.Lines -Name "email_sent_mode"
    if ($sentMode -eq "skipped_duplicate") {
        Write-Log "build.py skipped duplicate email for $ExpectedWeek"
        return $sentMode
    }
    if ($sentMode -ne "outlook") {
        throw "expected Outlook email mode, got '$sentMode'"
    }

    Write-Log "sent $TaskName email for $validatedWeek through Outlook"
    return $sentMode
}

Set-Location $Root
Import-ProjectEnvironment
Write-Log "starting daily release gate"

$GateArgs = @("run_release_gate.py")
if ($PollSeconds -gt 0) {
    $GateArgs += @("--poll-seconds", [string]$PollSeconds)
}
if ($MaxWaitMinutes -gt 0) {
    $GateArgs += @("--max-wait-minutes", [string]$MaxWaitMinutes)
}
if ($NoWait) {
    $GateArgs += "--no-wait"
}
if ($ShowDecision) {
    $GateArgs += "--show-decision"
}

$GateResult = Invoke-ProjectPythonOutput $GateArgs
$GateResult.Lines | ForEach-Object {
    $_ | Out-File -FilePath $LogPath -Append -Encoding utf8
}

if ($GateResult.ExitCode -ne 0) {
    throw "run_release_gate.py failed with exit code $($GateResult.ExitCode)"
}

$Action = Get-OutputField -Lines $GateResult.Lines -Name "release_gate_action"
if (-not $Action) {
    throw "run_release_gate.py did not emit release_gate_action"
}

if ($Action -eq "skip") {
    Write-Log "daily release gate skipped because today is not an EIA release day"
    return
}
if ($Action -ne "ready") {
    Write-Log "daily release gate finished with action '$Action'"
    return
}

$ReadyWeek = Get-OutputField -Lines $GateResult.Lines -Name "release_gate_ready_week"
if (-not $ReadyWeek) {
    throw "release gate did not emit release_gate_ready_week"
}

$Recipients = Get-EmailRecipients
$RecipientFingerprint = Get-RecipientFingerprint -Recipients $Recipients
$LastSend = Get-LastSuccessfulSend
if (
    -not $ForceSend -and
    $LastSend -and
    $LastSend.week_ending -eq $ReadyWeek -and
    $LastSend.recipient_fingerprint -eq $RecipientFingerprint
) {
    Write-Log "skipping Outlook send for $ReadyWeek because this recipient set was already sent"
    return
}

$SendMode = Send-LatestOutlookMail -ExpectedWeek $ReadyWeek -ForceEmail:$ForceSend
if ($SendMode -eq "outlook") {
    Save-LastSuccessfulSend -Week $ReadyWeek -Fingerprint $RecipientFingerprint -Recipients $Recipients
}
Write-Log "completed daily release gate"
