#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Download YouTube transcript and optionally audio.

Usage:
    uv run us/scripts/yt_transcript.py <url>                    # transcript only
    uv run us/scripts/yt_transcript.py <url> --audio             # transcript + mp3
    uv run us/scripts/yt_transcript.py <url> --start 17:25       # transcript from timestamp
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "data" / "yt"


def srt_to_text(srt_path: Path, start_seconds: int = 0) -> str:
    """Convert SRT to clean text, optionally starting from a timestamp."""
    lines = srt_path.read_text().splitlines()
    segments = []
    current_time = 0

    for line in lines:
        # Parse timestamp
        m = re.match(r"(\d{2}):(\d{2}):(\d{2}),\d+\s*-->", line)
        if m:
            h, mn, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            current_time = h * 3600 + mn * 60 + s
            continue

        # Skip sequence numbers and empty lines
        if line.strip() == "" or line.strip().isdigit():
            continue

        if current_time >= start_seconds:
            clean = re.sub(r"<[^>]+>", "", line).strip()
            if clean and clean not in segments[-1:]:
                segments.append(clean)

    return " ".join(segments)


def parse_timestamp(ts: str) -> int:
    """Parse MM:SS or HH:MM:SS to seconds."""
    parts = ts.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0


def download_transcript(url: str) -> Path:
    """Download auto-generated English subtitles."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Extract video ID
    vid_match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    vid_id = vid_match.group(1) if vid_match else "unknown"

    out_template = str(OUT_DIR / vid_id)

    subprocess.run(
        [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--sub-format", "srt",
            "--skip-download",
            "-o", out_template,
            url,
        ],
        check=True,
        capture_output=True,
    )

    srt_path = OUT_DIR / f"{vid_id}.en.srt"
    if not srt_path.exists():
        print(f"Error: No transcript found at {srt_path}", file=sys.stderr)
        sys.exit(1)

    return srt_path


def download_audio(url: str) -> Path:
    """Download audio as mp3."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    vid_match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    vid_id = vid_match.group(1) if vid_match else "unknown"

    out_template = str(OUT_DIR / vid_id)

    subprocess.run(
        [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "5",
            "-o", out_template + ".%(ext)s",
            url,
        ],
        check=True,
        capture_output=True,
    )

    mp3_path = OUT_DIR / f"{vid_id}.mp3"
    if not mp3_path.exists():
        print(f"Error: No audio found at {mp3_path}", file=sys.stderr)
        sys.exit(1)

    return mp3_path


def main():
    parser = argparse.ArgumentParser(description="Download YouTube transcript/audio")
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument("--audio", action="store_true", help="Also download mp3")
    parser.add_argument("--start", default=None, help="Start timestamp (MM:SS or HH:MM:SS)")
    parser.add_argument("--srt", action="store_true", help="Output raw SRT instead of clean text")
    args = parser.parse_args()

    print(f"Downloading transcript...", file=sys.stderr)
    srt_path = download_transcript(args.url)

    if args.srt:
        print(srt_path.read_text())
    else:
        start = parse_timestamp(args.start) if args.start else 0
        text = srt_to_text(srt_path, start)

        txt_path = srt_path.with_suffix(".txt")
        txt_path.write_text(text)
        print(text)
        print(f"\nSaved: {txt_path}", file=sys.stderr)

    if args.audio:
        print(f"Downloading audio...", file=sys.stderr)
        mp3_path = download_audio(args.url)
        print(f"Saved: {mp3_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
