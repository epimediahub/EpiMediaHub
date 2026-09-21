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

python3 - "$TARGET" <<'PY'
from __future__ import annotations

import base64
import html
import io
import re
import sys
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

target = Path(sys.argv[1])
download_dir = Path("/srv/epimediahub-downloads/android")

def image_partial(mime: str, raw: bytes) -> str:
    b64 = base64.b64encode(raw).decode("ascii")
    return (
        '<span class="brand-mark-inline brand-mark-real" aria-label="EpiMediaHub">'
        f'<img class="brand-logo-real" src="data:{mime};base64,{b64}" alt="EpiMediaHub">'
        '</span>\n'
    )

def mime_for(ext: str) -> str:
    return {
        "png":"image/png",
        "webp":"image/webp",
        "jpg":"image/jpeg",
        "jpeg":"image/jpeg",
        "svg":"image/svg+xml",
        "avif":"image/avif",
    }[ext]

def try_apk() -> tuple[str, bytes, str] | None:
    if not download_dir.exists():
        return None
    apks = list(download_dir.glob("*.apk"))
    apks.sort(
        key=lambda p: (
            0 if "universal" in p.name.lower() else 1,
            0 if "0.8.3" in p.name.lower() else 1,
            -p.stat().st_mtime_ns,
        )
    )
    pattern = re.compile(r"^res/drawable[^/]*/brand_header\.(png|webp|jpe?g|svg|avif|xml)$", re.I)
    for apk in apks:
        try:
            with zipfile.ZipFile(apk) as zf:
                names = zf.namelist()
                exact = [n for n in names if pattern.match(n)]
                if not exact:
                    exact = [n for n in names if "brand_header" in n.lower()]
                for name in exact:
                    ext = name.lower().rsplit(".", 1)[-1]
                    raw = zf.read(name)
                    if ext in {"png","webp","jpg","jpeg","svg","avif"}:
                        return f"{apk.name}:{name}", raw, ext
                    if ext == "xml" and raw.lstrip().startswith(b"<"):
                        return f"{apk.name}:{name}", raw, "xml-text"
        except zipfile.BadZipFile:
            continue
    return None

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
        if len(h) == 4:
            a, rgb = h[0] * 2, "".join(ch * 2 for ch in h[1:])
            return "#" + rgb, int(a, 16) / 255
        if len(h) == 8:
            return "#" + h[2:], int(h[:2], 16) / 255
        if len(h) == 6:
            return "#" + h, 1.0
    return "#FFFFFF", 1.0

def vector_to_svg(raw: bytes, colors: dict[str,str] | None = None) -> bytes:
    colors = colors or {}
    root = ET.fromstring(raw)
    tag = root.tag.split("}")[-1]
    if tag != "vector":
        raise ValueError("not vector")
    A = "{http://schemas.android.com/apk/res/android}"
    vw = root.attrib.get(A + "viewportWidth", "512")
    vh = root.attrib.get(A + "viewportHeight", "160")
    def esc(v): return html.escape(str(v), quote=True)
    def render(node):
        name = node.tag.split("}")[-1]
        if name == "path":
            d = node.attrib.get(A + "pathData", "")
            fill, fa = android_color(node.attrib.get(A + "fillColor", "#000000"), colors)
            stroke, sa = android_color(node.attrib.get(A + "strokeColor", "transparent"), colors)
            fa *= float(node.attrib.get(A + "fillAlpha", "1") or 1)
            sa *= float(node.attrib.get(A + "strokeAlpha", "1") or 1)
            attrs=[f'd="{esc(d)}"',f'fill="{esc(fill)}"',f'fill-opacity="{fa:.4f}"']
            if stroke != "none":
                attrs += [f'stroke="{esc(stroke)}"',f'stroke-opacity="{sa:.4f}"',f'stroke-width="{esc(node.attrib.get(A + "strokeWidth","0"))}"']
            return "<path "+" ".join(attrs)+"/>"
        if name == "group":
            tx=float(node.attrib.get(A+"translateX","0") or 0); ty=float(node.attrib.get(A+"translateY","0") or 0)
            sx=float(node.attrib.get(A+"scaleX","1") or 1); sy=float(node.attrib.get(A+"scaleY","1") or 1)
            rot=float(node.attrib.get(A+"rotation","0") or 0); px=float(node.attrib.get(A+"pivotX","0") or 0); py=float(node.attrib.get(A+"pivotY","0") or 0)
            t=[]
            if tx or ty: t.append(f"translate({tx} {ty})")
            if rot: t.append(f"rotate({rot} {px} {py})")
            if sx != 1 or sy != 1: t.append(f"translate({px} {py}) scale({sx} {sy}) translate({-px} {-py})")
            return f'<g transform="{esc(" ".join(t))}">'+"".join(render(ch) for ch in node)+"</g>"
        return "".join(render(ch) for ch in node)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {esc(vw)} {esc(vh)}" preserveAspectRatio="xMinYMid meet">{"".join(render(ch) for ch in root)}</svg>'
    return svg.encode()

found = try_apk()
if found:
    source, raw, ext = found
    if ext == "xml-text":
        raw = vector_to_svg(raw)
        ext = "svg"
    partial = image_partial(mime_for(ext), raw)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(partial)
    tmp.replace(target)
    print(f"Echtes Android-App-Logo aus APK installiert: {source}")
    raise SystemExit(0)

# Fallback: source-lite archive. This may not contain binary premium assets,
# but keeps older source-only builds working.
branch = "android-v0.7.0-ui"
base = f"https://raw.githubusercontent.com/epimediahub/EpiMediaHub/{branch}/android/source_parts"
chunks=[]
for part in ("00","01","02","03","04","05"):
    req=urllib.request.Request(f"{base}/source_{part}",headers={"User-Agent":"EpiMediaHub-Dashboard-Brand/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        chunks.append(resp.read().decode())
archive=base64.b64decode("".join("".join(chunks).split()))
tf=tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz")
members=[m for m in tf.getmembers() if m.isfile()]
pattern=re.compile(r"/res/drawable[^/]*/brand_header\.(png|webp|jpe?g|svg|xml)$",re.I)
candidates=[m for m in members if pattern.search(m.name)]
if not candidates:
    raise SystemExit("brand_header weder in den synchronisierten Android-APKs noch im Source-Lite-Archiv gefunden.")
m=candidates[0]
raw=tf.extractfile(m).read()
ext=m.name.lower().rsplit(".",1)[-1]
if ext=="xml":
    if not raw.lstrip().startswith(b"<"):
        raise SystemExit("brand_header ist binäres Android-XML und konnte nicht als Weblogo verwendet werden.")
    raw=vector_to_svg(raw); ext="svg"
partial=image_partial(mime_for(ext),raw)
target.parent.mkdir(parents=True,exist_ok=True)
tmp=target.with_suffix(target.suffix+".tmp")
tmp.write_text(partial)
tmp.replace(target)
print(f"Echtes Android-App-Logo aus Source-Lite installiert: {m.name}")
PY

chown epimediahub:epimediahub "$TARGET"
chmod 644 "$TARGET"

echo "Dashboard-Logo wurde aus der installierten Android-App übernommen."
