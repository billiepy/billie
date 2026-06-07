# Copyright (c) 2025 Nand Yaduwanshi <NoxxOP>
# Location: Supaul, Bihar
#
# All rights reserved.
#
# This code is the intellectual property of Nand Yaduwanshi.
# You are not allowed to copy, modify, redistribute, or use this
# code for commercial or personal projects without explicit permission.
#
# Allowed:
# - Forking for personal learning
# - Submitting improvements via pull requests
#
# Not Allowed:
# - Claiming this code as your own
# - Re-uploading without credit or permission
# - Selling or using commercially
#
# Contact for permissions:
# Email: badboy809075@gmail.com
#
# ATLEAST GIVE CREDITS IF YOU STEALING :
# ELSE NO FURTHER PUBLIC THUMBNAIL UPDATES

import os
import math
import traceback
import aiohttp
import aiofiles
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageOps
from py_yt import VideosSearch
from ShrutiMusic import app

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# ASSETS
# ═══════════════════════════════════════════════════════════════
FONT_TITLE    = "ShrutiMusic/assets/Inter-Bold.ttf"
FONT_BRAND    = "ShrutiMusic/assets/Inter-Light.ttf"
FONT_CHANNEL  = "ShrutiMusic/assets/Inter-Regular.ttf"
FONT_TIME     = "ShrutiMusic/assets/Inter-Regular.ttf"
ICONS_PATH    = "ShrutiMusic/assets/music_icons.png"
CARD_PATH     = "ShrutiMusic/assets/glass_card.png"
DEFAULT_THUMB = "ShrutiMusic/assets/ShrutiBots.jpg"

# ═══════════════════════════════════════════════════════════════
# BRANDING — Apna naam yahan daalo
# ═══════════════════════════════════════════════════════════════
BRAND_NAME = "NexGen Bots"

# ═══════════════════════════════════════════════════════════════
# CANVAS & LAYOUT
# ═══════════════════════════════════════════════════════════════
W, H         = 1280, 720

CARD_W       = 730
CARD_H       = 450
CARD_X       = (W - CARD_W) // 2
CARD_Y       = (H - CARD_H) // 2

ART_SIZE     = 210
ART_PADDING  = 28
ART_X        = CARD_X + ART_PADDING
ART_Y        = CARD_Y + (CARD_H - ART_SIZE) // 2

TEXT_X       = ART_X + ART_SIZE + 32
TEXT_MAX_W   = (CARD_X + CARD_W) - TEXT_X - 24

BAR_X1       = CARD_X + 36
BAR_X2       = CARD_X + CARD_W - 36
BAR_Y        = CARD_Y + CARD_H - 162
TIME_Y       = BAR_Y - 30
CTRL_Y       = BAR_Y + 52
VOL_Y        = CTRL_Y + 62

ICON_SIZE    = 38   # Each icon pasted size

# ═══════════════════════════════════════════════════════════════
# COLORS
# ═══════════════════════════════════════════════════════════════
WHITE        = (255, 255, 255, 255)
GRAY         = (180, 180, 180, 210)
DIM          = (120, 120, 120, 180)
CARD_FILL    = (28,  28,  32,  188)
CARD_BORDER  = (255, 255, 255, 22)
BAR_TRACK    = (95,  95,  95,  155)
BAR_FILL     = (218, 218, 218, 230)
VOL_TRACK    = (85,  85,  85,  140)
VOL_FILL     = (185, 185, 185, 200)
DOT_COLOR    = (255, 255, 255, 255)


# ═══════════════════════════════════════════════════════════════
# ICON LOADER — music_icons.png se auto-detect karke crop karo
# ═══════════════════════════════════════════════════════════════

def _load_icons(path: str, count: int = 5, size: int = ICON_SIZE):
    """
    Transparent PNG se icons auto-detect karo.
    Returns list of RGBA icon images, each resized to (size x size).
    """
    try:
        strip = Image.open(path).convert("RGBA")
        arr   = np.array(strip)
        alpha = arr[:, :, 3]

        # Non-transparent columns find karo
        cols = np.where(alpha.max(axis=0) > 8)[0]
        if len(cols) == 0:
            return None

        # Gaps dhundo (icons ke beech)
        gaps   = []
        prev   = cols[0]
        for c in cols[1:]:
            if c - prev > 15:
                gaps.append((prev, c))
            prev = c

        starts = [cols[0]] + [g[1] for g in gaps]
        ends   = [g[0] for g in gaps] + [cols[-1]]

        if len(starts) < count:
            return None

        icons = []
        rows  = np.where(alpha.max(axis=1) > 8)[0]
        row_s = int(rows[0])
        row_e = int(rows[-1]) + 1

        for i in range(count):
            x1 = max(0, int(starts[i]) - 5)
            x2 = min(strip.width, int(ends[i]) + 5)
            icon = strip.crop((x1, row_s, x2, row_e))
            icon = icon.resize((size, size), Image.LANCZOS)
            icons.append(icon)

        return icons

    except Exception as e:
        print(f"[icon load] {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# CARD LOADER — glass_card.png use karo ya PIL fallback
# ═══════════════════════════════════════════════════════════════

def _make_card(w: int, h: int) -> Image.Image:
    """
    glass_card.png available hai toh use karo,
    warna PIL se dark frosted card banao.
    """
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # Dark fill
    draw.rounded_rectangle([0, 0, w, h], radius=22, fill=CARD_FILL)

    # Try overlay glass_card.png border
    try:
        border = Image.open(CARD_PATH).convert("RGBA").resize((w, h), Image.LANCZOS)
        # Border image ko dim karke overlay karo
        r, g, b, a = border.split()
        a = a.point(lambda x: int(x * 0.3))
        border.putalpha(a)
        card = Image.alpha_composite(card, border)
    except Exception:
        # Fallback: PIL se subtle border
        draw2 = ImageDraw.Draw(card)
        draw2.rounded_rectangle(
            [1, 1, w-1, h-1], radius=22,
            outline=CARD_BORDER, width=1
        )

    return card


# ═══════════════════════════════════════════════════════════════
# SPEAKER ICON (volume bar ke liye)
# ═══════════════════════════════════════════════════════════════

def _draw_speaker(draw, cx, cy, sz, color, lw=2):
    b = sz // 3
    draw.polygon([
        (cx-b, cy-b//2), (cx, cy-sz//2),
        (cx,   cy+sz//2), (cx-b, cy+b//2)
    ], fill=color)
    for r in [b+3, b+8]:
        draw.arc(
            [cx-r, cy-r, cx+r, cy+r],
            start=315, end=45, fill=color, width=lw
        )


# ═══════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ═══════════════════════════════════════════════════════════════

async def gen_thumb(videoid: str):
    url        = f"https://www.youtube.com/watch?v={videoid}"
    thumb_path = CACHE_DIR / f"thumb_{videoid}.jpg"
    out_path   = CACHE_DIR / f"{videoid}_final.png"

    # ── Fetch metadata ─────────────────────────────────────────
    title    = "Unknown Title"
    duration = "0:00"
    channel  = "Unknown"

    try:
        results = VideosSearch(url, limit=1)
        result  = (await results.next())["result"][0]
        title    = result.get("title",    "Unknown Title")
        duration = result.get("duration", "0:00") or "0:00"
        channel  = result.get("channel", {}).get("name", "Unknown")
        thumburl = result["thumbnails"][0]["url"].split("?")[0]

        async with aiohttp.ClientSession() as session:
            async with session.get(thumburl) as resp:
                if resp.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await resp.read())
    except Exception as e:
        print(f"[gen_thumb fetch] {e}")

    # ── Open base image ────────────────────────────────────────
    try:
        src_path = thumb_path if thumb_path.exists() else DEFAULT_THUMB
        base = Image.open(src_path).convert("RGBA")
    except Exception:
        try:
            base = Image.open(DEFAULT_THUMB).convert("RGBA")
        except Exception:
            return None

    try:
        # ── Background — blurred + darkened ───────────────────
        bg = base.resize((W, H), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(28))
        bg = ImageEnhance.Brightness(bg).enhance(0.35)

        # ── Glass card ─────────────────────────────────────────
        card = _make_card(CARD_W, CARD_H)
        bg.paste(card, (CARD_X, CARD_Y), card)

        draw = ImageDraw.Draw(bg)

        # ── Album art — zoomed + rounded square ───────────────
        art = ImageOps.fit(
            base, (ART_SIZE, ART_SIZE),
            method=Image.LANCZOS, centering=(0.5, 0.5)
        )
        art_mask = Image.new("L", (ART_SIZE, ART_SIZE), 0)
        ImageDraw.Draw(art_mask).rounded_rectangle(
            [0, 0, ART_SIZE, ART_SIZE], radius=12, fill=255
        )
        art.putalpha(art_mask)
        bg.paste(art, (ART_X, ART_Y), art)

        # ── Fonts ──────────────────────────────────────────────
        try:
            f_title   = ImageFont.truetype(FONT_TITLE,   36)
            f_brand   = ImageFont.truetype(FONT_BRAND,   21)
            f_channel = ImageFont.truetype(FONT_CHANNEL, 26)
            f_time    = ImageFont.truetype(FONT_TIME,    25)
        except Exception:
            f_title = f_brand = f_channel = f_time = ImageFont.load_default()

        # ── Branding ───────────────────────────────────────────
        brand_y = CARD_Y + 36
        draw.text((TEXT_X, brand_y), BRAND_NAME, font=f_brand, fill=GRAY)

        # ── Title (truncated) ──────────────────────────────────
        title_clean = title if len(title) <= 38 else title[:36] + "..."
        title_y     = brand_y + 32
        draw.text((TEXT_X, title_y), title_clean, font=f_title, fill=WHITE)

        # ── Channel ────────────────────────────────────────────
        ch_y = title_y + 52
        draw.text((TEXT_X, ch_y), channel[:34], font=f_channel, fill=WHITE)

        # ── Progress bar ───────────────────────────────────────
        BAR_H       = 4
        DOT_R       = 6
        played_frac = 0.11
        bar_mid     = BAR_Y + BAR_H // 2
        fill_x      = max(BAR_X1 + 2, BAR_X1 + int((BAR_X2 - BAR_X1) * played_frac))

        # Track
        draw.rounded_rectangle(
            [BAR_X1, BAR_Y, BAR_X2, BAR_Y + BAR_H],
            radius=2, fill=BAR_TRACK
        )
        # Filled portion
        draw.rounded_rectangle(
            [BAR_X1, BAR_Y, fill_x, BAR_Y + BAR_H],
            radius=2, fill=BAR_FILL
        )
        # Dot
        draw.ellipse(
            [fill_x-DOT_R, bar_mid-DOT_R, fill_x+DOT_R, bar_mid+DOT_R],
            fill=DOT_COLOR
        )

        # Time labels
        draw.text((BAR_X1, TIME_Y), "0:24", font=f_time, fill=WHITE)
        dur_str = f"-{duration}"
        dur_w   = draw.textbbox((0,0), dur_str, font=f_time)[2]
        draw.text((BAR_X2 - dur_w, TIME_Y), dur_str, font=f_time, fill=WHITE)

        # ── Control icons ──────────────────────────────────────
        icons    = _load_icons(ICONS_PATH, count=5, size=ICON_SIZE)
        total_w  = BAR_X2 - BAR_X1
        spacing  = total_w // 4
        ctrl_pos = [BAR_X1 + i * spacing for i in range(5)]

        if icons and len(icons) == 5:
            # Use actual PNG icons
            alphas = [0.55, 0.80, 1.0, 0.80, 0.55]  # dim outer, bright center
            for i, (icon, px) in enumerate(zip(icons, ctrl_pos)):
                # Tint with alpha
                r2, g2, b2, a2 = icon.split()
                a2 = a2.point(lambda x: int(x * alphas[i]))
                icon2 = Image.merge("RGBA", (r2, g2, b2, a2))
                ix = px - ICON_SIZE // 2
                iy = CTRL_Y - ICON_SIZE // 2
                bg.paste(icon2, (ix, iy), icon2)
        else:
            # Fallback — simple text symbols
            symbols = ["★", "◀◀", "⏸", "▶▶", "🎧"]
            for sym, px in zip(symbols, ctrl_pos):
                draw.text((px - 10, CTRL_Y - 14), sym, font=f_time, fill=GRAY)

        # ── Volume bar ─────────────────────────────────────────
        VOL_H    = 3
        vol_fac  = 0.45
        vol_x1   = BAR_X1 + 30
        vol_x2   = BAR_X2 - 30
        vol_fill = max(vol_x1 + 2, vol_x1 + int((vol_x2 - vol_x1) * vol_fac))
        vol_dot  = 5
        vol_mid  = VOL_Y + VOL_H // 2

        _draw_speaker(draw, vol_x1 - 22, vol_mid, 14, DIM)

        draw.rounded_rectangle(
            [vol_x1, VOL_Y, vol_x2, VOL_Y+VOL_H],
            radius=1, fill=VOL_TRACK
        )
        draw.rounded_rectangle(
            [vol_x1, VOL_Y, vol_fill, VOL_Y+VOL_H],
            radius=1, fill=VOL_FILL
        )
        draw.ellipse(
            [vol_fill-vol_dot, vol_mid-vol_dot,
             vol_fill+vol_dot, vol_mid+vol_dot],
            fill=(200, 200, 200, 210)
        )
        _draw_speaker(draw, vol_x2 + 22, vol_mid, 16, GRAY)

        # ── Save ───────────────────────────────────────────────
        bg.save(str(out_path), "PNG", optimize=True)

        try:
            if thumb_path.exists():
                os.remove(thumb_path)
        except Exception:
            pass

        return str(out_path)

    except Exception as e:
        print(f"[gen_thumb render] {e}")
        traceback.print_exc()
        return None
