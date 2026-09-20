# Stop the background PLETHORA MJOLNIR watcher started by watch-background.ps1
$stateDir = Join-Path $env:USERPROFILE ".plethora-mjolnir"
$pidFile = Join-Path $stateDir "watch.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "No PID file found - watcher is not running." -ForegroundColor Yellow
    return
}
$pid = Get-Content $pidFile
if (Get-Process -Id $pid -ErrorAction SilentlyContinue) {
    Stop-Process -Id $pid -Force
    Write-Host "Stopped watcher (PID $pid)." -ForegroundColor Green
} else {
    Write-Host "Process $pid was not running." -ForegroundColor Yellow
}
Remove-Item $pidFile -ErrorAction SilentlyContinue
