# Launch the floating PLETHORA MJOLNIR launcher (no console window).
# Hotkey: Alt+Space (or Ctrl+Alt+Space) toggles the search bar.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here

$venvPy = Join-Path $root ".venv\Scripts\pythonw.exe"
$pythonw = if (Test-Path $venvPy) { $venvPy } else { "pythonw" }

Start-Process -FilePath $pythonw -ArgumentList @("-X", "utf8", (Join-Path $root "mj.py"), "ui") `
    -WorkingDirectory $root -WindowStyle Hidden
Write-Host "PLETHORA MJOLNIR launcher started - press Alt+Space." -ForegroundColor Green
