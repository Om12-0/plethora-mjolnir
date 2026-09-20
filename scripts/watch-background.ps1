# Start the PLETHORA MJOLNIR watcher invisibly (no console window).
# Logs go to %USERPROFILE%\.plethora-mjolnir\watch.log
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here

$venvPy = Join-Path $root ".venv\Scripts\pythonw.exe"
$pythonw = if (Test-Path $venvPy) { $venvPy } else { "pythonw" }

$stateDir = Join-Path $env:USERPROFILE ".plethora-mjolnir"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$log = Join-Path $stateDir "watch.log"
$errLog = Join-Path $stateDir "watch.err.log"
$pidFile = Join-Path $stateDir "watch.pid"

if (Test-Path $pidFile) {
    $old = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
        Write-Host "Watcher already running (PID $old)." -ForegroundColor Yellow
        return
    }
}

$p = Start-Process -FilePath $pythonw `
    -ArgumentList @("-X", "utf8", (Join-Path $root "mj.py"), "watch") `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput $log -RedirectStandardError $errLog -PassThru

$p.Id | Set-Content $pidFile
Write-Host "PLETHORA MJOLNIR watcher started (PID $($p.Id))." -ForegroundColor Green
Write-Host "Logs: $log"
