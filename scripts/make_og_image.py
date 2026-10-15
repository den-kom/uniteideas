#!/usr/bin/env python
"""Draw the 1200x630 social sharing image (app/static/og-image.png).

Needs Pillow and the Inter font. Re-run if the slogan or colours change.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BG, INK, MUTED, ACCENT = "#16130f", "#f4eee4", "#b9ab96", "#fdb02e"
FONTS = Path("/usr/share/fonts/opentype/inter")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def main() -> None:
    img = Image.new("RGB", (1200, 630), BG)
    draw = ImageDraw.Draw(img)
    logo = Image.open(ROOT / "app/static/logo.png").convert("RGBA").resize((96, 96), Image.LANCZOS)
    img.paste(logo, (80, 70), logo)
    draw.text((196, 84), "Unite", font=font("Inter-Bold.otf", 56), fill=INK)
    w = draw.textlength("Unite", font=font("Inter-Bold.otf", 56))
    draw.text((196 + w, 84), "Ideas", font=font("Inter-Bold.otf", 56), fill=ACCENT)
    draw.text((80, 250), "Put your idea", font=font("InterDisplay-Bold.otf", 96), fill=INK)
    draw.text((80, 360), "on the record.", font=font("InterDisplay-Bold.otf", 96), fill=INK)
    draw.text(
        (80, 520),
        "Share it. Seal the details. Get a timestamped receipt.",
        font=font("Inter-Regular.otf", 34),
        fill=MUTED,
    )
    draw.rectangle((0, 618, 1200, 630), fill=ACCENT)
    img.save(ROOT / "app/static/og-image.png", optimize=True)


if __name__ == "__main__":
    main()
