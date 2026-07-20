#!/usr/bin/env python3
"""
generate_video.py
------------------
Picks the next unused verse from verses.json, renders a 1080x1920 vertical
YouTube Short with animated bilingual (Telugu + English) text over a soft
animated gradient background, mixed with a soft background music loop.

Outputs:
  output/<date>.mp4          <- the rendered video
  output/<date>.meta.json    <- title/description/tags for the uploader

Exits non-zero with a clear message on any failure (verses queue empty,
missing font, missing music, ffmpeg error) so the automation fails loudly
instead of silently uploading something broken.
"""

import json
import random
import subprocess
import sys
import textwrap
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSES_FILE = ROOT / "verses.json"
MUSIC_DIR = ROOT / "assets" / "music"
OUTPUT_DIR = ROOT / "output"
TMP_DIR = ROOT / "tmp"

WIDTH, HEIGHT = 1080, 1920
FPS = 30


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def find_system_font(patterns) -> Path:
    """Ask fontconfig (fc-match) for an installed font file, trying each
    pattern in order. Far more reliable than hardcoding a download URL,
    since it just asks the OS what's actually installed."""
    for pattern in patterns:
        try:
            result = subprocess.run(
                ["fc-match", "-f", "%{file}", pattern],
                capture_output=True, text=True, check=True,
            )
            path = Path(result.stdout.strip())
            if path.exists():
                return path
        except Exception:
            continue
    fail(
        f"Could not find any installed font matching: {patterns}. "
        "Make sure the workflow's 'Install fonts' step (apt-get install fonts-noto) ran successfully."
    )


def pick_music() -> Path:
    tracks = sorted(MUSIC_DIR.glob("*.mp3"))
    if not tracks:
        fail(
            f"No .mp3 files found in {MUSIC_DIR}. Add at least one royalty-free "
            "soft background music loop there (see README)."
        )
    return random.choice(tracks)


def load_next_verse() -> dict:
    if not VERSES_FILE.exists():
        fail(f"{VERSES_FILE} does not exist.")
    data = json.loads(VERSES_FILE.read_text(encoding="utf-8"))
    for entry in data:
        if not entry.get("used"):
            return entry, data
    fail(
        "No unused verses left in verses.json! Paste more Telugu + English "
        "verses into the queue before the next run."
    )


def mark_used(entry: dict, data: list) -> None:
    for e in data:
        if e is entry or (e.get("reference") == entry.get("reference") and e.get("english") == entry.get("english")):
            e["used"] = True
            e["used_date"] = date.today().isoformat()
            break
    VERSES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def wrap_text(text: str, width_chars: int) -> str:
    wrapped = textwrap.fill(text.strip(), width=width_chars)
    return wrapped


def compute_duration(telugu: str, english: str) -> float:
    total_chars = len(telugu) + len(english)
    # Roughly scale reading time; clamp to a sensible Shorts range.
    duration = 10 + total_chars / 18.0
    return max(16.0, min(45.0, duration))


def ffmpeg_escape_path(p: Path) -> str:
    # Paths are used inside ffmpeg filter args; escape colons/backslashes.
    s = str(p).replace("\\", "/")
    s = s.replace(":", "\\:")
    return s


def build_video(entry: dict) -> Path:
    telugu = entry["telugu"].strip()
    english = entry["english"].strip()
    reference = entry.get("reference", "").strip()

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    telugu_wrapped = wrap_text(telugu, 22)
    english_wrapped = wrap_text(english, 30)

    telugu_txt = TMP_DIR / "telugu.txt"
    english_txt = TMP_DIR / "english.txt"
    ref_txt = TMP_DIR / "reference.txt"
    telugu_txt.write_text(telugu_wrapped, encoding="utf-8")
    english_txt.write_text(english_wrapped, encoding="utf-8")
    ref_txt.write_text(reference, encoding="utf-8")

    telugu_font = find_system_font([
        "Noto Sans Telugu:bold", "Noto Sans Telugu",
        "Noto Sans Telugu UI:bold", "Noto Sans Telugu UI",
    ])
    english_font = find_system_font(["Noto Sans:bold", "DejaVu Sans:bold"])
    music = pick_music()

    duration = compute_duration(telugu, english)
    today_str = date.today().isoformat()
    out_path = OUTPUT_DIR / f"{today_str}.mp4"

    # Soft animated pastel gradient background (no external footage needed,
    # so there is zero copyright risk on the visual).
    bg = (
        f"gradients=s={WIDTH}x{HEIGHT}:d={duration}:speed=0.02:"
        f"c0=0x1b2a4a:c1=0x3a4a6b:x0=0:y0=0:x1={WIDTH}:y1={HEIGHT}"
    )

    fade_in = 1.0
    fade_out = 1.0

    def esc_commas(expr: str) -> str:
        # Inside a single-quoted ffmpeg option value, internal commas must
        # still be backslash-escaped or the filtergraph parser splits on them.
        return expr.replace(",", "\\,")

    def fade_alpha(start_delay: float) -> str:
        # fades in starting at start_delay, stays opaque, fades out near the end
        expr = (
            f"if(lt(t,{start_delay}),0,"
            f"if(lt(t,{start_delay + fade_in}),(t-{start_delay})/{fade_in},"
            f"if(gt(t,{duration - fade_out}),max(0,({duration}-t)/{fade_out}),1)))"
        )
        return f"'{esc_commas(expr)}'"

    def slide_y(base_y: str, start_delay: float) -> str:
        expr = f"({base_y})+(1-min(max(t-{start_delay},0)/{fade_in},1))*18"
        return f"'{esc_commas(expr)}'"

    telugu_filter = (
        f"drawtext=fontfile={ffmpeg_escape_path(telugu_font)}:"
        f"textfile={ffmpeg_escape_path(telugu_txt)}:"
        f"fontsize=58:fontcolor=white:line_spacing=14:"
        f"x=(w-text_w)/2:y={slide_y('h*0.30', 0.0)}:"
        f"alpha={fade_alpha(0.0)}"
    )
    english_filter = (
        f"drawtext=fontfile={ffmpeg_escape_path(english_font)}:"
        f"textfile={ffmpeg_escape_path(english_txt)}:"
        f"fontsize=42:fontcolor=0xE8E8E8:line_spacing=10:"
        f"x=(w-text_w)/2:y={slide_y('h*0.58', 0.6)}:"
        f"alpha={fade_alpha(0.6)}"
    )
    ref_filter = (
        f"drawtext=fontfile={ffmpeg_escape_path(english_font)}:"
        f"textfile={ffmpeg_escape_path(ref_txt)}:"
        f"fontsize=34:fontcolor=0xC9A94A:"
        f"x=(w-text_w)/2:y=h*0.85:"
        f"alpha={fade_alpha(1.2)}"
    )

    vf = (
        f"{bg},format=yuv420p,"
        f"{telugu_filter},{english_filter},{ref_filter},"
        f"fade=t=in:st=0:d=0.6:alpha=1,fade=t=out:st={duration - 0.6}:d=0.6:alpha=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=s={WIDTH}x{HEIGHT}:d={duration}:r={FPS}",
        "-stream_loop", "-1", "-i", str(music),
        "-filter_complex", vf,
        "-map", "0:v", "-map", "1:a",
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-af", f"afade=t=in:st=0:d=1,afade=t=out:st={duration - 1.2}:d=1.2",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ]

    print("Running ffmpeg:\n", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"ffmpeg failed:\n{result.stderr[-4000:]}")

    return out_path


def write_metadata(entry: dict, video_path: Path) -> None:
    reference = entry.get("reference", "Daily Verse")
    title = f"{reference} | Daily Bible Verse ✝️ #Shorts"
    description = (
        f"{entry['english']}\n\n{entry['telugu']}\n\n"
        f"— {reference}\n\n"
        "A daily moment of peace. New verse every morning.\n"
        "#Shorts #BibleVerse #DailyVerse #Telugu #Faith #Jesus #Scripture"
    )
    meta = {
        "title": title[:100],
        "description": description[:4900],
        "tags": ["Bible verse", "daily verse", "Telugu bible", "shorts", "faith", "scripture"],
        "reference": reference,
    }
    meta_path = video_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote metadata to {meta_path}")


def main() -> None:
    entry, all_data = load_next_verse()
    print(f"Selected verse: {entry.get('reference')}")
    video_path = build_video(entry)
    write_metadata(entry, video_path)
    mark_used(entry, all_data)
    print(f"Done. Video at {video_path}")


if __name__ == "__main__":
    main()
