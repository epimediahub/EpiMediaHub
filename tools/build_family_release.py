#!/usr/bin/env python3
import argparse
import difflib
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import cairosvg
from PIL import Image, ImageDraw, ImageFilter

VERSION = "0.9.9"
PLUGIN_REL = Path("usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub")

FOOTBALL = {
    "man_city": ("england", ["Manchester City", "Man City"]),
    "liverpool": ("england", ["Liverpool", "Liverpool FC"]),
    "arsenal": ("england", ["Arsenal", "Arsenal FC"]),
    "man_utd": ("england", ["Manchester United", "Man United", "Man Utd"]),
    "chelsea": ("england", ["Chelsea", "Chelsea FC"]),
    "inter": ("italy", ["Inter", "Inter Milan", "Internazionale"]),
    "milan": ("italy", ["AC Milan", "Milan"]),
    "juventus": ("italy", ["Juventus", "Juventus FC"]),
    "napoli": ("italy", ["Napoli", "SSC Napoli"]),
    "roma": ("italy", ["AS Roma", "Roma"]),
    "real_madrid": ("spain", ["Real Madrid"]),
    "barcelona": ("spain", ["Barcelona", "FC Barcelona"]),
    "atletico": ("spain", ["Atletico Madrid", "Atlético Madrid"]),
    "sevilla": ("spain", ["Sevilla", "Sevilla FC"]),
    "athletic": ("spain", ["Athletic Club", "Athletic Bilbao"]),
    "bayern": ("germany", ["Bayern Munich", "Bayern München", "FC Bayern"]),
    "dortmund": ("germany", ["Borussia Dortmund", "Dortmund"]),
    "leverkusen": ("germany", ["Bayer Leverkusen", "Leverkusen"]),
    "frankfurt": ("germany", ["Eintracht Frankfurt", "Frankfurt"]),
    "leipzig": ("germany", ["RB Leipzig", "Leipzig"]),
    "fc_koeln": ("germany", ["1 FC Köln", "FC Köln", "FC Cologne", "Cologne", "Koln"]),
    "psg": ("france", ["Paris Saint-Germain", "Paris Saint Germain", "PSG"]),
    "marseille": ("france", ["Olympique Marseille", "Marseille"]),
    "lyon": ("france", ["Olympique Lyon", "Lyon"]),
    "monaco": ("france", ["AS Monaco", "Monaco"]),
    "lille": ("france", ["LOSC Lille", "Lille"]),
    "ajax": ("netherlands", ["Ajax", "Ajax Amsterdam"]),
    "psv": ("netherlands", ["PSV", "PSV Eindhoven"]),
    "feyenoord": ("netherlands", ["Feyenoord", "Feyenoord Rotterdam"]),
    "az": ("netherlands", ["AZ Alkmaar", "AZ"]),
    "twente": ("netherlands", ["FC Twente", "Twente"]),
    "galatasaray": ("turkey", ["Galatasaray"]),
    "fenerbahce": ("turkey", ["Fenerbahce", "Fenerbahçe"]),
    "trabzonspor": ("turkey", ["Trabzonspor"]),
    "besiktas": ("turkey", ["Besiktas", "Beşiktaş"]),
    "basaksehir": ("turkey", ["Istanbul Basaksehir", "İstanbul Başakşehir", "Basaksehir"]),
    "porto": ("portugal", ["FC Porto", "Porto"]),
    "benfica": ("portugal", ["Benfica", "SL Benfica"]),
    "sporting": ("portugal", ["Sporting CP", "Sporting Lisbon", "Sporting"]),
    "celtic": ("scotland", ["Celtic", "Celtic FC"]),
    "rangers": ("scotland", ["Rangers", "Rangers FC"]),
}

CARS = {
    "ferrari": ["Ferrari"],
    "mercedes": ["Mercedes Benz", "Mercedes-Benz", "Mercedes"],
    "bmw": ["BMW"],
    "audi": ["Audi"],
    "porsche": ["Porsche"],
    "lamborghini": ["Lamborghini"],
    "volkswagen": ["Volkswagen", "VW"],
    "maserati": ["Maserati"],
    "bentley": ["Bentley"],
    "bugatti": ["Bugatti"],
    "aston_martin": ["Aston Martin"],
}

# These are deliberately explicit. Fashion logos must never be selected with
# fuzzy matching because a near filename can silently produce a wrong brand.
FASHION_FILES = {
    "gg_luxury": ("Gucci · Family", "gucci.svg"),
    "paris_monogram": ("Louis Vuitton · Family", "louis_vuitton.svg"),
    "milano_triangle": ("Prada · Family", "prada.svg"),
    "baroque_gold": ("Versace · Family", "versace.svg"),
}


def run(*cmd, cwd=None):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(x) for x in cmd], cwd=cwd, check=True)


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).lower()
    value = value.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", value)


def score_name(path, aliases):
    stem = normalize(Path(path).stem)
    reduced = re.sub(r"(footballclub|football|club|logo|badge|crest|fc|cf|ac|sc)$", "", stem)
    best = 0.0
    for alias in aliases:
        a = normalize(alias)
        ar = re.sub(r"(footballclub|football|club|logo|badge|crest|fc|cf|ac|sc)$", "", a)
        for left in (stem, reduced):
            for right in (a, ar):
                if not left or not right:
                    continue
                if left == right:
                    best = max(best, 1.0)
                elif right in left or left in right:
                    ratio = min(len(left), len(right)) / float(max(len(left), len(right)))
                    best = max(best, 0.84 + 0.15 * ratio)
                else:
                    best = max(best, difflib.SequenceMatcher(None, left, right).ratio())
    if Path(path).suffix.lower() == ".svg":
        best += 0.025
    return min(best, 1.0)


def candidates_under(root, subdir=None):
    base = Path(root)
    if subdir:
        exact = base / subdir
        if exact.exists():
            base = exact
        else:
            wanted = normalize(subdir)
            matches = [p for p in base.iterdir() if p.is_dir() and normalize(p.name) == wanted]
            if matches:
                base = matches[0]
    files = []
    for ext in ("*.svg", "*.png", "*.webp"):
        files.extend(base.rglob(ext))
    return files


def resolve_logo(root, aliases, subdir=None, min_score=0.58):
    files = candidates_under(root, subdir)
    if not files:
        raise RuntimeError("No logo files found under %s / %s" % (root, subdir or ""))
    ranked = sorted(((score_name(p, aliases), p) for p in files), key=lambda x: x[0], reverse=True)
    score, path = ranked[0]
    print("resolve:", aliases[0], "->", path, "score=%.3f" % score)
    if score < min_score:
        print("Top candidates:")
        for s, p in ranked[:12]:
            print("  %.3f %s" % (s, p))
        raise RuntimeError("Could not confidently resolve logo for %s" % aliases[0])
    return path


def load_logo(path):
    path = Path(path)
    if path.suffix.lower() == ".svg":
        png = cairosvg.svg2png(url=str(path), output_width=1200)
        image = Image.open(io.BytesIO(png)).convert("RGBA")
    else:
        image = Image.open(path).convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox:
        image = image.crop(bbox)
    if not bbox or image.width < 2 or image.height < 2:
        raise RuntimeError("Logo has no usable visible area: %s" % path)
    return image


def fit(image, max_w, max_h):
    image = image.copy()
    image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return image


def paste_center(canvas, image, box):
    x0, y0, x1, y1 = box
    image = fit(image, x1 - x0, y1 - y0)
    x = x0 + (x1 - x0 - image.width) // 2
    y = y0 + (y1 - y0 - image.height) // 2
    canvas.alpha_composite(image, (x, y))


def build_mark(logo, out_path):
    canvas = Image.new("RGBA", (180, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle((1, 1, 178, 78), radius=14,
                           fill=(255, 255, 255, 232), outline=(255, 255, 255, 245), width=1)
    paste_center(canvas, logo, (10, 7, 170, 73))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG", optimize=True)


def build_background(base_path, logo, out_path):
    base = Image.open(base_path).convert("RGBA")
    if base.size != (1280, 720):
        base = base.resize((1280, 720), Image.Resampling.LANCZOS)

    # Only the artwork area is changed; Enigma2 screen layout remains untouched.
    region = (770, 95, 1215, 575)
    blurred = base.crop(region).filter(ImageFilter.GaussianBlur(radius=26))
    blurred = Image.alpha_composite(blurred, Image.new("RGBA", blurred.size, (0, 0, 0, 105)))
    base.paste(blurred, region[:2])

    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow, "RGBA")
    sd.rounded_rectangle((843, 155, 1163, 525), radius=30, fill=(0, 0, 0, 95))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    base = Image.alpha_composite(base, shadow)

    card = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(card, "RGBA")
    draw.rounded_rectangle((835, 145, 1155, 515), radius=28,
                           fill=(255, 255, 255, 232), outline=(255, 255, 255, 248), width=2)
    base = Image.alpha_composite(base, card)
    paste_center(base, logo, (865, 175, 1125, 485))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(out_path, "PNG", optimize=True)


def extract_ipk(ipk, work):
    work = Path(work)
    ardir = work / "ar"
    data = work / "data"
    control = work / "control"
    ardir.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    control.mkdir(parents=True, exist_ok=True)
    run("ar", "x", str(Path(ipk).resolve()), cwd=ardir)
    run("tar", "-xzf", "data.tar.gz", "-C", str(data), cwd=ardir)
    run("tar", "-xzf", "control.tar.gz", "-C", str(control), cwd=ardir)
    return data, control


def patch_text_files(data, control):
    plugin = data / PLUGIN_REL / "plugin.py"
    text = plugin.read_text(encoding="utf-8")
    text = text.replace('PLUGIN_VERSION = "0.9.8"', 'PLUGIN_VERSION = "0.9.9"')
    text = text.replace("# -------------------- Themes / skins (v0.9.8) --------------------",
                        "# -------------------- Themes / skins (v0.9.9) --------------------")
    if '"0.9.9": {' not in text:
        anchor = "RELEASE_NOTES = {"
        idx = text.find(anchor)
        if idx >= 0:
            insert_at = text.find("{", idx) + 1
            note = '''\n    "0.9.9": {\n        "de": ["Interne Design-Ressourcen aktualisiert.", "Bestehendes Enigma2-Layout und Bedienung bleiben unverändert."],\n        "en": ["Updated internal design resources.", "Existing Enigma2 layout and controls remain unchanged."],\n        "tr": ["Dahili tasarım kaynakları güncellendi.", "Mevcut Enigma2 düzeni ve kontrolleri değişmedi."],\n        "it": ["Risorse grafiche interne aggiornate.", "Layout e controlli Enigma2 esistenti restano invariati."],\n        "es": ["Recursos de diseño internos actualizados.", "El diseño y los controles de Enigma2 permanecen sin cambios."]\n    },'''
            text = text[:insert_at] + note + text[insert_at:]
    plugin.write_text(text, encoding="utf-8")

    control_file = control / "control"
    c = control_file.read_text(encoding="utf-8")
    c = re.sub(r"(?m)^Version:\s*.*$", "Version: 0.9.9", c)
    c = re.sub(r"(?m)^Description:\s*.*$",
               "Description: Epi MediaHub - v0.9.9 integrated Family skin resources", c)
    control_file.write_text(c, encoding="utf-8")


def update_catalog(plugin_dir):
    catalog_path = plugin_dir / "themes" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for key, (label, _filename) in FASHION_FILES.items():
        family_id = "family_" + key
        if family_id in catalog.get("themes", {}):
            catalog["themes"][family_id]["label"] = label
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return catalog


def resolve_sources(args):
    sources = {}
    for theme, (country, aliases) in FOOTBALL.items():
        sources[theme] = resolve_logo(args.football_root, aliases, subdir=country, min_score=0.56)
    for theme, aliases in CARS.items():
        sources[theme] = resolve_logo(args.car_root, aliases, min_score=0.60)

    fashion_root = Path(args.fashion_root)
    for theme, (label, filename) in FASHION_FILES.items():
        source = fashion_root / filename
        if not source.is_file():
            raise RuntimeError("Missing explicit fashion logo for %s: %s" % (label, source))
        print("resolve exact:", label, "->", source)
        sources[theme] = source
    return sources


def verify_package_tree(plugin_dir, catalog):
    family_ids = [k for k, v in catalog.get("themes", {}).items() if v.get("family")]
    if len(family_ids) != 56:
        raise RuntimeError("Expected 56 Family themes, got %d" % len(family_ids))
    marks_dir = plugin_dir / "themes" / "marks"
    family_dir = plugin_dir / "themes" / "family"
    for family_id in family_ids:
        mark = marks_dir / (family_id + ".png")
        bg = family_dir / (family_id + ".png")
        if not mark.is_file() or not bg.is_file():
            raise RuntimeError("Missing generated assets for %s" % family_id)
        with Image.open(mark) as im:
            if im.size != (180, 80):
                raise RuntimeError("Bad mark size for %s: %r" % (family_id, im.size))
        with Image.open(bg) as im:
            if im.size != (1280, 720):
                raise RuntimeError("Bad background size for %s: %r" % (family_id, im.size))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--football-root", required=True)
    ap.add_argument("--car-root", required=True)
    ap.add_argument("--fashion-root", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    base_ipk = Path(args.base).resolve()
    output = Path(args.output).resolve()
    with tempfile.TemporaryDirectory(prefix="epimedia099-") as td:
        data, control = extract_ipk(base_ipk, td)
        plugin_dir = data / PLUGIN_REL
        themes_dir = plugin_dir / "themes"
        marks_dir = themes_dir / "marks"
        family_dir = themes_dir / "family"

        patch_text_files(data, control)
        catalog = update_catalog(plugin_dir)
        sources = resolve_sources(args)

        expected = set(FOOTBALL) | set(CARS) | set(FASHION_FILES)
        if set(sources) != expected:
            raise RuntimeError("Source resolution mismatch: %d/%d" % (len(sources), len(expected)))

        for base_theme, source_path in sorted(sources.items()):
            family_id = "family_" + base_theme
            family_meta = catalog.get("themes", {}).get(family_id)
            base_meta = catalog.get("themes", {}).get(base_theme)
            if not family_meta or not base_meta:
                raise RuntimeError("Missing catalog entry for %s / %s" % (base_theme, family_id))
            base_bg = themes_dir / base_meta.get("background", "%s.png" % base_theme)
            if not base_bg.is_file():
                raise RuntimeError("Missing base background: %s" % base_bg)
            logo = load_logo(source_path)
            build_mark(logo, marks_dir / (family_id + ".png"))
            build_background(base_bg, logo, family_dir / (family_id + ".png"))

        verify_package_tree(plugin_dir, catalog)
        run("python3", "-m", "py_compile", str(plugin_dir / "plugin.py"))
        pycache = plugin_dir / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache)

        pkg = Path(td) / "pkg"
        pkg.mkdir()
        (pkg / "debian-binary").write_text("2.0\n", encoding="ascii")
        run("tar", "--owner=0", "--group=0", "-czf", str(pkg / "control.tar.gz"),
            "-C", str(control), ".")
        run("tar", "--owner=0", "--group=0", "-czf", str(pkg / "data.tar.gz"),
            "-C", str(data), ".")
        if output.exists():
            output.unlink()
        run("ar", "r", str(output), "debian-binary", "control.tar.gz", "data.tar.gz", cwd=pkg)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print("OUTPUT", output)
    print("SIZE", output.stat().st_size)
    print("SHA256", digest)
    output.with_suffix(output.suffix + ".sha256").write_text(
        "%s  %s\n" % (digest, output.name), encoding="ascii")


if __name__ == "__main__":
    main()
