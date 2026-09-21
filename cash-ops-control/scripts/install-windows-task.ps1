param([string]$TaskName = "Cash Ops Control")
$ErrorActionPreference = "Stop"
$Project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = (Get-Command python).Source
$Action = New-ScheduledTaskAction -Execute $Python -Argument 'cash_ops.py scan' -WorkingDirectory $Project
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Hours 6)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Scan configured public bounty sources. Uses Python stdlib; no LLM or paid API." -Force
Write-Host "Installed '$TaskName'. It runs every 6 hours while this PC is available."
