"""Generate default overlay template PNGs with Pillow."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()


def _gradient_bar(draw: ImageDraw.Draw, x0: int, y0: int, x1: int, y1: int,
                  color_top: tuple, color_bot: tuple) -> None:
    """Draw a vertical gradient rectangle."""
    h = y1 - y0
    for i in range(h):
        ratio = i / max(h - 1, 1)
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * ratio)
        a = int(color_top[3] + (color_bot[3] - color_top[3]) * ratio)
        draw.line([(x0, y0 + i), (x1, y0 + i)], fill=(r, g, b, a))


# ------------------------------------------------------------------ 16:9 Templates

def create_youtube_frame(w: int = 1920, h: int = 1080) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Bottom gradient bar
    _gradient_bar(draw, 0, h - 120, w, h, (0, 0, 0, 0), (0, 0, 0, 200))

    # Channel name placeholder
    font = _get_font(28)
    draw.text((30, h - 80), "Channel Name", fill=(255, 255, 255, 220), font=font)

    # Thin top accent line
    draw.rectangle([0, 0, w, 3], fill=(255, 0, 80, 200))

    return img


def create_rec_frame(w: int = 1920, h: int = 1080) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Border
    bw = 3
    draw.rectangle([bw, bw, w - bw, h - bw], outline=(255, 255, 255, 150), width=bw)

    # REC indicator
    draw.ellipse([w - 80, 20, w - 56, 44], fill=(255, 0, 0, 230))
    font = _get_font(20)
    draw.text((w - 50, 20), "REC", fill=(255, 255, 255, 230), font=font)

    # Timestamp placeholder
    font_sm = _get_font(16)
    draw.text((30, h - 40), "00:00:00", fill=(255, 255, 255, 180), font=font_sm)

    # Corner marks
    mark = 30
    c = (255, 255, 255, 200)
    for corner in [(15, 15), (w - 15 - mark, 15), (15, h - 15 - mark), (w - 15 - mark, h - 15 - mark)]:
        x, y = corner
        if x < w // 2:
            draw.line([(x, y), (x + mark, y)], fill=c, width=2)
            draw.line([(x, y), (x, y + mark)], fill=c, width=2)
        else:
            draw.line([(x, y), (x + mark, y)], fill=c, width=2)
            draw.line([(x + mark, y), (x + mark, y + mark)], fill=c, width=2)

    return img


def create_minimal_border(w: int = 1920, h: int = 1080) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Elegant thin border with padding
    pad = 20
    draw.rectangle(
        [pad, pad, w - pad, h - pad],
        outline=(255, 255, 255, 120), width=2,
    )

    return img


# ------------------------------------------------------------------ 9:16 Templates

def create_shorts_frame(w: int = 1080, h: int = 1920) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Top gradient
    _gradient_bar(draw, 0, 0, w, 100, (0, 0, 0, 180), (0, 0, 0, 0))
    # Bottom gradient
    _gradient_bar(draw, 0, h - 150, w, h, (0, 0, 0, 0), (0, 0, 0, 200))

    # Channel name area
    font = _get_font(26)
    draw.text((30, h - 100), "Channel Name", fill=(255, 255, 255, 220), font=font)

    return img


def create_channel_badge(w: int = 1080, h: int = 1920) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Bottom gradient
    _gradient_bar(draw, 0, h - 200, w, h, (0, 0, 0, 0), (0, 0, 0, 180))

    # Profile circle placeholder
    cx, cy, r = 80, h - 120, 35
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(100, 100, 100, 200),
                 outline=(255, 255, 255, 200), width=2)

    # Channel name
    font = _get_font(24)
    draw.text((cx + r + 15, cy - 14), "Channel", fill=(255, 255, 255, 220), font=font)

    return img


def create_recording_vertical(w: int = 1080, h: int = 1920) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Border
    draw.rectangle([4, 4, w - 4, h - 4], outline=(255, 255, 255, 130), width=2)

    # REC dot + text
    draw.ellipse([w - 70, 20, w - 48, 42], fill=(255, 0, 0, 230))
    font = _get_font(18)
    draw.text((w - 44, 20), "REC", fill=(255, 255, 255, 230), font=font)

    # Bottom timestamp
    font_sm = _get_font(14)
    draw.text((20, h - 35), "2026.01.01", fill=(255, 255, 255, 160), font=font_sm)

    # Corner brackets
    m = 25
    c = (255, 255, 255, 180)
    for x0, y0, dx, dy in [
        (12, 12, 1, 1), (w - 12 - m, 12, -1, 1),
        (12, h - 12 - m, 1, -1), (w - 12 - m, h - 12 - m, -1, -1),
    ]:
        ex = x0 + m if dx > 0 else x0
        ey = y0 + m if dy > 0 else y0
        sx = x0 if dx > 0 else x0 + m
        sy = y0 if dy > 0 else y0 + m
        draw.line([(sx, y0 if dy > 0 else y0 + m), (sx + m, y0 if dy > 0 else y0 + m)], fill=c, width=2)
        draw.line([(x0 if dx > 0 else x0 + m, sy), (x0 if dx > 0 else x0 + m, sy + m)], fill=c, width=2)

    return img


# ------------------------------------------------------------------ Main

TEMPLATES = [
    ("youtube_frame", "YouTube Frame", "16:9", "frame", create_youtube_frame),
    ("rec_frame", "REC Frame", "16:9", "frame", create_rec_frame),
    ("minimal_border", "Minimal Border", "16:9", "frame", create_minimal_border),
    ("shorts_frame", "Shorts Frame", "9:16", "frame", create_shorts_frame),
    ("channel_badge", "Channel Badge", "9:16", "lower_third", create_channel_badge),
    ("recording_vertical", "Recording Vertical", "9:16", "frame", create_recording_vertical),
]


def main():
    project_root = Path(__file__).resolve().parent.parent
    templates_dir = project_root / "resources" / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"templates": []}

    for tid, name, aspect, category, create_fn in TEMPLATES:
        print(f"Generating: {name} ({aspect})...")
        img = create_fn()
        png_path = templates_dir / f"{tid}.png"
        img.save(str(png_path), "PNG")

        # Generate thumbnail (160px wide)
        thumb = img.copy()
        thumb.thumbnail((160, 160), Image.Resampling.LANCZOS)
        thumb_path = templates_dir / f"{tid}_thumb.png"
        thumb.save(str(thumb_path), "PNG")

        manifest["templates"].append({
            "template_id": tid,
            "name": name,
            "image_path": f"{tid}.png",
            "thumbnail_path": f"{tid}_thumb.png",
            "category": category,
            "aspect_ratio": aspect,
            "opacity": 1.0,
            "is_builtin": True,
        })

        print(f"  Saved: {png_path}")

    # Write manifest
    manifest_path = templates_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nManifest: {manifest_path}")
    print(f"Total: {len(TEMPLATES)} templates generated.")


if __name__ == "__main__":
    main()
