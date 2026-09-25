param(
    [switch]$ForceSend,
    [int]$PollSeconds = 0,
    [int]$MaxWaitMinutes = 0,
    [switch]$NoWait,
    [switch]$ShowDecision,
    [switch]$Latest,
    [switch]$NoEmail,
    [switch]$ConfigureRecipients
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
    Write-Host $Message
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
    $recipients = @(Get-Content $recipientsPath |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") })
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

function Initialize-EmailRecipients {
    $path = Join-Path $Root "email_recipients.txt"
    if (Test-Path -LiteralPath $path) {
        $existing = @(Get-Content -LiteralPath $path | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith("#") })
        if ($existing.Count -gt 0) { return }
    }
    $entered = Read-Host "First run: enter recipient email addresses separated by commas or semicolons"
    $addresses = @($entered -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($addresses.Count -eq 0) { throw "No recipients entered. Rerun the launcher to configure email." }
    foreach ($address in $addresses) {
        try {
            $parsed = [System.Net.Mail.MailAddress]::new($address)
            if ($parsed.Address -ne $address -or -not $address.Contains('@')) { throw "Invalid address" }
        } catch {
            throw "Invalid recipient address. Rerun the launcher and enter email addresses only."
        }
    }
    [System.IO.File]::WriteAllLines($path, [string[]]$addresses, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Recipients saved locally. This file is excluded from Git."
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
    $result.Lines | ForEach-Object {
        Write-Host $_
        $_ | Out-File -FilePath $LogPath -Append -Encoding utf8
    }
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
if (-not $ShowDecision -and -not $NoEmail) {
    if ($ConfigureRecipients) { Initialize-EmailRecipients }
    $Recipients = @(Get-EmailRecipients)
}
Write-Log "starting daily release gate"

$GateArgs = @("run_release_gate.py")
if ($Latest) {
    $GateArgs += "--latest"
}
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
    Write-Host $_
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

if ($NoEmail) {
    $BuildExitCode = Invoke-ProjectPython @("build.py", "--week", $ReadyWeek, "--validate", "--skip-email")
    if ($BuildExitCode -ne 0) { throw "Latest summary build failed with exit code $BuildExitCode" }
    Write-Log "Built latest summary for $ReadyWeek without email."
    return
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
