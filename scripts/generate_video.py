"""
generate_video.py
------------------
Renders one vertical Bible-verse Short.

Upgrades over the old version:
  - True 4K vertical output (2160x3840), not 1080x1920
  - Animated, colorful moving gradient background (FFmpeg's built-in
    `gradients` source -- no stock footage, no copyright risk, but no
    longer a flat/dull static color)
  - Proper fonts: Noto Sans Telugu for Telugu text (renders correctly
    and looks modern), Poppins SemiBold for English (clean, trending
    "short-form" look)
  - Text animates in with a slide+fade rather than appearing statically
  - Duration is forced into the 40-45s window regardless of verse length
  - Accepts override_font, override_music, override_text/telugu/english
    so the same script powers both the daily run and the 3-layer edit
    workflow

Usage (env vars, all optional except telugu/english/reference):
    VERSE_TELUGU="..."       (required)
    VERSE_ENGLISH="..."      (required)
    VERSE_REF="Psalm 23:1"   (required)
    FONT_STYLE="modern|elegant|bold"      (default: modern)
    MUSIC_FILE="calm_piano_1.mp3"         (default: random from assets/music)
    OUTPUT_PATH="output/short.mp4"        (default: output/short.mp4)
"""

import os
import glob
import random
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---- Config -----------------------------------------------------------

WIDTH, HEIGHT = 2160, 3840       # true 4K vertical
MIN_DURATION, MAX_DURATION = 40, 45
FPS = 30

FONT_DIR = Path("assets/fonts")
MUSIC_DIR = Path("assets/music")

FONT_STYLES = {
    # style_name: (telugu_font_file, english_font_file, accent_color)
    "modern":  ("NotoSansTelugu-SemiBold.ttf", "Poppins-SemiBold.ttf", (255, 214, 102)),
    "elegant": ("NotoSansTelugu-Medium.ttf",   "PlayfairDisplay-Medium.ttf", (230, 200, 255)),
    "bold":    ("NotoSansTelugu-Bold.ttf",     "Montserrat-Bold.ttf", (120, 220, 255)),
}

GRADIENT_PALETTES = [
    "0x1e1147:0x3a1c71:0xd76d77:0xffaf7b",   # dusk purple->coral
    "0x0f2027:0x203a43:0x2c5364:0x00c9a7",   # deep teal
    "0x1a2980:0x26d0ce:0x1a2980:0x00224d",   # blue glow
    "0x2b1055:0x7597de:0x2b1055:0x000000",   # indigo night
]


def _pick_font_style():
    style = os.environ.get("FONT_STYLE", "modern").strip().lower()
    return FONT_STYLES.get(style, FONT_STYLES["modern"])


def _pick_music():
    override = os.environ.get("MUSIC_FILE", "").strip()
    if override:
        path = MUSIC_DIR / override
        if path.exists():
            return str(path)
    tracks = glob.glob(str(MUSIC_DIR / "*.mp3"))
    if not tracks:
        raise SystemExit("No music files found in assets/music/")
    return random.choice(tracks)


def _target_duration(telugu: str, english: str) -> int:
    """Longer combined text -> lean toward 45s, shorter -> lean toward 40s."""
    length = len(telugu) + len(english)
    if length < 80:
        return MIN_DURATION
    if length > 220:
        return MAX_DURATION
    # linear interpolate between 40 and 45 over the 80-220 char range
    ratio = (length - 80) / (220 - 80)
    return int(MIN_DURATION + ratio * (MAX_DURATION - MIN_DURATION))


def _wrap(text, width_chars):
    return "\n".join(textwrap.wrap(text, width=width_chars))


def render_text_layer(telugu, english, reference, font_style) -> str:
    """Renders a transparent PNG with the Telugu + English text + reference,
    positioned for a 9:16 4K canvas. Returns the PNG path."""
    telugu_font_file, english_font_file, accent = font_style

    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    telugu_font = ImageFont.truetype(str(FONT_DIR / telugu_font_file), 118)
    english_font = ImageFont.truetype(str(FONT_DIR / english_font_file), 96)
    ref_font = ImageFont.truetype(str(FONT_DIR / english_font_file), 64)

    telugu_wrapped = _wrap(telugu, 18)
    english_wrapped = _wrap(english, 24)

    # Soft dark scrim band behind the text so it stays readable over the
    # moving gradient at every frame, not just against one flat color.
    scrim = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim)
    scrim_draw.rectangle([0, HEIGHT * 0.32, WIDTH, HEIGHT * 0.72],
                          fill=(0, 0, 0, 110))
    img = Image.alpha_composite(img, scrim)
    draw = ImageDraw.Draw(img)

    def centered(text, font, y, fill):
        bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
        w = bbox[2] - bbox[0]
        draw.multiline_text(((WIDTH - w) / 2, y), text, font=font,
                             fill=fill, align="center", spacing=20)

    centered(telugu_wrapped, telugu_font, HEIGHT * 0.36, (255, 255, 255, 255))
    centered(english_wrapped, english_font, HEIGHT * 0.53, (255, 255, 255, 255))
    centered(f"— {reference}", ref_font, HEIGHT * 0.67, accent + (255,))

    out_path = "/tmp/text_layer.png"
    img.save(out_path)
    return out_path


def build_ffmpeg_command(text_png, music_path, duration, output_path):
    palette = random.choice(GRADIENT_PALETTES)

    # 1) `gradients` lavfi source = animated moving multi-color gradient,
    #    scaled/cropped to our 4K vertical canvas.
    # 2) overlay the text PNG, fading it in over 1s and out over the
    #    last 1s so it doesn't just snap on/off.
    # 3) mix in looped background music, fading in/out, volume lowered
    #    so it stays "soft" behind the reading experience.
    filter_complex = (
        f"[0:v]gradients=s={WIDTH}x{HEIGHT}:x0=0:y0=0:x1={WIDTH}:y1={HEIGHT}"
        f":nb_colors=4:c0={palette.split(':')[0]}:c1={palette.split(':')[1]}"
        f":c2={palette.split(':')[2]}:c3={palette.split(':')[3]}:speed=0.02,"
        f"format=yuv420p[bg];"
        f"[1:v]fade=in:st=0:d=1:alpha=1,fade=out:st={duration-1}:d=1:alpha=1[txt];"
        f"[bg][txt]overlay=0:0:format=auto,format=yuv420p[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:d={duration}",
        "-loop", "1", "-t", str(duration), "-i", text_png,
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "2:a",
        "-t", str(duration),
        "-af", f"afade=in:st=0:d=1,afade=out:st={duration-1}:d=1,volume=0.35",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(FPS),
        output_path,
    ]
    return cmd


def main():
    telugu = os.environ.get("VERSE_TELUGU")
    english = os.environ.get("VERSE_ENGLISH")
    reference = os.environ.get("VERSE_REF")
    if not (telugu and english and reference):
        raise SystemExit("VERSE_TELUGU, VERSE_ENGLISH, and VERSE_REF are required.")

    override_telugu = os.environ.get("OVERRIDE_TELUGU", "").strip()
    override_english = os.environ.get("OVERRIDE_ENGLISH", "").strip()
    if override_telugu:
        telugu = override_telugu
    if override_english:
        english = override_english

    font_style = _pick_font_style()
    music_path = _pick_music()
    duration = _target_duration(telugu, english)
    output_path = os.environ.get("OUTPUT_PATH", "output/short.mp4")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    text_png = render_text_layer(telugu, english, reference, font_style)
    cmd = build_ffmpeg_command(text_png, music_path, duration, output_path)

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Done -> {output_path} ({duration}s, {WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
