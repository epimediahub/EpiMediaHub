# GalaBox Keystore-free encrypted VPN vault (isolated pilot)

## Why

A GalaBox Elite Android TV unit reports Android 13 / SDK API 30, with:
- AndroidKeyStore load: OK
- AndroidKeyStore AES-256/128 GCM: ProviderException -> KeyStoreException
- AndroidKeyStore RSA-2048 OAEP: ProviderException -> KeyStoreException
- Software AES-256 GCM: OK

Existing Fire TV uses a different, known-working manually configured WireGuard
peer. Never change any Fire TV peer, local profile, app license, or VPN grant.

## Protocol

The existing manually provisioned VPN license stays unchanged and still binds
to one registered `devices.device_id`. After explicit GalaBox compatibility
opt-in, if all AndroidKeyStore protection methods fail, the Android client may
POST to `/v1/device/vpn/galabox-vault-key` using its registered Bearer token,
device ID and storage purpose (`identity` or `profile`).

The provisioning server, and NOT the device, holds a randomly generated
**32-byte, persistent, root-backed-up master** at
`$EPIMEDIAHUB_DATA_DIR/galabox-vpn-vault-master.bin` (0600, owned by service
user). It derives a distinct HMAC-SHA256 key for each registered device and
purpose, then returns that wrapping key *only to an authenticated licensed
device* over HTTPS. It never receives a WireGuard private key.

The GalaBox uses the wrapping key in RAM to AES-256-GCM-encrypt local secrets,
uses random 96-bit IV and purpose/device-bound AAD, stores only ciphertext
in `noBackupFilesDir`, and zeroizes the wrapping key when finished.
If the server is unreachable, unlicensed or the master missing, the VPN remains
blocked, never switches to a direct stream. No automatic key rotation.

## Production operator flow

On the Hetzner provisioning dashboard host, download the isolated server
branch with the already used GitHub clone or sparse checkout.

1. `sudo python3 deploy/install_galabox_remote_vault.py --check`
   (read-only; requires the currently installed control center)
2. After reviewing CHECK OK and explicitly authorizing deployment:
   `sudo python3 deploy/install_galabox_remote_vault.py --apply`

The installer snapshots the complete SQLite DB, backs up current `wsgi.py`,
and backs up the persistent master under a root-only directory. It copies only
the new module, appends a single WSGI import, restarts the provisioning
service, checks health and anonymous auth rejection, and rolls back program
files on failure. It does not modify license tables or existing WireGuard peers.

Never delete or regenerate `galabox-vpn-vault-master.bin`: encrypted GalaBox
keys will become permanently unreadable. Keep backups encrypted/offsite with
root-only access. Do not upload key bytes, client tokens, WireGuard keys, or
VPN profiles to GitHub or support.

## Caveats

An authenticated bearer token is currently the existing proof of device
registration. If that token is compromised and an attacker also copies local
ciphertext, the attacker may request the wrapping key while the license
remains valid. This is weaker at-rest protection than healthy hardware-backed
AndroidKeyStore; treat it as a constrained compatibility fallback, not a new
security standard. Review token revocation, API abuse rate limits, backup and
incident response before extending beyond the one test GalaBox.

A successful WireGuard peer handshake and correct Finland public exit must
still be confirmed on the device; unlocking the profile alone is insufficient.
