#!/usr/bin/env python3
"""Generate the Open Graph image for https://vpngate.hizb.or.id/.

Renders 1200x630 (the size declared in index.html's og:image tags) with the
same design tokens as the site: pure-black canvas, no rounded corners, Roboto
uppercase display type, muted #bbbbbb secondary text, and the full-width
BMW-M-style tri-colour bar at the bottom.

Geometry (measured from the previous 1.0 artwork so the family resemblance
survives a version bump):
    logo        68px square at x=126, y=164
    title       baseline centred on the logo, starts at x=260
    sub-title   30px muted, left margin x=96
    info line   23px muted, left margin x=96
    M bar       24px full width, bottom edge y=630

Usage:  python3 tools/make-og-image.py [-o og-image.png]
Requires: Pillow, and Roboto TTFs (Debian/Ubuntu: fonts-roboto).
"""

from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# --- design tokens (must match index.html :root) ---------------------------
CANVAS = (0, 0, 0)
CARD = (26, 26, 26)
ELEV = (38, 38, 38)
TEXT = (255, 255, 255)
MUTED = (187, 187, 187)
HAIR = (28, 28, 28)
M1 = (0, 102, 177)
M2 = (28, 105, 212)
M3 = (226, 39, 24)

W, H = 1200, 630
SS = 2  # supersample factor for crisp text edges

FONT_DIR_CANDIDATES = [
    "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF",
    "/usr/share/fonts/truetype/roboto",
    "/usr/share/fonts/TTF",
]
FONT_FALLBACK = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
]


def find_font(name: str) -> str:
    for d in FONT_DIR_CANDIDATES + FONT_FALLBACK:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise SystemExit(f"font not found: {name}")


def load(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(find_font(f"Roboto-{weight}.ttf"), size * SS)


def tracked(draw, xy, text, font, fill, tracking=0.0):
    """Draw uppercase display text with letter-spacing, like the site's CSS.

    Coordinates are passed through untouched — callers chaining segments must
    feed the returned x back in directly (it is already in canvas units).
    """
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking * SS
    return x


def draw_logo(d: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """The app icon, drawn to match the inline SVG in index.html."""
    s = size / 64.0
    d.rectangle([x, y, x + size, y + size], fill=CANVAS)
    # camera-ish frame: outer 30x30 at (17,9), stroke 4
    d.rectangle([x + 17 * s, y + 9 * s, x + 47 * s, y + 39 * s],
                outline=TEXT, width=max(1, round(4 * s)))
    # inner 16x16 at (24,16), stroke 3
    d.rectangle([x + 24 * s, y + 16 * s, x + 40 * s, y + 32 * s],
                outline=TEXT, width=max(1, round(3 * s)))
    # lens dot r=3.5 at (32,24)
    cx, cy, r = x + 32 * s, y + 24 * s, 3.5 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=TEXT)
    # M bar inside the icon
    bar_y = y + 58 * s
    d.rectangle([x, bar_y, x + 22 * s, y + 64 * s], fill=M1)
    d.rectangle([x + 22 * s, bar_y, x + 43 * s, y + 64 * s], fill=M2)
    d.rectangle([x + 43 * s, bar_y, x + 64 * s, y + 64 * s], fill=M3)


def render(path: str) -> None:
    img = Image.new("RGB", (W * SS, H * SS), CANVAS)
    d = ImageDraw.Draw(img)

    logo_x, logo_y, logo_s = 126, 164, 68
    draw_logo(d, logo_x * SS, logo_y * SS, logo_s * SS)

    # --- title, INK centred against the logo --------------------------------
    # getbbox() tells exactly where the glyphs land relative to the anchor,
    # so the visual caps centre on the logo regardless of font metrics.
    f_title = load(60, "Bold")
    title = "VPN GATE CLIENT"
    _x0, y0, _x1, y1 = f_title.getbbox(title)
    ink_h = (y1 - y0) / SS
    ty = (logo_y + logo_s // 2) - ink_h / 2 - y0 / SS
    tracked(d, (260 * SS, ty * SS), title, f_title, TEXT, tracking=0.6)

    # --- sub-title ---------------------------------------------------------
    f_sub = load(29, "Regular")
    sub = "Unofficial open-source GUI for free VPN Gate servers"
    asc, desc = f_sub.getmetrics()
    tracked(d, (96 * SS, 250 * SS), sub, f_sub, MUTED, tracking=1.0)

    # --- 1.1 release strip -------------------------------------------------
    box_x, box_y, box_h = 96, 318, 56
    d.rectangle([box_x * SS, box_y * SS, 1080 * SS, (box_y + box_h) * SS],
                fill=ELEV)
    d.rectangle([box_x * SS, box_y * SS,
                 (box_x + 4) * SS, (box_y + box_h) * SS], fill=M2)
    d.rectangle([box_x * SS, box_y * SS,
                 1080 * SS, (box_y + 1) * SS], fill=HAIR)
    d.rectangle([box_x * SS, (box_y + box_h - 1) * SS,
                 1080 * SS, (box_y + box_h) * SS], fill=HAIR)

    f_tag = load(19, "Bold")
    f_feat = load(19, "Medium")
    ty = box_y + 18
    end_x = 1080 - 24
    right = "ONE-CLICK CONNECT · VERIFIED IP"
    rw = sum(d.textlength(c, font=f_feat) for c in right) + 1.2 * SS * len(right)
    tracked(d, ((box_x + 24) * SS, ty * SS), "V1.1-1  ·  IPv6 LEAK BLOCKED",
            f_tag, TEXT, tracking=1.2)
    tracked(d, ((end_x * SS) - rw, ty * SS), right, f_feat, MUTED,
            tracking=1.2)

    # --- info line ---------------------------------------------------------
    f_info = load(22, "Regular")
    tracked(d, (96 * SS, 388 * SS),
            "vpngate.hizb.or.id   ·   Download .deb   ·   MIT License",
            f_info, MUTED, tracking=0.6)

    # --- full-width M bar (drawn at 1x after downscale: hard edges, no
    # supersample ringing) --------------------------------------------------
    img = img.resize((W, H), Image.LANCZOS)
    d1 = ImageDraw.Draw(img)
    bar_top = H - 24
    third = W // 3
    d1.rectangle([0, bar_top, third, H], fill=M1)
    d1.rectangle([third, bar_top, 2 * third, H], fill=M2)
    d1.rectangle([2 * third, bar_top, W, H], fill=M3)

    img.save(path, "PNG", optimize=True)
    print(f"wrote {path} ({os.path.getsize(path)} bytes, {W}x{H})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default="og-image.png")
    args = ap.parse_args()
    render(args.output)


if __name__ == "__main__":
    sys.exit(main())