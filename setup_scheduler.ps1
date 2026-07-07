<#
Registers a Windows Scheduled Task that runs Centellian24_US_Monitor's weekly
collection (scripts/run_weekly.py via run_weekly.bat) every Sunday at 06:17
local system time (see PRD_rev.md §7 for the 06:17 KST rationale).

Run this ONCE from an elevated ("Run as Administrator") PowerShell prompt,
from the project root (or anywhere — it resolves paths relative to this
script's own location).
#>

$ErrorActionPreference = "Stop"

$TaskName    = "Centellian24_US_Monitor_Weekly"
$ProjectRoot = $PSScriptRoot
$BatchPath   = Join-Path $ProjectRoot "run_weekly.bat"

if (-not (Test-Path $BatchPath)) {
    throw "run_weekly.bat not found at $BatchPath -- run this script from the project root."
}

$tz = Get-TimeZone
if ($tz.Id -ne "Korea Standard Time") {
    Write-Warning "Local system time zone is '$($tz.Id)', not 'Korea Standard Time'. The 06:17 trigger below fires at 06:17 LOCAL time, not 06:17 KST -- adjust the -At value in this script if you need it to line up with actual KST."
}

$Action = New-ScheduledTaskAction -Execute $BatchPath -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "06:17"

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Task '$TaskName' already exists -- unregistering old version first."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Centellian24 US Monitor: weekly Amazon/Trends/Gemini/Qoo10 collection + git push (see PRD_rev.md section 7)." `
    | Out-Null

Write-Host ""
Write-Host "Registered scheduled task '$TaskName'."
Write-Host "It runs every Sunday at 06:17 (local system time)."
Write-Host "'Run task as soon as possible after a scheduled start is missed' is enabled (-StartWhenAvailable), so if the PC was off or asleep at 06:17, it will run once the PC is back on (still requires you to be logged in -- see note below)."
Write-Host ""
Write-Host "Verify registration:"
Write-Host "  schtasks /query /tn `"$TaskName`" /v /fo list"
Write-Host ""
Write-Host "NOTE on git push authentication:"
Write-Host "  This task runs with LogonType=Interactive, meaning it only fires while you are logged into an interactive Windows session -- not a fully unattended background run while logged out. This is intentional: SSH keys / 'gh auth' tokens are normally only accessible from your own interactive session, and switching to an unattended logon type (S4U or a stored password) risks 'git push' failing silently because it can't reach your credentials."
Write-Host "  Before relying on this, confirm 'git push' works with zero prompts when run manually from a plain terminal (no cached SSH agent password prompt, no 'gh auth login' re-prompt)."
Write-Host ""
Write-Host "Optional: register scripts/check_missed_run.py to run at login (Windows Startup) so you notice a skipped week promptly:"
Write-Host "  See the '실행 누락 대응' section in README.md."
