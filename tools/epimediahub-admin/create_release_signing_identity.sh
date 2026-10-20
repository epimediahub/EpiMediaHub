#!/usr/bin/env bash
# One-time OFFLINE Android release identity, never upload to public repo/chat.
set -Eeuo pipefail
umask 077
command -v keytool >/dev/null || { echo 'Java keytool is required';exit 2; }
command -v python3 >/dev/null || { echo 'Python3 required';exit 2; }
ROOT="${HOME}/.epimediahub-admin-release"
[[ ! -L "$ROOT" ]] || { echo 'STOP: unsafe signer directory'; exit 2; }
mkdir -p -m 700 "$ROOT"
chmod 700 "$ROOT"
KEYSTORE="$ROOT/admin-signing.jks"
SECRET="$ROOT/github-release-signing-secret.json"
if [[ -e "$KEYSTORE" || -e "$SECRET" ]];then
  echo 'STOP: existing Admin signing material. Refusing to rotate or overwrite.'
  exit 2
fi
ALIAS=epimediahub_admin
export ADMIN_STORE_PASSWORD="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
export ADMIN_KEY_PASSWORD="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
keytool -genkeypair -noprompt -storetype JKS \
  -keystore "$KEYSTORE" -alias "$ALIAS" \
  -storepass "$ADMIN_STORE_PASSWORD" -keypass "$ADMIN_KEY_PASSWORD" \
  -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 9125 \
  -dname 'CN=EpiMediaHub Admin,OU=Private Administration,O=EpiMediaHub,C=DE' \
  >/dev/null 2>&1
chmod 600 "$KEYSTORE"
CERT="$(
  keytool -list -v -alias "$ALIAS" -keystore "$KEYSTORE" \
    -storepass "$ADMIN_STORE_PASSWORD" 2>/dev/null |
  awk '/SHA256:/{print $2;exit}' | tr -d ':' | tr '[:upper:]' '[:lower:]'
)"
export ADMIN_SIGNER_DIGEST="$CERT"
export ADMIN_SIGNER_ALIAS="$ALIAS"
export ADMIN_SIGNER_KEYSTORE="$KEYSTORE"
python3 - "$SECRET" <<'PY'
import base64,json,os,re,sys
cert=os.environ['ADMIN_SIGNER_DIGEST']
if not re.fullmatch(r'[0-9a-f]{64}',cert):raise SystemExit('STOP: Invalid certificate fingerprint')
from pathlib import Path
path=Path(sys.argv[1])
out={'keystore_base64':base64.b64encode(Path(os.environ['ADMIN_SIGNER_KEYSTORE']).read_bytes()).decode(),
     'store_password':os.environ['ADMIN_STORE_PASSWORD'],
     'key_password':os.environ['ADMIN_KEY_PASSWORD'],
     'key_alias':os.environ['ADMIN_SIGNER_ALIAS'],
     'cert_sha256':cert}
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:json.dump(out,f,separators=(',',':'))
PY
echo 'EpiMediaHub Admin signing identity generated successfully.'
echo "Protected keystore and one-secret GitHub JSON saved under $ROOT"
echo 'Set GitHub Actions secret EPI_ADMIN_RELEASE_SIGNING_JSON using the local JSON file.'
echo 'KEEP an encrypted offsite backup. NEVER share the contents in chat or public GitHub.'
