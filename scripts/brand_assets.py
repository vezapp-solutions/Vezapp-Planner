"""Derive favicon, app icons and the colour palette from the copied Vezapp logo.

Run from the repo root with the backend virtualenv (needs Pillow):
    backend\\.venv\\Scripts\\python.exe scripts\\brand_assets.py

The source logo (frontend/public/brand/vezapp-logo.png) is only read, never modified.
"""
import colorsys
from collections import Counter
from pathlib import Path

from PIL import Image

BRAND = Path(__file__).resolve().parent.parent / "frontend" / "public" / "brand"
SOURCE = BRAND / "vezapp-logo.png"


def luminance(rgb):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hex_of(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def flatten_on_white(image):
    """The logo is a transparent PNG; palette and icons are worked out on white."""
    rgba = image.convert("RGBA")
    page = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    page.alpha_composite(rgba)
    return page.convert("RGB")


def dominant_colours(image):
    """Most common quantised colours that are neither near-white nor near-grey-white."""
    small = image.convert("RGB").resize((320, int(320 * image.height / image.width)))
    counts = Counter()
    for r, g, b in small.getdata():
        if min(r, g, b) > 235:
            continue
        counts[(r // 8 * 8 + 4, g // 8 * 8 + 4, b // 8 * 8 + 4)] += 1
    return counts


def split_teal_and_charcoal(counts):
    teal = max(
        (c for c in counts if c[1] > 150 and c[1] - c[0] > 80), key=lambda c: counts[c], default=None
    )
    charcoal = max(
        (c for c in counts if max(c) < 90 and max(c) - min(c) < 20),
        key=lambda c: counts[c],
        default=None,
    )
    return teal, charcoal


def darken_until(rgb, background, minimum):
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    while v > 0 and contrast(tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, s, v)), background) < minimum:
        v -= 0.005
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))


def mark_box(image):
    """Bounding box of the triangle mark: the first block of non-white columns."""
    gray = image.convert("L")
    width, height = gray.size
    px = gray.load()
    ink = [any(px[x, y] < 200 for y in range(height)) for x in range(width)]
    start = ink.index(True)
    end, gap = start, 0
    for x in range(start, width):
        if ink[x]:
            end, gap = x, 0
        else:
            gap += 1
            if gap > max(2, round(width * 24 / 1274)):  # a few pixels, scaled to the logo size
                break
    rows = [y for y in range(height) if any(px[x, y] < 200 for x in range(start, end + 1))]
    return start, rows[0], end + 1, rows[-1] + 1


def square_icon(mark, size, padding_ratio=0.16, background=(255, 255, 255)):
    canvas = Image.new("RGB", (size, size), background)
    inner = int(size * (1 - 2 * padding_ratio))
    scale = min(inner / mark.width, inner / mark.height)
    resized = mark.resize((max(1, round(mark.width * scale)), max(1, round(mark.height * scale))), Image.LANCZOS)
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return canvas


def main():
    logo = flatten_on_white(Image.open(SOURCE))
    teal, charcoal = split_teal_and_charcoal(dominant_colours(logo))
    print(f"logo size            : {logo.size}")
    print(f"sampled brand teal   : {hex_of(teal)}")
    print(f"sampled charcoal     : {hex_of(charcoal)}")

    white, near_black = (255, 255, 255), (15, 23, 26)
    teal_text = darken_until(teal, white, 4.5)
    print(f"teal on white        : {contrast(teal, white):.2f}:1  (fails AA for text, accent only)")
    print(f"darker teal for text : {hex_of(teal_text)}  {contrast(teal_text, white):.2f}:1 on white")
    print(f"white on darker teal : {contrast(white, teal_text):.2f}:1 (buttons)")
    print(f"charcoal on white    : {contrast(charcoal, white):.2f}:1")
    print(f"teal on dark surface : {contrast(teal, near_black):.2f}:1 ({hex_of(near_black)})")

    box = mark_box(logo)
    mark = logo.crop(box)
    print(f"mark crop box        : {box}")
    mark.save(BRAND / "vezapp-mark.png")

    square_icon(mark, 512).save(BRAND / "icon-512.png")
    square_icon(mark, 192).save(BRAND / "icon-192.png")
    square_icon(mark, 180, padding_ratio=0.14).save(BRAND / "apple-touch-icon.png")
    square_icon(mark, 64, padding_ratio=0.06).save(
        BRAND / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]
    )
    print("wrote vezapp-mark.png, icon-512.png, icon-192.png, apple-touch-icon.png, favicon.ico")


if __name__ == "__main__":
    main()
