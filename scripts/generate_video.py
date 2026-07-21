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

--------------------------------------------------------------------------
WHAT CHANGED IN THIS VERSION (fixing overlap / centering / spill / jerk):

1. Text is now measured with the ACTUAL font file (via Pillow) before
   ffmpeg ever runs, so wrapping is based on real pixel width, not a
   guessed character count. Long Telugu conjuncts / bold glyphs no longer
   overflow the 1080px frame.

2. Every wrapped line gets its OWN exact x position (computed from its
   real measured width), so every line is perfectly centered -- not just
   the widest line in the paragraph.

3. Telugu / English / reference blocks are stacked using their REAL
   measured heights (line count x line height), so a long verse simply
   makes the block taller and the next block shifts down -- they can
   never overlap. If a verse is long enough that everything wouldn't fit
   the safe area, font size is scaled down slightly (auto-fit) instead of
   spilling off screen.

4. Animation is a single ease-out "rise into place" + fade per block
   (no more double-fade from a whole-frame fade layered on top of a
   per-element fade), which reads as smooth instead of jerky.

5. Bold fonts, an outline/shadow for contrast, and a soft translucent
   "card" behind the text for a richer, more eye-catching look.
--------------------------------------------------------------------------
"""

import json
import random
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    from PIL import ImageFont
except ImportError:
    print(
        "ERROR: Pillow is required (pip install Pillow). "
        "Add 'Pillow' to requirements.txt.",
        file=sys.stderr,
    )
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
VERSES_FILE = ROOT / "verses.json"
MUSIC_DIR = ROOT / "assets" / "music"
OUTPUT_DIR = ROOT / "output"
TMP_DIR = ROOT / "tmp"

WIDTH, HEIGHT = 1080, 1920
FPS = 30

# ---- Layout / style knobs -------------------------------------------------
SAFE_LEFT_RIGHT_MARGIN = 0.07   # fraction of WIDTH kept clear on each side
SAFE_TOP = 0.11                 # fraction of HEIGHT reserved above content
SAFE_BOTTOM = 0.88              # fraction of HEIGHT reserved below content

TELUGU_BASE_SIZE = 66
ENGLISH_BASE_SIZE = 46
REF_BASE_SIZE = 30
MIN_SCALE = 0.55                # never shrink fonts below 55% of base

GAP_TELUGU_ENGLISH = 64
GAP_ENGLISH_REF = 52
LINE_SPACING_EXTRA = 12          # extra px between wrapped lines in a block

TELUGU_COLOR = "0xFFFFFF"
ENGLISH_COLOR = "0xF2F2F2"
REF_COLOR = "0xE3C25B"           # warm gold accent
CARD_COLOR = "black@0.40"
DIVIDER_COLOR = "0xE3C25B@0.85"


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def find_system_font(patterns) -> Path:
    """Ask fontconfig (fc-match) for an installed font file, trying each
    pattern in order (boldest / best options first)."""
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


def compute_duration(telugu: str, english: str) -> float:
    total_chars = len(telugu) + len(english)
    duration = 10 + total_chars / 18.0
    return max(16.0, min(45.0, duration))


def ffmpeg_escape_path(p: Path) -> str:
    s = str(p).replace("\\", "/")
    s = s.replace(":", "\\:")
    return s


def esc_commas(expr: str) -> str:
    # Inside the filtergraph string, literal commas inside an option value
    # must be escaped or the parser treats them as the next chained filter.
    return expr.replace(",", "\\,")


# ---- Pixel-accurate text measuring / wrapping -----------------------------

def wrap_by_pixel(text: str, font: "ImageFont.FreeTypeFont", max_width: float) -> list:
    """Word-wrap using the REAL rendered width of the given font, so lines
    never exceed max_width regardless of script or glyph width."""
    words = text.split()
    if not words:
        return [""]

    def split_long_word(word: str) -> list:
        # Fallback for a single word wider than max_width on its own
        # (rare, but prevents any possibility of spilling off-frame).
        pieces, current = [], ""
        for ch in word:
            if font.getlength(current + ch) <= max_width or not current:
                current += ch
            else:
                pieces.append(current)
                current = ch
        if current:
            pieces.append(current)
        return pieces

    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            if font.getlength(word) > max_width:
                pieces = split_long_word(word)
                lines.extend(pieces[:-1])
                current = pieces[-1] if pieces else ""
            else:
                current = word
    if current:
        lines.append(current)
    return lines or [""]


def line_height_for(font: "ImageFont.FreeTypeFont") -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent + LINE_SPACING_EXTRA


def block_metrics(lines: list, font: "ImageFont.FreeTypeFont"):
    lh = line_height_for(font)
    widths = [font.getlength(line) for line in lines]
    height = lh * len(lines)
    return widths, lh, height


def fit_layout(telugu: str, english: str, reference: str,
                telugu_font_path: Path, english_font_path: Path):
    """Try progressively smaller font scales until telugu+english+reference
    fit inside the safe vertical area. Returns everything build_video needs."""
    safe_width = WIDTH * (1 - 2 * SAFE_LEFT_RIGHT_MARGIN)
    safe_top_px = HEIGHT * SAFE_TOP
    safe_bottom_px = HEIGHT * SAFE_BOTTOM
    safe_height = safe_bottom_px - safe_top_px

    scale = 1.0
    for _ in range(20):
        t_size = max(int(TELUGU_BASE_SIZE * scale), int(TELUGU_BASE_SIZE * MIN_SCALE))
        e_size = max(int(ENGLISH_BASE_SIZE * scale), int(ENGLISH_BASE_SIZE * MIN_SCALE))
        r_size = max(int(REF_BASE_SIZE * scale), int(REF_BASE_SIZE * MIN_SCALE))

        t_font = ImageFont.truetype(str(telugu_font_path), t_size)
        e_font = ImageFont.truetype(str(english_font_path), e_size)
        r_font = ImageFont.truetype(str(english_font_path), r_size)

        t_lines = wrap_by_pixel(telugu, t_font, safe_width)
        e_lines = wrap_by_pixel(english, e_font, safe_width)
        r_lines = wrap_by_pixel(reference, r_font, safe_width) if reference else []

        t_widths, t_lh, t_h = block_metrics(t_lines, t_font)
        e_widths, e_lh, e_h = block_metrics(e_lines, e_font)
        r_widths, r_lh, r_h = block_metrics(r_lines, r_font) if r_lines else ([], 0, 0)

        gap2 = GAP_ENGLISH_REF if r_lines else 0
        total_h = t_h + GAP_TELUGU_ENGLISH + e_h + gap2 + r_h

        if total_h <= safe_height or scale <= MIN_SCALE:
            start_y = safe_top_px + max(0, (safe_height - total_h) / 2)
            return {
                "telugu": {"font": t_font, "font_path": telugu_font_path, "lines": t_lines,
                            "widths": t_widths, "line_h": t_lh, "top": start_y, "color": TELUGU_COLOR},
                "english": {"font": e_font, "font_path": english_font_path, "lines": e_lines,
                             "widths": e_widths, "line_h": e_lh,
                             "top": start_y + t_h + GAP_TELUGU_ENGLISH, "color": ENGLISH_COLOR},
                "reference": {"font": r_font, "font_path": english_font_path, "lines": r_lines,
                               "widths": r_widths, "line_h": r_lh,
                               "top": start_y + t_h + GAP_TELUGU_ENGLISH + e_h + gap2, "color": REF_COLOR},
                "card_top": start_y - 46,
                "card_bottom": start_y + total_h + 46,
            }
        scale *= 0.92

    fail("Could not fit verse text within the safe area even at minimum font size.")


def write_line_files(block_key: str, lines: list) -> list:
    paths = []
    for i, line in enumerate(lines):
        p = TMP_DIR / f"{block_key}_{i}.txt"
        p.write_text(line, encoding="utf-8")
        paths.append(p)
    return paths


def drawtext_for_line(font_path: Path, text_path: Path, x: float, y_expr: str,
                        fontsize: int, color: str, alpha_expr: str) -> str:
    return (
        f"drawtext=fontfile={ffmpeg_escape_path(font_path)}:"
        f"textfile={ffmpeg_escape_path(text_path)}:"
        f"fontsize={fontsize}:fontcolor={color}:"
        f"borderw=3:bordercolor=black@0.55:"
        f"shadowx=0:shadowy=3:shadowcolor=black@0.35:"
        f"x={x:.1f}:y={y_expr}:alpha={alpha_expr}"
    )


def ease_rise_expr(fixed_y: float, delay: float, duration_in: float) -> str:
    # (1 - p)^3 goes 1 -> 0 as p goes 0 -> 1: text starts ~26px lower and
    # eases up into its final resting position -- smooth, not jerky.
    p = f"min(max(t-{delay}\\,0)/{duration_in}\\,1)"
    return f"'{fixed_y:.1f}+(pow(1-{p}\\,3))*26'"


def ease_alpha_expr(delay: float, fade_in: float, duration: float, fade_out: float) -> str:
    expr = (
        f"if(lt(t\\,{delay})\\,0\\,"
        f"if(lt(t\\,{delay + fade_in})\\,(t-{delay})/{fade_in}\\,"
        f"if(gt(t\\,{duration - fade_out})\\,max(0\\,({duration}-t)/{fade_out})\\,1)))"
    )
    return f"'{expr}'"


def build_video(entry: dict) -> Path:
    telugu = entry["telugu"].strip()
    english = entry["english"].strip()
    reference = entry.get("reference", "").strip()

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    telugu_font_path = find_system_font([
        "Noto Sans Telugu:style=Bold", "Noto Sans Telugu:bold", "Noto Sans Telugu",
        "Noto Sans Telugu UI:style=Bold", "Noto Sans Telugu UI",
    ])
    english_font_path = find_system_font([
        "Noto Sans Display:style=Bold", "Noto Sans:style=Bold", "Noto Sans:bold",
        "DejaVu Sans:bold",
    ])
    music = pick_music()

    layout = fit_layout(telugu, english, reference, telugu_font_path, english_font_path)

    duration = compute_duration(telugu, english)
    today_str = date.today().isoformat()
    out_path = OUTPUT_DIR / f"{today_str}.mp4"

    bg = (
        f"gradients=s={WIDTH}x{HEIGHT}:d={duration}:speed=0.02:"
        f"c0=0x1b2a4a:c1=0x3a4a6b:x0=0:y0=0:x1={WIDTH}:y1={HEIGHT}"
    )

    filters = [bg, "format=yuv420p"]

    # Soft translucent "card" behind all the text for a richer, more
    # eye-catching, higher-contrast look.
    card_x = WIDTH * SAFE_LEFT_RIGHT_MARGIN - 24
    card_w = WIDTH * (1 - 2 * SAFE_LEFT_RIGHT_MARGIN) + 48
    card_y = layout["card_top"]
    card_h = layout["card_bottom"] - layout["card_top"]
    filters.append(
        f"drawbox=x={card_x:.1f}:y={card_y:.1f}:w={card_w:.1f}:h={card_h:.1f}:"
        f"color={CARD_COLOR}:t=fill"
    )

    block_delays = {"telugu": 0.0, "english": 0.55, "reference": 1.05}
    fade_in = 0.7
    fade_out = 0.6

    for key in ("telugu", "english", "reference"):
        block = layout[key]
        if not block["lines"] or block["lines"] == [""]:
            continue
        line_paths = write_line_files(key, block["lines"])
        delay = block_delays[key]
        alpha_expr = ease_alpha_expr(delay, fade_in, duration, fade_out)
        for i, (line_path, width) in enumerate(zip(line_paths, block["widths"])):
            x = (WIDTH - width) / 2
            y = block["top"] + i * block["line_h"]
            y_expr = ease_rise_expr(y, delay, fade_in)
            filters.append(
                drawtext_for_line(
                    block["font_path"], line_path, x, y_expr,
                    block["font"].size, block["color"], alpha_expr,
                )
            )

    # Thin gold divider between the English text and the reference line.
    if layout["reference"]["lines"] and layout["reference"]["lines"] != [""]:
        divider_y = layout["reference"]["top"] - GAP_ENGLISH_REF / 2 - 1.5
        filters.append(
            f"drawbox=x={(WIDTH - 130) / 2:.1f}:y={divider_y:.1f}:w=130:h=3:"
            f"color={DIVIDER_COLOR}:t=fill"
        )

    vf = ",".join(filters)

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
    title = f"{reference} | Daily Bible Verse \u271d\ufe0f #Shorts"
    description = (
        f"{entry['english']}\n\n{entry['telugu']}\n\n"
        f"\u2014 {reference}\n\n"
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
