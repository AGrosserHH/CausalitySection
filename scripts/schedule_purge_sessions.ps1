<#
.SYNOPSIS
Registers a Windows Task Scheduler job that removes expired aitiolin sessions.

.DESCRIPTION
Runs "python manage.py purge_sessions" from the repository's virtual environment every hour by
default, with the working directory set to aitiolin/causalproject so the backend .env is found.
Running the script again updates the existing task. The task runs only while you are logged on,
and it catches up after a missed slot, for example when the machine was off.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\schedule_purge_sessions.ps1

.EXAMPLE
Unregister-ScheduledTask -TaskName "aitiolin purge_sessions" -Confirm:$false
#>
param(
    [string]$TaskName = "aitiolin purge_sessions",
    [int]$EveryMinutes = 60
)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$workdir = Join-Path $root "aitiolin\causalproject"
if (-not (Test-Path $python)) { throw "Python virtual environment not found: $python" }
if (-not (Test-Path (Join-Path $workdir "manage.py"))) { throw "manage.py not found in $workdir" }

$action = New-ScheduledTaskAction -Execute $python -Argument "manage.py purge_sessions" -WorkingDirectory $workdir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$description = "Removes expired aitiolin prototype sessions and their server files (see aitiolin/README.md, Retention and cleanup)."

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $description -Force | Out-Null
Write-Host "Registered task '$TaskName': every $EveryMinutes minutes, $python manage.py purge_sessions (in $workdir)"
