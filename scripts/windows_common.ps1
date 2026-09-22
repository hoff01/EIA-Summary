Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Import-KeyValueFile {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }

    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $pair = $trimmed -split "=", 2
        if ($pair.Count -ne 2) {
            continue
        }
        $key = $pair[0].Trim()
        $value = $pair[1].Trim()
        if (
            (($value.StartsWith('"')) -and $value.EndsWith('"')) -or
            (($value.StartsWith("'")) -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$key] = $value
    }

    return $values
}

function Get-ProjectConfig {
    $root = Get-ProjectRoot
    return Import-KeyValueFile (Join-Path $root "project.env")
}

function Import-ProjectEnvironment {
    $root = Get-ProjectRoot
    foreach ($path in @((Join-Path $root "project.env"), (Join-Path $root ".env"))) {
        $entries = Import-KeyValueFile $path
        foreach ($entry in $entries.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value)
        }
    }
}

function Get-EasternTimeZone {
    try {
        return [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    } catch {
        return [System.TimeZoneInfo]::FindSystemTimeZoneById("America/New_York")
    }
}

function Convert-EasternClockToLocalTaskTime {
    param([string]$ClockText)

    $culture = [System.Globalization.CultureInfo]::InvariantCulture
    $parsed = [datetime]::Parse($ClockText, $culture)
    $today = Get-Date
    $easternClock = [datetime]::SpecifyKind(
        [datetime]::new($today.Year, $today.Month, $today.Day, $parsed.Hour, $parsed.Minute, 0),
        [System.DateTimeKind]::Unspecified
    )
    $easternZone = Get-EasternTimeZone
    $utcClock = [System.TimeZoneInfo]::ConvertTimeToUtc($easternClock, $easternZone)
    $localClock = [System.TimeZoneInfo]::ConvertTimeFromUtc($utcClock, [System.TimeZoneInfo]::Local)
    return $localClock.ToString("h:mmtt", $culture).ToLowerInvariant()
}

function Get-WindowsTaskScheduleTimeLocal {
    $config = Get-ProjectConfig
    $localTime = $config["WINDOWS_TASK_SCHEDULE_TIME_LOCAL"]
    if ($localTime) {
        return $localTime
    }

    $easternTime = $config["WINDOWS_TASK_SCHEDULE_TIME_EASTERN"]
    if (-not $easternTime) {
        $easternTime = $config["RELEASE_MONITOR_START_ET"]
    }
    if (-not $easternTime) {
        $easternTime = "10:28"
    }
    return Convert-EasternClockToLocalTaskTime $easternTime
}

function Get-WindowsTaskScheduleTimeEastern {
    $config = Get-ProjectConfig
    $easternTime = $config["WINDOWS_TASK_SCHEDULE_TIME_EASTERN"]
    if (-not $easternTime) {
        $easternTime = $config["RELEASE_MONITOR_START_ET"]
    }
    if (-not $easternTime) {
        $easternTime = "10:28"
    }
    return $easternTime
}

function Invoke-ProjectPython {
    param([string[]]$Arguments)

    $pythonCommand = Get-ProjectPythonCommand
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($pythonCommand -eq "py") {
            $output = & py -3 @Arguments 2>&1
        } else {
            $output = & $pythonCommand @Arguments 2>&1
        }
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $output | ForEach-Object { Write-Host $_ }
    return $exitCode
}

function Invoke-ProjectPythonOutput {
    param([string[]]$Arguments)

    $pythonCommand = Get-ProjectPythonCommand
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($pythonCommand -eq "py") {
            $output = & py -3 @Arguments 2>&1
        } else {
            $output = & $pythonCommand @Arguments 2>&1
        }
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Lines = @($output | ForEach-Object { [string]$_ })
    }
}

function Get-ProjectPythonCommand {
    $root = Get-ProjectRoot
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return "py"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    throw "Python was not found. Run scripts\\setup_windows.ps1 after installing Python 3.11+."
}

function New-ProjectVenvIfMissing {
    $root = Get-ProjectRoot
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $venvDir = Join-Path $root ".venv"
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        & py -3 -m venv $venvDir
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create the virtual environment with py -3."
        }
    } else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) {
            throw "Python was not found. Install Python 3.11+ and rerun scripts\\setup_windows.ps1."
        }
        & python -m venv $venvDir
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create the virtual environment with python -m venv."
        }
    }

    return $venvPython
}
