"""Generate FastMovieMaker app icon (.ico + .png)."""

from PIL import Image, ImageDraw, ImageFont
import math


def create_icon(size: int = 256) -> Image.Image:
    """Create FastMovieMaker icon at given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = size * 0.04
    s = size  # shorthand

    # --- Background: rounded rectangle with gradient feel ---
    # Dark navy-blue base
    bg_rect = [pad, pad, s - pad, s - pad]
    corner_r = int(s * 0.18)
    draw.rounded_rectangle(bg_rect, radius=corner_r, fill=(20, 25, 45, 255))

    # Subtle inner glow border
    draw.rounded_rectangle(
        [pad + 1, pad + 1, s - pad - 1, s - pad - 1],
        radius=corner_r,
        outline=(60, 120, 220, 100),
        width=2,
    )

    # --- Film strip bars (top & bottom) ---
    bar_h = int(s * 0.07)
    bar_y_top = int(pad)
    bar_y_bot = int(s - pad - bar_h)

    # Top bar
    draw.rounded_rectangle(
        [pad, bar_y_top, s - pad, bar_y_top + bar_h],
        radius=corner_r,
        fill=(40, 50, 80, 200),
    )
    # Bottom bar
    draw.rounded_rectangle(
        [pad, bar_y_bot, s - pad, bar_y_bot + bar_h],
        radius=corner_r,
        fill=(40, 50, 80, 200),
    )

    # Film perforations (sprocket holes)
    hole_r = int(s * 0.018)
    hole_spacing = int(s * 0.08)
    hole_y_top = bar_y_top + bar_h // 2
    hole_y_bot = bar_y_bot + bar_h // 2

    for i in range(20):
        hx = int(pad + hole_spacing * 0.7 + i * hole_spacing)
        if hx + hole_r > s - pad:
            break
        draw.ellipse(
            [hx - hole_r, hole_y_top - hole_r, hx + hole_r, hole_y_top + hole_r],
            fill=(20, 25, 45, 255),
        )
        draw.ellipse(
            [hx - hole_r, hole_y_bot - hole_r, hx + hole_r, hole_y_bot + hole_r],
            fill=(20, 25, 45, 255),
        )

    # --- Play triangle (center-left) ---
    cx = s * 0.42
    cy = s * 0.50
    tri_size = s * 0.22

    # Triangle points (play button)
    p1 = (cx - tri_size * 0.4, cy - tri_size * 0.55)
    p2 = (cx - tri_size * 0.4, cy + tri_size * 0.55)
    p3 = (cx + tri_size * 0.55, cy)

    # Glow behind triangle
    for glow in range(6, 0, -1):
        alpha = int(15 * (7 - glow))
        glow_offset = glow * 1.5
        gp1 = (p1[0] - glow_offset, p1[1] - glow_offset)
        gp2 = (p2[0] - glow_offset, p2[1] + glow_offset)
        gp3 = (p3[0] + glow_offset, p3[1])
        draw.polygon([gp1, gp2, gp3], fill=(60, 160, 255, alpha))

    # Main triangle - bright blue
    draw.polygon([p1, p2, p3], fill=(80, 180, 255, 255))

    # --- Lightning bolt (speed / "Fast") ---
    bx = s * 0.65  # bolt center x
    by = s * 0.46  # bolt center y
    bolt_h = s * 0.38
    bolt_w = s * 0.16

    bolt_points = [
        (bx - bolt_w * 0.1, by - bolt_h * 0.5),   # top
        (bx - bolt_w * 0.45, by + bolt_h * 0.05),  # upper-left notch
        (bx - bolt_w * 0.05, by - bolt_h * 0.02),  # center-left
        (bx + bolt_w * 0.1, by + bolt_h * 0.5),    # bottom
        (bx + bolt_w * 0.45, by - bolt_h * 0.05),  # lower-right notch
        (bx + bolt_w * 0.05, by + bolt_h * 0.02),  # center-right
    ]

    # Glow behind bolt
    for glow in range(5, 0, -1):
        alpha = int(20 * (6 - glow))
        scaled = []
        for px, py in bolt_points:
            dx = px - bx
            dy = py - by
            scaled.append((bx + dx * (1 + glow * 0.08), by + dy * (1 + glow * 0.08)))
        draw.polygon(scaled, fill=(255, 200, 50, alpha))

    # Main bolt - golden yellow
    draw.polygon(bolt_points, fill=(255, 210, 60, 255))
    # Bright highlight
    inner_points = []
    for px, py in bolt_points:
        dx = px - bx
        dy = py - by
        inner_points.append((bx + dx * 0.6, by + dy * 0.6))
    draw.polygon(inner_points, fill=(255, 240, 150, 200))

    # --- Speed lines (right side) ---
    for i, offset_y in enumerate([-0.18, -0.06, 0.06, 0.18]):
        line_y = int(cy + s * offset_y)
        line_x_start = int(s * 0.82)
        line_x_end = int(s * (0.88 + i % 2 * 0.04))
        line_w = max(2, int(s * 0.012))
        alpha = 180 - i * 20
        draw.rounded_rectangle(
            [line_x_start, line_y - line_w, line_x_end, line_y + line_w],
            radius=line_w,
            fill=(80, 180, 255, alpha),
        )

    return img


def main():
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Generate high-res source
    icon_256 = create_icon(256)

    # Save PNG
    png_path = os.path.join(project_root, "resources", "icon.png")
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    icon_256.save(png_path, "PNG")
    print(f"Saved: {png_path}")

    # Generate multi-size ICO (16, 24, 32, 48, 64, 128, 256)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_images = []
    for sz in sizes:
        resized = icon_256.resize((sz, sz), Image.Resampling.LANCZOS)
        ico_images.append(resized)

    ico_path = os.path.join(project_root, "resources", "icon.ico")
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(sz, sz) for sz in sizes],
        append_images=ico_images[1:],
    )
    print(f"Saved: {ico_path}")


if __name__ == "__main__":
    main()
