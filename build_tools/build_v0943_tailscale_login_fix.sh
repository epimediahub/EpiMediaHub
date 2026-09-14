#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.42.ipk"
T=/tmp/epimedia0943
P="$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub/plugin.py"

rm -rf "$T"
mkdir -p "$T/ar" "$T/data" "$T/control" "$T/pkg"
cd "$T/ar"
ar x "$B"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary

# Never package persistent user data.
rm -rf "$T/data/etc/enigma2/EpiMediaHub" "$T/data/etc/enigma2/epimediahub"

export P
python3 - <<'PY'
import os
from pathlib import Path

p = Path(os.environ['P'])
t = p.read_text(encoding='utf-8')

if t.count('PLUGIN_VERSION = "0.9.42"') != 1:
    raise SystemExit('Expected exactly one v0.9.42 version marker')
t = t.replace('PLUGIN_VERSION = "0.9.42"', 'PLUGIN_VERSION = "0.9.43"', 1)

# v0.9.42 inserted regexes from a raw build string with doubled backslashes.
# In plugin.py that made the regex expect literal backslashes, so a valid
# 100.x.x.x Tailscale IP was never detected and login.tailscale.com URLs were
# never matched. Fix both patterns only; leave playback/features untouched.
bad_ip = r're.match(r"^100\\.\\d+\\.\\d+\\.\\d+$", value)'
good_ip = r're.match(r"^100\.\d+\.\d+\.\d+$", value)'
if t.count(bad_ip) != 1:
    raise SystemExit('Expected one buggy Tailscale IP regex, found %d' % t.count(bad_ip))
t = t.replace(bad_ip, good_ip, 1)

bad_url = r're.search(r"https://login\\.tailscale\\.com/a/[A-Za-z0-9_-]+", output)'
good_url = r're.search(r"https://login\.tailscale\.com/a/[A-Za-z0-9_-]+", output)'
if t.count(bad_url) != 2:
    raise SystemExit('Expected two buggy Tailscale auth URL regexes, found %d' % t.count(bad_url))
t = t.replace(bad_url, good_url)

# If tailscale up exits because the node is already authenticated, re-check the
# IP once before showing a login-link error. This also makes upgrades from a
# manually configured receiver recover immediately.
old = '''            if not auth_url:\n                match = re.search(r"https://login\\.tailscale\\.com/a/[A-Za-z0-9_-]+", output)\n                if match:\n                    auth_url = match.group(0)\n                    self._result = ("auth", auth_url, "")\n\n            # Keep watching after the URL has been shown.'''
new = '''            if not auth_url:\n                match = re.search(r"https://login\\.tailscale\\.com/a/[A-Za-z0-9_-]+", output)\n                if match:\n                    auth_url = match.group(0)\n                    self._result = ("auth", auth_url, "")\n\n            # tailscale up can return without an auth URL when this node was\n            # already approved (for example after a manual setup). Re-check\n            # the assigned IP before entering the browser-auth wait loop.\n            ip = _tailscale_ip()\n            if ip:\n                self._result = ("connected", ip, "")\n                return\n\n            # Keep watching after the URL has been shown.'''
# The URL regex has already been corrected above, so build the anchor with the
# corrected form if necessary.
old = old.replace(r'login\\.tailscale\\.com', r'login\.tailscale\.com')
new = new.replace(r'login\\.tailscale\\.com', r'login\.tailscale\.com')
if old not in t:
    raise SystemExit('Tailscale post-up auth anchor missing')
t = t.replace(old, new, 1)

notes_anchor = '_RELEASE_NOTES = {'
if notes_anchor in t:
    notes = '''_RELEASE_NOTES = {\n    "0.9.43": {\n        "de": ["Fernzugriff/Tailscale: Erkennung gültiger 100.x.x.x-Adressen korrigiert.", "Tailscale-Anmeldelinks werden jetzt korrekt erkannt und als QR-Code angezeigt.", "Bereits manuell angemeldete Receiver werden sofort als verbunden erkannt; Mediathek und übrige Funktionen bleiben unverändert."],\n        "en": ["Remote access/Tailscale: fixed detection of valid 100.x.x.x addresses.", "Tailscale login links are now detected correctly and shown as a QR code.", "Receivers already authenticated manually are detected as connected immediately; Mediathek and all other features remain unchanged."],\n    },'''
    t = t.replace(notes_anchor, notes, 1)

p.write_text(t, encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.43/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.43 Tailscale login and status fix/' "$T/control/control"

python3 -m py_compile "$P"
find "$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub" -type d -name __pycache__ -prune -exec rm -rf {} +

# v0.9.43 guards.
grep -Fq 'PLUGIN_VERSION = "0.9.43"' "$P"
grep -Fq 'class EpiTailscaleSetup(Screen)' "$P"
grep -Fq '("remoteaccess", "Fernzugriff (Tailscale): %s" % _tailscale_state_text())' "$P"
grep -Fq 'ref=eServiceReference(4097,0,url)' "$P"
grep -Fq 'FAMILY_PIN_HASH' "$P"
grep -Fq 'family_skins_unlocked' "$P"
grep -Fq 'parental_pin_hash' "$P"

python3 - <<'PY'
import os
from pathlib import Path
p = Path(os.environ['P'])
t = p.read_text(encoding='utf-8')
if r're.match(r"^100\\.\\d+\\.\\d+\\.\\d+$", value)' in t:
    raise SystemExit('Buggy doubled Tailscale IP regex remains')
if r're.search(r"https://login\\.tailscale\\.com/a/[A-Za-z0-9_-]+", output)' in t:
    raise SystemExit('Buggy doubled Tailscale URL regex remains')
if r're.match(r"^100\.\d+\.\d+\.\d+$", value)' not in t:
    raise SystemExit('Correct Tailscale IP regex missing')
if t.count(r're.search(r"https://login\.tailscale\.com/a/[A-Za-z0-9_-]+", output)') != 2:
    raise SystemExit('Correct Tailscale auth URL regex count mismatch')
if 'ip = _tailscale_ip()\n            if ip:\n                self._result = ("connected", ip, "")\n                return\n\n            # Keep watching after the URL has been shown.' not in t:
    raise SystemExit('Already-authenticated fallback missing')
print('v0.9.43 Tailscale regex/status guards: OK')
PY

sh -n "$T/control/preinst" 2>/dev/null || true
sh -n "$T/control/postinst" 2>/dev/null || true

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.43.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"

ar t EpiMediaHub_v0.9.43.ipk | grep -Fxq debian-binary
ar t EpiMediaHub_v0.9.43.ipk | grep -Fxq control.tar.gz
ar t EpiMediaHub_v0.9.43.ipk | grep -Fxq data.tar.gz
if ar p EpiMediaHub_v0.9.43.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2
  exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.43.ipk)
echo "v0.9.43 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.43.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.43.ipk" > EpiMediaHub_v0.9.43.ipk.sha256
printf '{\n  "version": "0.9.43",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.43.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.43.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add EpiMediaHub_v0.9.43.ipk EpiMediaHub_v0.9.43.ipk.sha256 update.json
git commit -m 'Publish EpiMediaHub v0.9.43 Tailscale login/status fix'
git push
