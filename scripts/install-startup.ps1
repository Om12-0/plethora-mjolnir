# Register PLETHORA MJOLNIR to start the watcher at logon (Task Scheduler).
# Falls back to a Startup-folder shortcut if task registration is not permitted.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here

$venvPy = Join-Path $root ".venv\Scripts\pythonw.exe"
$pythonw = if (Test-Path $venvPy) { $venvPy } else { "pythonw" }
$taskName = "PlethoraMjolnir"

try {
    $action = New-ScheduledTaskAction -Execute $pythonw `
        -Argument "-X utf8 `"$(Join-Path $root 'mj.py')`" watch" `
        -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Description "PLETHORA MJOLNIR background file indexer" -Force | Out-Null
    Write-Host "Scheduled task '$taskName' registered (runs at logon)." -ForegroundColor Green
    Write-Host "Remove later with: .\scripts\uninstall-startup.ps1"
}
catch {
    Write-Host "Task registration failed ($($_.Exception.Message))." -ForegroundColor Yellow
    Write-Host "Falling back to a Startup-folder shortcut ..."
    $startup = [Environment]::GetFolderPath("Startup")
    $lnk = Join-Path $startup "PLETHORA MJOLNIR.lnk"
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($lnk)
    $s.TargetPath = $pythonw
    $s.Arguments = "-X utf8 `"$(Join-Path $root 'mj.py')`" watch"
    $s.WorkingDirectory = $root
    $s.WindowStyle = 7
    $s.Save()
    Write-Host "Startup shortcut created: $lnk" -ForegroundColor Green
}
