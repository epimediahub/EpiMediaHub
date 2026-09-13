#!/usr/bin/env python3
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

root = Path(os.environ["EPI_PLUGIN_ROOT"])
theme_dir = root / "themes"
catalog = json.loads((theme_dir / "catalog.json").read_text(encoding="utf-8"))
themes = catalog.get("themes", {})
home_dir = theme_dir / "home_motifs"
banner_dir = theme_dir / "banner_motifs"
dialog_dir = theme_dir / "dialog_motifs"
for directory in (home_dir, banner_dir, dialog_dir):
    directory.mkdir(parents=True, exist_ok=True)

tile_rects = [
    (0, 0, 550, 95), (620, 0, 1170, 95),
    (0, 115, 550, 210), (620, 115, 1170, 210),
    (0, 230, 550, 325), (620, 230, 1170, 325),
]

def rgb(value, fallback=(30, 136, 216)):
    value = str(value or "").strip().lstrip("#")
    try:
        if len(value) == 8:
            value = value[-6:]
        if len(value) == 6:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        pass
    return fallback

def load_motif(theme_id):
    candidates = [
        theme_dir / "marks" / ("%s.png" % theme_id),
        theme_dir / "center_marks" / ("%s.png" % theme_id),
        theme_dir / ("%s.png" % theme_id),
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            image = Image.open(str(candidate)).convert("RGBA")
            box = image.getchannel("A").getbbox()
            if box:
                return image.crop(box)
        except Exception:
            pass
    return Image.new("RGBA", (256, 256), (255, 255, 255, 0))

def alpha_image(image, maximum):
    image = image.copy().convert("RGBA")
    alpha = image.getchannel("A").point(lambda p: int(p * maximum / 255.0))
    image.putalpha(alpha)
    return image

def scaled_cover(image, min_w, min_h):
    w, h = image.size
    if w <= 0 or h <= 0:
        return image
    factor = max(float(min_w) / float(w), float(min_h) / float(h))
    return image.resize((max(1, int(w * factor)), max(1, int(h * factor))), Image.LANCZOS)

def paste_center(canvas, image, center_x, center_y):
    x = int(center_x - image.size[0] / 2)
    y = int(center_y - image.size[1] / 2)
    canvas.alpha_composite(image, (x, y))

for number, (theme_id, meta) in enumerate(themes.items(), 1):
    motif = load_motif(theme_id)
    accent = rgb(meta.get("accent"))

    # One large motif is rendered once and only revealed through the six tile
    # windows. This creates a continuous image across the dashboard instead of
    # repeating a full logo in every tile.
    virtual = Image.new("RGBA", (1170, 325), (0, 0, 0, 0))
    huge = scaled_cover(motif, 1080, 690)
    shadow = alpha_image(huge.filter(ImageFilter.GaussianBlur(18)), 28)
    crisp = alpha_image(huge, 78)
    paste_center(virtual, shadow, 585, 163)
    paste_center(virtual, crisp, 585, 163)
    mask = Image.new("L", (1170, 325), 0)
    md = ImageDraw.Draw(mask)
    for rect in tile_rects:
        md.rounded_rectangle(rect, radius=18, fill=255)
    clipped = Image.new("RGBA", virtual.size, (0, 0, 0, 0))
    clipped.paste(virtual, (0, 0), mask)
    home = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    home.alpha_composite(clipped, (55, 210))
    home.save(str(home_dir / ("%s.png" % theme_id)), optimize=True)

    # Broadcast-style zapping banner with a subdued large theme mark, glass
    # surface and a crisp accent line derived from the selected theme.
    banner = Image.new("RGBA", (1280, 220), (8, 13, 20, 232))
    bd = ImageDraw.Draw(banner)
    for y in range(220):
        a = int(18 * (1.0 - float(y) / 220.0))
        bd.line((0, y, 1280, y), fill=(accent[0], accent[1], accent[2], a))
    bd.rectangle((0, 0, 1280, 5), fill=(accent[0], accent[1], accent[2], 235))
    bm = alpha_image(scaled_cover(motif, 520, 300), 72)
    paste_center(banner, bm, 1045, 110)
    banner.save(str(banner_dir / ("%s.png" % theme_id)), optimize=True)

    # Exit confirmation surface uses the same visual language but keeps the
    # artwork intentionally quiet behind the text and buttons.
    dialog = Image.new("RGBA", (760, 330), (9, 14, 22, 246))
    dd = ImageDraw.Draw(dialog)
    dd.rounded_rectangle((1, 1, 758, 328), radius=24, outline=(accent[0], accent[1], accent[2], 170), width=2)
    dd.rectangle((0, 0, 760, 6), fill=(accent[0], accent[1], accent[2], 240))
    dm = alpha_image(scaled_cover(motif, 430, 330), 48)
    paste_center(dialog, dm, 575, 165)
    dialog.save(str(dialog_dir / ("%s.png" % theme_id)), optimize=True)

    if number % 20 == 0:
        print("Generated %d/%d themes" % (number, len(themes)))

print("Generated premium assets for %d themes" % len(themes))
