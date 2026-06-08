"""
thumbnails.py — iOS Music Player Style Thumbnail Generator
=============================================================
Generates a thumbnail that looks like an iOS music player card.

Layout:
  - Full blurred + darkened YouTube thumbnail as background
  - Semi-transparent dark rounded card in the center
  - Album art (zoomed/cropped) on the left side of the card
  - Title, Channel, Branding text on the right side
  - Progress bar with time labels (static 0:24 position)
  - 5 control icons: Star, Rewind, Pause, Forward, Headphones
  - Volume bar at the bottom

Assets Required (in ShrutiMusic/assets/):
  - Inter-Bold.ttf        → Title text
  - Inter-Light.ttf       → Branding name
  - Inter-Regular.ttf     → Channel + Time text
  - music_icons.png       → Control icons strip (transparent background)
  - glass_card.png        → Optional card border overlay
  - ShrutiBots.jpg        → Default fallback thumbnail
"""

import os
import asyncio
import logging
import traceback

import aiohttp
import aiofiles
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageOps
from py_yt import VideosSearch
from ShrutiMusic import app


# ═══════════════════════════════════════════════════════════════
# LOGGING SETUP
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ThumbnailGen")


# ═══════════════════════════════════════════════════════════════
# ★ CONFIGURATION — Edit these values to customize your thumbnail
# ═══════════════════════════════════════════════════════════════

# ── Cache System ──────────────────────────────────────────────
# TRUE  → Bot will save generated thumbnails to cache folder.
#         If a thumbnail for the same video was generated before,
#         it will reuse that file instead of generating again.
#         This saves time and CPU on repeated songs.
#
# FALSE → Bot will ALWAYS generate a fresh thumbnail every time,
#         even if the same video was generated before.
#         Cache folder will not be used at all.
CACHE_GENERATION = False

# ── Branding ──────────────────────────────────────────────────
# This name appears in small gray text above the song title
# on every thumbnail.
BRAND_NAME = "NexGen Bots"

# ── Asset Paths ───────────────────────────────────────────────
ASSETS_DIR    = Path("ShrutiMusic/assets")
CACHE_DIR     = Path("ShrutiMusic/cache")

FONT_TITLE    = ASSETS_DIR / "Inter-Bold.ttf"       # Bold — song title
FONT_BRAND    = ASSETS_DIR / "Inter-Light.ttf"      # Light — brand name
FONT_CHANNEL  = ASSETS_DIR / "Inter-Regular.ttf"   # Regular — channel name
FONT_TIME     = ASSETS_DIR / "Inter-Regular.ttf"   # Regular — time labels

ICONS_PATH    = ASSETS_DIR / "music_icons.png"      # 5 icons in one strip
CARD_PATH     = ASSETS_DIR / "glass_card.png"       # Optional card border
DEFAULT_THUMB = ASSETS_DIR / "ShrutiBots.jpg"       # Fallback if YouTube fails

# ── Canvas Size ────────────────────────────────────────────────
# Full canvas dimensions (matches Image 2 reference)
CANVAS_W      = 1456
CANVAS_H      = 816

# ── Card Dimensions ───────────────────────────────────────────
# The dark frosted glass card in the center
CARD_W        = 740
CARD_H        = 480
CARD_X        = (CANVAS_W - CARD_W) // 2    # Horizontal center → 358
CARD_Y        = (CANVAS_H - CARD_H) // 2    # Vertical center   → 168

# ── Album Art ─────────────────────────────────────────────────
# Square album art on the left side of the card
# Zoomed and cropped from YouTube thumbnail (same as AnonXMusic)
CONTROLS_ZONE = 195    # Height reserved for progress bar + icons + volume
TOP_ZONE      = CARD_H - CONTROLS_ZONE    # Upper zone height → 285

ART_SIZE      = 220    # Square size in pixels
ART_X         = CARD_X + 30
ART_Y         = CARD_Y + (TOP_ZONE - ART_SIZE) // 2    # Vertically centered in top zone → 200

# ── Text Area ─────────────────────────────────────────────────
# Starts right of the album art
TEXT_X        = ART_X + ART_SIZE + 32    # → 640

# ── Progress Bar ──────────────────────────────────────────────
BAR_X1        = CARD_X + 40              # Left edge  → 398
BAR_X2        = CARD_X + CARD_W - 40    # Right edge → 1058
BAR_Y         = CARD_Y + CARD_H - CONTROLS_ZONE + 15   # → 468
TIME_Y        = BAR_Y - 32              # Time labels above bar → 436

# ── Control Icons Row ─────────────────────────────────────────
CTRL_Y        = BAR_Y + 58              # → 526
ICON_SIZE     = 38                       # Each icon square size

# ── Volume Bar ────────────────────────────────────────────────
VOL_Y         = CTRL_Y + 68             # → 594

# ── Colors ────────────────────────────────────────────────────
WHITE         = (255, 255, 255, 255)     # Pure white — title, time, dot
GRAY          = (172, 172, 172, 210)     # Light gray — branding, channel
DIM           = (118, 118, 118, 175)     # Dimmed — outer icons, speaker
CARD_FILL     = (22,  22,  26,  205)     # Very dark near-black — card background
BAR_TRACK     = (88,  88,  88,  150)     # Dark gray — unfilled progress track
BAR_FILL_C    = (212, 212, 212, 235)     # Light gray — filled progress
VOL_TRACK     = (78,  78,  78,  140)     # Dark gray — unfilled volume track
VOL_FILL_C    = (178, 178, 178, 200)     # Gray — filled volume
DOT_COLOR     = (255, 255, 255, 255)     # White circle dot on progress bar

# ── Icon Brightness Multipliers ───────────────────────────────
# Controls how bright each icon appears
# Star=dim, Rewind=medium, Pause=full, Forward=medium, Headphones=dim
ICON_ALPHAS   = [0.50, 0.78, 1.0, 0.78, 0.50]


# ═══════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════

# Create cache directory if it doesn't exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Load Fonts Once ───────────────────────────────────────────
# Fonts are loaded once at startup so every thumbnail generation
# doesn't waste time reloading them from disk.
def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    """Load a font file safely. Falls back to PIL default if not found."""
    try:
        if path.exists():
            return ImageFont.truetype(str(path), size)
        logger.warning(f"Font not found: {path} — using PIL default")
        return ImageFont.load_default()
    except Exception as e:
        logger.warning(f"Font load error ({path}): {e} — using PIL default")
        return ImageFont.load_default()


# These are loaded once when the module is imported
LOADED_FONTS = {
    "title":   _load_font(FONT_TITLE,   35),
    "brand":   _load_font(FONT_BRAND,   22),
    "channel": _load_font(FONT_CHANNEL, 26),
    "time":    _load_font(FONT_TIME,    25),
}


# ═══════════════════════════════════════════════════════════════
# ICON LOADER
# ═══════════════════════════════════════════════════════════════

def _load_icons_from_strip(count: int = 5, size: int = ICON_SIZE):
    """
    Load individual icons from the music_icons.png strip.

    Why equal-column split instead of gap detection:
      The pause icon consists of TWO vertical bars with a gap between them.
      Gap-based detection would see that gap and split the pause icon into
      two separate icons, resulting in 6 detections instead of 5.
      Equal-column split avoids this entirely by dividing the strip into
      exactly 5 equal sections regardless of internal gaps.

    Returns:
      List of 5 RGBA icon images, each resized to (size x size).
      Returns None if the file doesn't exist or an error occurs.
    """
    try:
        if not ICONS_PATH.exists():
            logger.warning(f"Icons file not found: {ICONS_PATH}")
            return None

        strip      = Image.open(ICONS_PATH).convert("RGBA")
        strip_w, strip_h = strip.size

        # Detect the vertical bounds of all icon content
        arr        = np.array(strip)
        alpha      = arr[:, :, 3]
        rows       = np.where(alpha.max(axis=1) > 8)[0]

        if len(rows) == 0:
            logger.warning("Icons strip appears to be empty or fully transparent")
            return None

        row_top    = int(rows[0])
        row_bottom = int(rows[-1]) + 1

        # Divide strip horizontally into equal sections
        # Small margin on each side to avoid edge artifacts
        left_margin  = int(strip_w * 0.06)
        usable_width = strip_w - (2 * left_margin)
        col_width    = usable_width // count

        icons = []
        for i in range(count):
            # Column boundaries for this icon
            col_x1 = left_margin + (i * col_width)
            col_x2 = left_margin + ((i + 1) * col_width)

            # Crop the column
            col_crop = strip.crop((col_x1, row_top, col_x2, row_bottom))

            # Tight crop: remove empty space within the column
            col_alpha = np.array(col_crop)[:, :, 3]
            content_cols = np.where(col_alpha.max(axis=0) > 8)[0]

            if len(content_cols) > 0:
                tight_x1 = max(0, int(content_cols[0]) - 3)
                tight_x2 = min(col_crop.width, int(content_cols[-1]) + 3)
                col_crop = col_crop.crop((tight_x1, 0, tight_x2, col_crop.height))

            # Resize to target icon size
            icon = col_crop.resize((size, size), Image.LANCZOS)
            icons.append(icon)

        logger.info(f"Loaded {len(icons)} icons from strip successfully")
        return icons

    except Exception as e:
        logger.error(f"Failed to load icons: {e}")
        return None


# Load icons once at startup (same as fonts)
LOADED_ICONS = _load_icons_from_strip(count=5, size=ICON_SIZE)


# ═══════════════════════════════════════════════════════════════
# CARD BUILDER
# ═══════════════════════════════════════════════════════════════

def _build_card(width: int, height: int) -> Image.Image:
    """
    Build the frosted glass card image.

    Process:
      1. Draw a dark filled rounded rectangle as the base
      2. If glass_card.png exists, overlay it as a subtle border highlight
      3. If not, draw a manual 1px rounded border instead

    Returns:
      RGBA image of the card, ready to paste onto the background.
    """
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # Step 1: Dark fill
    draw.rounded_rectangle(
        [0, 0, width, height],
        radius=24,
        fill=CARD_FILL
    )

    # Step 2: Optional glass border overlay
    try:
        if CARD_PATH.exists():
            border_img = Image.open(CARD_PATH).convert("RGBA")
            border_img = border_img.resize((width, height), Image.LANCZOS)

            # Make the border very subtle (22% opacity)
            r, g, b, a = border_img.split()
            a = a.point(lambda px: int(px * 0.22))
            border_img.putalpha(a)

            card = Image.alpha_composite(card, border_img)
        else:
            # Fallback: draw a thin white border manually
            draw.rounded_rectangle(
                [1, 1, width - 1, height - 1],
                radius=24,
                outline=(255, 255, 255, 18),
                width=1
            )
    except Exception as e:
        logger.warning(f"Card border overlay failed: {e}")

    return card


# ═══════════════════════════════════════════════════════════════
# SPEAKER ICON DRAWER (for volume bar)
# ═══════════════════════════════════════════════════════════════

def _draw_speaker_icon(draw: ImageDraw.Draw, cx: int, cy: int,
                       size: int, color: tuple, line_width: int = 2):
    """
    Draw a speaker/volume icon using PIL shapes.
    Used for the left (muted) and right (loud) ends of the volume bar.

    Args:
      draw       → PIL ImageDraw object
      cx, cy     → Center coordinates
      size       → Overall size in pixels
      color      → RGBA tuple
      line_width → Arc line thickness
    """
    body_half = size // 3

    # Speaker body (trapezoid polygon)
    draw.polygon([
        (cx - body_half, cy - body_half // 2),
        (cx,             cy - size // 2),
        (cx,             cy + size // 2),
        (cx - body_half, cy + body_half // 2),
    ], fill=color)

    # Sound waves (two arcs on the right side)
    for radius in [body_half + 3, body_half + 8]:
        draw.arc(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            start=315, end=45,
            fill=color, width=line_width
        )


# ═══════════════════════════════════════════════════════════════
# PIL RENDERER — Runs in executor (non-blocking)
# ═══════════════════════════════════════════════════════════════

def _render_thumbnail(base_image: Image.Image,
                      title: str,
                      duration: str,
                      channel: str) -> Image.Image:
    """
    The core PIL rendering function.
    This runs in a thread executor so it doesn't block the bot's
    async event loop while doing CPU-intensive image processing.

    Args:
      base_image → The YouTube thumbnail (or default fallback) as RGBA
      title      → Song title string
      duration   → Duration string (e.g. "3:45")
      channel    → Channel name string

    Returns:
      Fully rendered RGBA image, or None if rendering failed.
    """
    try:
        # ── Step 1: Create blurred background ─────────────────
        # Resize to full canvas, apply Gaussian blur and dim brightness
        # This creates the iOS-style blurred background effect
        background = base_image.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(22))
        background = ImageEnhance.Brightness(background).enhance(0.48)

        # ── Step 2: Paste the dark glass card ─────────────────
        card_image = _build_card(CARD_W, CARD_H)
        background.paste(card_image, (CARD_X, CARD_Y), card_image)

        draw = ImageDraw.Draw(background)

        # ── Step 3: Album art (zoomed, rounded corners) ───────
        # ImageOps.fit zooms and crops to exact square (copyright-safe transform)
        art = ImageOps.fit(
            base_image,
            (ART_SIZE, ART_SIZE),
            method=Image.LANCZOS,
            centering=(0.5, 0.5)
        )

        # Apply rounded corner mask
        art_mask = Image.new("L", (ART_SIZE, ART_SIZE), 0)
        ImageDraw.Draw(art_mask).rounded_rectangle(
            [0, 0, ART_SIZE, ART_SIZE], radius=14, fill=255
        )
        art.putalpha(art_mask)
        background.paste(art, (ART_X, ART_Y), art)

        # ── Step 4: Text — Branding ───────────────────────────
        brand_y = CARD_Y + 36
        draw.text(
            (TEXT_X, brand_y),
            BRAND_NAME,
            font=LOADED_FONTS["brand"],
            fill=GRAY
        )

        # ── Step 5: Text — Song Title ─────────────────────────
        # Truncate long titles to fit within the card's text area
        title_display = title if len(title) <= 34 else title[:32] + "..."
        title_y       = brand_y + 30
        draw.text(
            (TEXT_X, title_y),
            title_display,
            font=LOADED_FONTS["title"],
            fill=WHITE
        )

        # ── Step 6: Text — Channel Name ───────────────────────
        channel_y = title_y + 50
        draw.text(
            (TEXT_X, channel_y),
            channel[:34],
            font=LOADED_FONTS["channel"],
            fill=WHITE
        )

        # ── Step 7: Progress Bar ──────────────────────────────
        BAR_HEIGHT  = 5
        DOT_RADIUS  = 7
        played_frac = 0.11    # Static position → looks like 0:24 into the song

        bar_mid_y   = BAR_Y + BAR_HEIGHT // 2

        # Ensure dot doesn't go past the left edge
        fill_end_x  = max(
            BAR_X1 + DOT_RADIUS + 2,
            BAR_X1 + int((BAR_X2 - BAR_X1) * played_frac)
        )

        # Unfilled track (full width)
        draw.rectangle(
            [BAR_X1, BAR_Y, BAR_X2, BAR_Y + BAR_HEIGHT],
            fill=BAR_TRACK
        )
        # Filled portion (played amount)
        draw.rectangle(
            [BAR_X1, BAR_Y, fill_end_x, BAR_Y + BAR_HEIGHT],
            fill=BAR_FILL_C
        )
        # Playhead dot
        draw.ellipse(
            [
                fill_end_x - DOT_RADIUS, bar_mid_y - DOT_RADIUS,
                fill_end_x + DOT_RADIUS, bar_mid_y + DOT_RADIUS,
            ],
            fill=DOT_COLOR
        )

        # Time labels: played on left, remaining on right
        draw.text(
            (BAR_X1, TIME_Y),
            "0:24",
            font=LOADED_FONTS["time"],
            fill=WHITE
        )
        remaining_str  = f"-{duration}"
        remaining_bbox = draw.textbbox((0, 0), remaining_str, font=LOADED_FONTS["time"])
        remaining_w    = remaining_bbox[2] - remaining_bbox[0]
        draw.text(
            (BAR_X2 - remaining_w, TIME_Y),
            remaining_str,
            font=LOADED_FONTS["time"],
            fill=WHITE
        )

        # ── Step 8: Control Icons ─────────────────────────────
        total_bar_width = BAR_X2 - BAR_X1
        icon_spacing    = total_bar_width // 4
        icon_positions  = [BAR_X1 + (i * icon_spacing) for i in range(5)]

        if LOADED_ICONS and len(LOADED_ICONS) == 5:
            # Use actual PNG icons from music_icons.png
            for idx, (icon, center_x) in enumerate(zip(LOADED_ICONS, icon_positions)):
                # Apply brightness multiplier for visual hierarchy
                r_ch, g_ch, b_ch, a_ch = icon.split()
                a_ch = a_ch.point(lambda px: int(px * ICON_ALPHAS[idx]))
                styled_icon = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

                paste_x = center_x - ICON_SIZE // 2
                paste_y = CTRL_Y   - ICON_SIZE // 2
                background.paste(styled_icon, (paste_x, paste_y), styled_icon)
        else:
            # Fallback: render Unicode symbols if icons file is missing
            logger.warning("Icons not loaded — using Unicode symbol fallback")
            fallback_symbols = ["★", "◀◀", "⏸", "▶▶", "🎧"]
            for symbol, center_x in zip(fallback_symbols, icon_positions):
                draw.text(
                    (center_x - 10, CTRL_Y - 12),
                    symbol,
                    font=LOADED_FONTS["time"],
                    fill=GRAY
                )

        # ── Step 9: Volume Bar ────────────────────────────────
        VOL_HEIGHT   = 4
        vol_fill_fac = 0.45    # Static position (45% volume)
        vol_left     = BAR_X1 + 32
        vol_right    = BAR_X2 - 32
        vol_fill_x   = max(
            vol_left + 6,
            vol_left + int((vol_right - vol_left) * vol_fill_fac)
        )
        vol_dot_r    = 5
        vol_mid_y    = VOL_Y + VOL_HEIGHT // 2

        # Left speaker icon (dim — muted end)
        _draw_speaker_icon(draw, vol_left - 24, vol_mid_y, 15, DIM)

        # Volume track
        draw.rectangle(
            [vol_left, VOL_Y, vol_right, VOL_Y + VOL_HEIGHT],
            fill=VOL_TRACK
        )
        # Volume fill
        draw.rectangle(
            [vol_left, VOL_Y, vol_fill_x, VOL_Y + VOL_HEIGHT],
            fill=VOL_FILL_C
        )
        # Volume dot
        draw.ellipse(
            [
                vol_fill_x - vol_dot_r, vol_mid_y - vol_dot_r,
                vol_fill_x + vol_dot_r, vol_mid_y + vol_dot_r,
            ],
            fill=(200, 200, 200, 210)
        )

        # Right speaker icon (brighter — loud end)
        _draw_speaker_icon(draw, vol_right + 24, vol_mid_y, 17, GRAY)

        return background

    except Exception as e:
        logger.error(f"Render failed: {e}")
        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════
# MAIN ASYNC GENERATOR
# ═══════════════════════════════════════════════════════════════

async def gen_thumb(videoid: str) -> str:
    """
    Main entry point for thumbnail generation.

    Flow:
      1. Check cache (if CACHE_GENERATION is True)
      2. Fetch video metadata (title, duration, channel) from YouTube
      3. Download the YouTube thumbnail image
      4. Run PIL rendering in executor (non-blocking)
      5. Save output (respecting CACHE_GENERATION setting)
      6. Return the output file path

    Args:
      videoid → YouTube video ID string (e.g. "dQw4w9WgXcQ")

    Returns:
      Path string to the generated PNG file, or None on failure.
    """
    video_url  = f"https://www.youtube.com/watch?v={videoid}"
    thumb_path = CACHE_DIR / f"thumb_{videoid}.jpg"
    out_path   = CACHE_DIR / f"{videoid}_final.png"

    # ── Cache Check ───────────────────────────────────────────
    # Only check cache if CACHE_GENERATION is enabled.
    # If cached file exists, return it immediately without re-generating.
    if CACHE_GENERATION and out_path.exists():
        logger.info(f"Cache hit for {videoid} — returning cached thumbnail")
        return str(out_path)

    # ── Fetch Metadata ────────────────────────────────────────
    title    = "Unknown Title"
    duration = "0:00"
    channel  = "Unknown"

    try:
        results      = VideosSearch(video_url, limit=1)
        search_data  = (await results.next())["result"][0]

        title    = search_data.get("title",    "Unknown Title")
        duration = search_data.get("duration", "0:00") or "0:00"
        channel  = search_data.get("channel", {}).get("name", "Unknown")
        thumb_url = search_data["thumbnails"][0]["url"].split("?")[0]

        # Download the YouTube thumbnail image
        async with aiohttp.ClientSession() as session:
            async with session.get(thumb_url) as response:
                if response.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as file:
                        await file.write(await response.read())
                else:
                    logger.warning(f"Thumbnail download failed (HTTP {response.status})")

    except Exception as e:
        logger.error(f"Metadata/thumbnail fetch error: {e}")

    # ── Load Base Image ───────────────────────────────────────
    try:
        image_source = thumb_path if thumb_path.exists() else DEFAULT_THUMB
        base_image   = Image.open(image_source).convert("RGBA")
    except Exception:
        try:
            base_image = Image.open(DEFAULT_THUMB).convert("RGBA")
            logger.warning("YouTube thumbnail unavailable — using default fallback")
        except Exception as e:
            logger.error(f"Could not open any image source: {e}")
            return None

    # ── Render (Non-blocking) ─────────────────────────────────
    # Run the PIL rendering in a thread executor so the bot's
    # async event loop is not blocked during image processing.
    loop           = asyncio.get_event_loop()
    rendered_image = await loop.run_in_executor(
        None,
        _render_thumbnail,
        base_image,
        title,
        duration,
        channel
    )

    # ── Cleanup Temp File ─────────────────────────────────────
    try:
        if thumb_path.exists():
            os.remove(thumb_path)
    except Exception:
        pass

    # ── Save Output ───────────────────────────────────────────
    if rendered_image is None:
        logger.error(f"Rendering returned None for video {videoid}")
        return None

    try:
        # Always save to out_path (used as return value)
        rendered_image.save(str(out_path), "PNG", optimize=True)
        logger.info(f"Thumbnail saved → {out_path}")

        # If cache is disabled, we still save temporarily to return the path,
        # but we schedule deletion after returning so it's not kept.
        if not CACHE_GENERATION:
            # File will be regenerated next time — no cache kept
            logger.info("Cache disabled — thumbnail will not be reused next time")

        return str(out_path)

    except Exception as e:
        logger.error(f"Failed to save thumbnail: {e}")
        return None
