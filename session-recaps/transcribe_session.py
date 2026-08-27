#!/usr/bin/env python3
"""Transcribe a Craig zip (or loose audio) into a speaker-labeled markdown file."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

AUDIO_SUFFIXES = {".flac", ".ogg", ".wav", ".mp3", ".m4a", ".opus", ".webm", ".aac"}
SKIP_NAME_PARTS = ("mixed", "all-speakers", "all_speakers")
ROOT = Path(__file__).resolve().parent


def _prepend_path(directory: Path) -> None:
    if not directory.is_dir():
        return
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(directory))
        except Exception:
            pass
    os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")


def _add_ffmpeg_to_path() -> None:
    if shutil.which("ffmpeg"):
        return
    home = Path.home()
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "WinGet" / "Links",
    ]
    winget_pkgs = home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_pkgs.is_dir():
        candidates.extend(winget_pkgs.glob("Gyan.FFmpeg*/ffmpeg-*/bin"))
    for directory in candidates:
        _prepend_path(directory)
        if shutil.which("ffmpeg"):
            return


def _add_nvidia_dll_dirs() -> None:
    """Windows + pip CUDA wheels: expose cublas/cudnn DLLs to CTranslate2.

    nvidia-* packages are namespace packages, so nvidia.__file__ is None.
    DLLs live in nvidia/<lib>/bin (e.g. nvidia/cublas/bin/cublas64_12.dll).
    """
    if os.name != "nt":
        return
    try:
        import nvidia
        import ctypes

        dirs = []
        for root in nvidia.__path__:
            nvidia_root = Path(root)
            dirs.extend(nvidia_root.glob("*/bin"))
            dirs.extend(nvidia_root.glob("*/lib"))
        for directory in dirs:
            _prepend_path(directory)
        for name in ("cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll", "nvrtc64_120_0.dll"):
            for directory in dirs:
                candidate = directory / name
                if candidate.exists():
                    ctypes.WinDLL(str(candidate))
                    break
    except Exception:
        return


def load_config() -> dict:
    local = ROOT / "config.local.json"
    example = ROOT / "config.example.json"
    data: dict = {}
    if example.exists():
        data.update(json.loads(example.read_text(encoding="utf-8")))
    if local.exists():
        data.update(json.loads(local.read_text(encoding="utf-8")))
    data.setdefault("webhook_url", "")
    data.setdefault("whisper_model", "turbo")
    data.setdefault("language", "en")
    data.setdefault("speaker_map", {})
    return data


def load_names_prompt() -> str:
    names = ROOT / "names.txt"
    if not names.exists():
        return ""
    text = " ".join(names.read_text(encoding="utf-8").split())
    return text[:800]


def speaker_from_filename(path: Path, speaker_map: dict[str, str]) -> str:
    stem = path.stem
    stem = re.sub(r"^\d+[-_ ]+", "", stem)
    stem = re.sub(r"[-_ ]+\d{5,}$", "", stem)
    stem = stem.replace("_", " ").replace("-", " ").strip() or path.stem
    mapped = {k.lower(): v for k, v in speaker_map.items()}
    return mapped.get(stem.lower(), stem)


def collect_audio(source: Path, extract_dir: Path) -> list[Path]:
    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            zf.extractall(extract_dir)
        search_root = extract_dir
    elif source.is_dir():
        search_root = source
    elif source.is_file() and source.suffix.lower() in AUDIO_SUFFIXES:
        return [source]
    else:
        raise SystemExit(f"Not a zip, audio file, or folder: {source}")

    files = [
        p
        for p in search_root.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES
    ]
    files = [p for p in files if not any(part in p.stem.lower() for part in SKIP_NAME_PARTS)] or files
    files.sort(key=lambda p: p.name.lower())
    if not files:
        raise SystemExit(f"No audio files found in {source}")
    return files


def format_ts(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def merge_segments(rows: list[dict], gap: float = 2.0) -> list[dict]:
    if not rows:
        return []
    rows = sorted(rows, key=lambda r: (r["start"], r["speaker"]))
    merged = [dict(rows[0])]
    for row in rows[1:]:
        prev = merged[-1]
        if row["speaker"] == prev["speaker"] and row["start"] - prev["end"] <= gap:
            prev["end"] = max(prev["end"], row["end"])
            prev["text"] = f"{prev['text']} {row['text']}".strip()
        else:
            merged.append(dict(row))
    return merged


def load_model(model_name: str):
    _add_ffmpeg_to_path()
    _add_nvidia_dll_dirs()
    from faster_whisper import WhisperModel

    last_error = None
    for device, compute in (("cuda", "float16"), ("cpu", "int8")):
        try:
            model = WhisperModel(model_name, device=device, compute_type=compute)
            print(f"Loaded Whisper '{model_name}' on {device} ({compute})")
            return model, device
        except Exception as exc:
            last_error = exc
            print(f"Could not load '{model_name}' on {device}: {exc}")
    raise SystemExit(f"Failed to load Whisper model '{model_name}': {last_error}")


def transcribe_file(model, audio: Path, speaker: str, language: str, prompt: str) -> list[dict]:
    print(f"Transcribing {audio.name} as {speaker}...")
    segments, _info = model.transcribe(
        str(audio),
        language=language or None,
        initial_prompt=prompt or None,
        vad_filter=True,
        beam_size=5,
    )
    rows = []
    for segment in segments:
        text = (segment.text or "").strip()
        if not text:
            continue
        rows.append(
            {
                "start": float(segment.start or 0),
                "end": float(segment.end or 0),
                "speaker": speaker,
                "text": text,
            }
        )
    print(f"  {len(rows)} segments")
    return rows


def write_markdown(path: Path, source: Path, model_name: str, device: str, rows: list[dict]) -> None:
    date_label = path.stem
    lines = [
        f"# Session transcript — {date_label}",
        "",
        f"- Source: `{source.name}`",
        f"- Model: `{model_name}` ({device})",
        f"- Speakers: {', '.join(sorted({r['speaker'] for r in rows}) or ['unknown'])}",
        "",
        "## Transcript",
        "",
    ]
    if not rows:
        lines.append("_No speech detected._")
        lines.append("")
    else:
        for row in rows:
            lines.append(f"**[{format_ts(row['start'])}] {row['speaker']}:** {row['text']}")
            lines.append("")
    lines.extend(
        [
            "---",
            "",
            "In Cursor, ask: *Write a recap of this transcript, post it to #session-recaps, and list campaign-note updates.*",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def post_discord(webhook_url: str, transcript: Path, source_name: str) -> None:
    if not webhook_url or "ID/TOKEN" in webhook_url:
        print("No webhook configured; skipped Discord upload.")
        return
    content = (
        f"Session transcript from `{source_name}` is attached.\n"
        "In Cursor, ask: Write a recap of this transcript, post it to #session-recaps, "
        "and list campaign-note updates."
    )
    payload = json.dumps({"content": content[:1900], "username": "Session Recaps"})
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        raise SystemExit("curl is required to upload the transcript to Discord.")
    result = subprocess.run(
        [
            curl,
            "-sS",
            "-X",
            "POST",
            webhook_url,
            "-F",
            f"payload_json={payload}",
            "-F",
            f"files[0]=@{transcript}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Discord upload failed: {result.stderr or result.stdout}")
    print("Posted transcript to #session-recaps.")


def default_output_name(source: Path) -> str:
    stamp = datetime.fromtimestamp(source.stat().st_mtime).strftime("%Y-%m-%d_%H%M")
    return f"{stamp}.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe a Craig recording into markdown.")
    parser.add_argument("input", type=Path, help="Craig zip, audio file, or folder of tracks")
    parser.add_argument("--no-discord", action="store_true", help="Skip the Discord upload")
    parser.add_argument("--date", help="Output filename stem, e.g. 2026-08-14")
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Not found: {source}")

    config = load_config()
    prompt = load_names_prompt()
    out_dir = ROOT / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{args.date}.md" if args.date else out_dir / default_output_name(source)

    work_root = ROOT / "work"
    work_root.mkdir(parents=True, exist_ok=True)
    extract_dir = Path(tempfile.mkdtemp(prefix="craig_", dir=work_root))

    try:
        audio_files = collect_audio(source, extract_dir)
        speaker_map = config.get("speaker_map") or {}
        model, device = load_model(config.get("whisper_model") or "turbo")
        rows: list[dict] = []
        for audio in audio_files:
            speaker = speaker_from_filename(audio, speaker_map)
            rows.extend(
                transcribe_file(
                    model,
                    audio,
                    speaker,
                    config.get("language") or "en",
                    prompt,
                )
            )
        rows = merge_segments(rows)
        write_markdown(output, source, config.get("whisper_model") or "turbo", device, rows)
        print(f"Wrote {output}")
        if not args.no_discord:
            post_discord(config.get("webhook_url") or "", output, source.name)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
