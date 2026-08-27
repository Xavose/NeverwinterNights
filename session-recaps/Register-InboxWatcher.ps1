# Register a logon task so the inbox watcher starts with Windows.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Watcher = Join-Path $Root "watch-inbox.ps1"
$TaskName = "Neverwinter-Session-Inbox"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Watcher`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Registered and started scheduled task '$TaskName'."
Write-Host "It watches: $Root\inbox"
Write-Host "Stop it with: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
