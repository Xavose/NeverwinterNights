# Polls session-recaps/inbox for Craig zips / audio and runs transcribe_session.py.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Inbox = Join-Path $Root "inbox"
$Processed = Join-Path $Inbox "processed"
$Failed = Join-Path $Inbox "failed"
$Logs = Join-Path $Root "logs"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Transcribe = Join-Path $Root "transcribe_session.py"
$OkExt = @(".zip", ".flac", ".ogg", ".wav", ".mp3", ".m4a", ".opus")

New-Item -ItemType Directory -Force -Path $Inbox, $Processed, $Failed, $Logs | Out-Null

$ffmpegHints = @(
    "$env:LOCALAPPDATA\Microsoft\WinGet\Links",
    "$env:ProgramFiles\ffmpeg\bin",
    "$env:ProgramFiles\WinGet\Links"
)
foreach ($hint in $ffmpegHints) {
    if (Test-Path $hint) { $env:Path = "$hint;$env:Path" }
}

function Write-Log([string]$Message) {
    $line = "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $Message
    Add-Content -Path (Join-Path $Logs "watcher.log") -Value $line
    Write-Host $line
}

function Get-Python {
    if (Test-Path $VenvPython) { return $VenvPython }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    throw "Python not found. Run setup.ps1 first."
}

function Test-FileReady([string]$Path) {
    try {
        $first = (Get-Item -LiteralPath $Path).Length
        if ($first -le 0) { return $false }
        Start-Sleep -Seconds 3
        $second = (Get-Item -LiteralPath $Path).Length
        return ($first -eq $second)
    } catch {
        return $false
    }
}

function Invoke-Transcribe([string]$Path) {
    $name = [IO.Path]::GetFileName($Path)
    Write-Log "Transcribing $name"
    try {
        $python = Get-Python
        $output = & $python $Transcribe $Path 2>&1
        $code = $LASTEXITCODE
        foreach ($line in $output) { Write-Log "$line" }
        if ($code -ne 0) { throw "transcribe_session.py exited $code" }

        $dest = Join-Path $Processed $name
        if (Test-Path $dest) {
            $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            $dest = Join-Path $Processed ("{0}_{1}{2}" -f [IO.Path]::GetFileNameWithoutExtension($name), $stamp, [IO.Path]::GetExtension($name))
        }
        Move-Item -LiteralPath $Path -Destination $dest -Force
        Write-Log "Done. Moved $name to processed/"
    } catch {
        Write-Log "FAILED $name : $_"
        if (Test-Path -LiteralPath $Path) {
            Move-Item -LiteralPath $Path -Destination (Join-Path $Failed $name) -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Log "Watching $Inbox  (Ctrl+C to stop)"
Write-Log "Drop a Craig zip here after /stop."

while ($true) {
    $files = Get-ChildItem -File -LiteralPath $Inbox -ErrorAction SilentlyContinue |
        Where-Object { $OkExt -contains $_.Extension.ToLowerInvariant() }

    foreach ($file in $files) {
        if (Test-FileReady $file.FullName) {
            Invoke-Transcribe $file.FullName
        }
    }

    Start-Sleep -Seconds 5
}
