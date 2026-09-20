# Remove PLETHORA MJOLNIR autostart (task + startup-folder shortcut).
$taskName = "PlethoraMjolnir"
try {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed scheduled task '$taskName'." -ForegroundColor Green
    } else {
        Write-Host "No scheduled task '$taskName'." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Could not query scheduled tasks: $($_.Exception.Message)" -ForegroundColor Yellow
}

$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "PLETHORA MJOLNIR.lnk"
if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "Removed startup shortcut." -ForegroundColor Green }
