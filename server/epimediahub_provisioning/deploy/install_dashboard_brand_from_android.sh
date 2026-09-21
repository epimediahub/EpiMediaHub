#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo ausführen." >&2
  exit 1
fi

APP_DIR="${EPIMEDIAHUB_APP_DIR:-/opt/epimediahub/provisioning}"
ANDROID_BRANCH="${EPIMEDIAHUB_ANDROID_BRANCH:-android-v0.7.0-ui}"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${ANDROID_BRANCH}/android/source_parts"
TARGET="$APP_DIR/templates/brand_mark_v081.html"

mkdir -p /var/tmp
TMP="$(mktemp -d -p /var/tmp epimediahub-brand.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

: > "$TMP/source.b64"
for part in 00 01 02 03 04 05; do
  curl -fsSL "$RAW/source_${part}?nocache=$(date +%s)-${part}" >> "$TMP/source.b64"
done

python3 - "$TMP/source.b64" "$TARGET" <<'PY'
from __future__ import annotations

import base64
import html
import io
import re
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

src = Path(sys.argv[1])
target = Path(sys.argv[2])
archive = base64.b64decode("".join(src.read_text().split()))
tf = tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz")
members = [m for m in tf.getmembers() if m.isfile()]

candidates = []
for m in members:
    lower = m.name.lower()
    if re.search(r"/res/drawable[^/]*/brand_header\.(png|webp|jpe?g|svg|xml)$", lower):
        ext = lower.rsplit(".", 1)[-1]
        rank = {"svg": 0, "png": 1, "webp": 2, "jpg": 3, "jpeg": 3, "xml": 4}.get(ext, 9)
        candidates.append((rank, m))

if not candidates:
    raise SystemExit("brand_header wurde im Android-Quellarchiv nicht gefunden.")

_, member = sorted(candidates, key=lambda x: (x[0], x[1].name))[0]
data = tf.extractfile(member).read()
ext = member.name.lower().rsplit(".", 1)[-1]

def image_partial(mime: str, raw: bytes) -> str:
    b64 = base64.b64encode(raw).decode("ascii")
    return (
        '<span class="brand-mark-inline brand-mark-real" aria-label="EpiMediaHub">'
        f'<img class="brand-logo-real" src="data:{mime};base64,{b64}" alt="EpiMediaHub">'
        '</span>\n'
    )

def android_color(value: str, colors: dict[str, str]) -> tuple[str, float]:
    value = (value or "").strip()
    if value.startswith("@color/"):
        value = colors.get(value.split("/", 1)[1], "#FFFFFF")
    if value in ("@android:color/transparent", "transparent"):
        return "none", 1.0
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) == 4:  # ARGB
            a, rgb = h[0] * 2, "".join(ch * 2 for ch in h[1:])
            return "#" + rgb, int(a, 16) / 255
        if len(h) == 8:  # AARRGGBB
            return "#" + h[2:], int(h[:2], 16) / 255
        if len(h) == 6:
            return "#" + h, 1.0
    # Conservative fallback for unresolved Android resources.
    return "#FFFFFF", 1.0

def load_colors() -> dict[str, str]:
    out = {}
    for m in members:
        if re.search(r"/res/values[^/]*/colors\.xml$", m.name.lower()):
            try:
                root = ET.fromstring(tf.extractfile(m).read())
                for child in root:
                    if child.tag.endswith("color") and child.attrib.get("name") and child.text:
                        out[child.attrib["name"]] = child.text.strip()
            except Exception:
                pass
    return out

def vector_to_svg(raw: bytes) -> bytes:
    root = ET.fromstring(raw)
    tag = root.tag.split("}")[-1]
    if tag != "vector":
        raise SystemExit(f"brand_header.xml ist kein Android-Vector-Drawable ({tag}).")
    A = "{http://schemas.android.com/apk/res/android}"
    vw = root.attrib.get(A + "viewportWidth", "512")
    vh = root.attrib.get(A + "viewportHeight", "160")
    colors = load_colors()
    ids = iter(range(1, 10000))

    def esc(v):
        return html.escape(str(v), quote=True)

    def render_node(node):
        name = node.tag.split("}")[-1]
        if name == "path":
            d = node.attrib.get(A + "pathData", "")
            fill, fill_alpha = android_color(node.attrib.get(A + "fillColor", "#000000"), colors)
            stroke, stroke_alpha = android_color(node.attrib.get(A + "strokeColor", "transparent"), colors)
            fill_alpha *= float(node.attrib.get(A + "fillAlpha", "1") or 1)
            stroke_alpha *= float(node.attrib.get(A + "strokeAlpha", "1") or 1)
            attrs = [
                f'd="{esc(d)}"',
                f'fill="{esc(fill)}"',
                f'fill-opacity="{fill_alpha:.4f}"',
            ]
            if stroke != "none":
                attrs += [
                    f'stroke="{esc(stroke)}"',
                    f'stroke-opacity="{stroke_alpha:.4f}"',
                    f'stroke-width="{esc(node.attrib.get(A + "strokeWidth", "0"))}"',
                    f'stroke-linecap="{esc(node.attrib.get(A + "strokeLineCap", "butt"))}"',
                    f'stroke-linejoin="{esc(node.attrib.get(A + "strokeLineJoin", "miter"))}"',
                ]
            return "<path " + " ".join(attrs) + "/>"
        if name == "group":
            tx = float(node.attrib.get(A + "translateX", "0") or 0)
            ty = float(node.attrib.get(A + "translateY", "0") or 0)
            sx = float(node.attrib.get(A + "scaleX", "1") or 1)
            sy = float(node.attrib.get(A + "scaleY", "1") or 1)
            rot = float(node.attrib.get(A + "rotation", "0") or 0)
            px = float(node.attrib.get(A + "pivotX", "0") or 0)
            py = float(node.attrib.get(A + "pivotY", "0") or 0)
            transforms = []
            if tx or ty:
                transforms.append(f"translate({tx} {ty})")
            if rot:
                transforms.append(f"rotate({rot} {px} {py})")
            if sx != 1 or sy != 1:
                transforms.append(f"translate({px} {py}) scale({sx} {sy}) translate({-px} {-py})")
            body = "".join(render_node(ch) for ch in node)
            transform = f' transform="{esc(" ".join(transforms))}"' if transforms else ""
            return f"<g{transform}>{body}</g>"
        if name == "clip-path":
            cid = f"clip{next(ids)}"
            d = node.attrib.get(A + "pathData", "")
            return f'<defs><clipPath id="{cid}"><path d="{esc(d)}"/></clipPath></defs>'
        return "".join(render_node(ch) for ch in node)

    body = "".join(render_node(ch) for ch in root)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {esc(vw)} {esc(vh)}" '
        f'preserveAspectRatio="xMinYMid meet">{body}</svg>'
    )
    return svg.encode("utf-8")

if ext == "png":
    partial = image_partial("image/png", data)
elif ext == "webp":
    partial = image_partial("image/webp", data)
elif ext in ("jpg", "jpeg"):
    partial = image_partial("image/jpeg", data)
elif ext == "svg":
    partial = image_partial("image/svg+xml", data)
elif ext == "xml":
    partial = image_partial("image/svg+xml", vector_to_svg(data))
else:
    raise SystemExit("Nicht unterstütztes brand_header-Format: " + ext)

target.parent.mkdir(parents=True, exist_ok=True)
tmp = target.with_suffix(target.suffix + ".tmp")
tmp.write_text(partial)
tmp.replace(target)
print(f"Echtes Android-App-Logo installiert: {member.name}")
PY

chown epimediahub:epimediahub "$TARGET"
chmod 644 "$TARGET"

echo "Dashboard-Logo wurde direkt aus dem Android brand_header übernommen."
