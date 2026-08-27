# Session recaps pipeline

After a Discord session, drop the **Craig zip** into `inbox/`. A watcher transcribes each speaker track with Whisper (using campaign names from `names.txt`) and:

1. Saves markdown to `transcripts/`
2. Uploads that file to the Discord `#session-recaps` channel

Then in Cursor, ask: **Write a recap of this transcript, post it to #session-recaps, and list campaign-note updates.**

## One-time setup

In PowerShell, from this folder:

```powershell
Set-ExecutionPolicy -Scope CurrentUser Bypass
.\setup.ps1
.\Register-InboxWatcher.ps1
```

`setup.ps1` installs ffmpeg and a Python venv with Whisper. `Register-InboxWatcher.ps1` starts a watcher at Windows logon.

Or double-click `Start-InboxWatcher.bat` when you want it running only for a session.

## Each game night

1. In Discord voice: `/join` (Craig), then `/stop` when you wrap.
2. Download Craig’s zip (FLAC, one file per speaker).
3. Drop the zip into `inbox/`.
4. Wait. Progress is in `logs/watcher.log`.
5. The transcript lands in `transcripts/` and in `#session-recaps`.

Processed zips move to `inbox/processed/`. Failures go to `inbox/failed/`.

## Optional: map Discord names to characters

Edit `config.local.json` (not committed):

```json
{
  "speaker_map": {
    "SomeDiscordName": "Gariel",
    "AnotherName": "Abbath"
  }
}
```

Use the filename Craig gives each track (usually the Discord display name).

## Manual run

```powershell
.\.venv\Scripts\python.exe transcribe_session.py "C:\path\to\craig.zip"
```

`--no-discord` skips the channel upload.

## Notes

- First transcription downloads the Whisper model (large). Later runs reuse it.
- This PC has an NVIDIA GPU; the script prefers CUDA and falls back to CPU.
- Add or fix names in `names.txt` anytime — Whisper uses that list as a hint.
- `config.local.json` holds the Discord webhook and must stay out of git.
