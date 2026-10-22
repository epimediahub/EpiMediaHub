#!/usr/bin/env bash
# Direct install of checksum-pinned, previously validated EpiScene guided learning.
set -Eeuo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo "STOP: root required" >&2; exit 2; }
for tool in curl base64 sha256sum tar bash mktemp; do
 command -v "$tool" >/dev/null || { echo "STOP: missing $tool" >&2; exit 2; }
done
PAYLOAD_URL='https://raw.githubusercontent.com/epimediahub/EpiMediaHub/d53d6a78904d0905b2b66d3eabd6d5e3a5fafd5f/tools/episcene-learning-v1/active-guided-learning/episcene-active-learning-v1.tar.gz.b64'
PAYLOAD_SHA='6e39b26a2ba342bfa90f64e86bd124633bd1e07c1b58dbc6e34776d7e2492e6e'
B64=$(mktemp /root/.episcene-guided-XXXXXXXX.b64)
ARCHIVE=$(mktemp /root/.episcene-guided-XXXXXXXX.tar.gz)
trap 'rm -f -- "$B64" "$ARCHIVE"' EXIT
curl -fLsS --retry 2 --connect-timeout 10 --max-time 90 -o "$B64" "$PAYLOAD_URL"
base64 --decode "$B64" > "$ARCHIVE"
echo "$PAYLOAD_SHA  $ARCHIVE" | sha256sum --check --status || {
 echo "STOP: downloaded archive does not match verified source" >&2; exit 3;
}
while IFS= read -r member; do
 case "$member" in
  episcene-active-learning-v1/|episcene-active-learning-v1/install.sh|episcene-active-learning-v1/patch_active_learning.py|episcene-active-learning-v1/test_active_learning.py|episcene-active-learning-v1/README.txt|episcene-active-learning-v1/skip_external_learning_hints.py) ;;
  *) echo "STOP: unexpected archive member" >&2; exit 3;;
 esac
done < <(tar -tzf "$ARCHIVE")
echo "PACKAGE_VERIFIED: exact original SHA-256 and safe members"
tar -xzf "$ARCHIVE" -C /root --no-same-owner --no-same-permissions
bash /root/episcene-active-learning-v1/install.sh --apply
