# One-time setup: ffmpeg, Python venv, faster-whisper.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "Installing ffmpeg if needed..."
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    $ffmpegDirs = @(
        "$env:ProgramFiles\ffmpeg\bin",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links",
        "$env:ProgramFiles\WinGet\Links"
    )
    foreach ($dir in $ffmpegDirs) {
        if (Test-Path $dir) {
            $env:Path = "$dir;$env:Path"
        }
    }
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        Write-Warning "ffmpeg was installed but is not on PATH yet. Open a new terminal after setup."
    }
} else {
    Write-Host "ffmpeg already on PATH."
}

$venv = Join-Path $Root ".venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Write-Host "Creating Python venv..."
    python -m venv $venv
}

$python = Join-Path $venv "Scripts\python.exe"
Write-Host "Installing faster-whisper..."
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $Root "requirements.txt")

# Optional Windows CUDA wheels for CTranslate2
try {
    & $python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
} catch {
    Write-Warning "Could not install NVIDIA CUDA pip wheels (CPU fallback will still work)."
}

$localConfig = Join-Path $Root "config.local.json"
$example = Join-Path $Root "config.example.json"
if (-not (Test-Path $localConfig)) {
    Copy-Item $example $localConfig
    Write-Host "Created config.local.json. Paste your Discord webhook URL if it is empty."
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "inbox"), (Join-Path $Root "inbox\processed"), (Join-Path $Root "inbox\failed"), (Join-Path $Root "logs"), (Join-Path $Root "transcripts") | Out-Null

Write-Host ""
Write-Host "Setup complete."
Write-Host "1. Drop a Craig zip into: $Root\inbox"
Write-Host "2. Start the watcher:     .\watch-inbox.ps1"
Write-Host "   or register it to start at login: .\Register-InboxWatcher.ps1"
