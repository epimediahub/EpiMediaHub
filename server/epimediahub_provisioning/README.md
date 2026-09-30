# EpiMediaHub Provisioning Server

Raspberry-Pi backend for customer/device provisioning used by Android first and Enigma2 later.

## Version 0.8.2: reviewed intro and end-credit markers

Android 1.0.16 can save exact intro, recap and end-credit boundaries locally and
submit them using its device session. `/admin/skip` lists the proposals for an
authenticated administrator. Only approved proposals are shared with other
devices. Marks are tied to the provider file, episode and measured runtime;
different files and runtimes never inherit a guessed percentage. Proposals can
also explicitly disable an incorrect segment. Milliseconds are preserved.

The device endpoints are `POST /v1/device/skip/lookup`, `/submit` and `/presence`
under that prefix. They require an enabled device and customer. They accept
hashed file/series identities and validated metadata; stream URLs, passwords and
request headers are not accepted. Admin review requires the existing admin login
and a CSRF token. IMDb/TMDB corrections are explicitly reviewed in the dashboard.

Optional audio analysis is enabled separately for each existing Xtream playlist
in `/admin/skip`. Enable it only when the provider permits an additional
connection. The worker waits while an Android 1.0.16 player reports playback for
that provider account, uses bounded temporary audio decoding and retains only
fingerprints. It reads explicit chapter boundaries and learns intro audio from
approved references of the same series and season. Every result remains a pending
proposal until reviewed. Missing references, unsupported streams, ambiguous
matches and varying intros keep the manual correction path. This does not promise
automatic detection of every edit or season.

Upgrade an existing Raspberry installation with:

```bash
curl -fsSL https://raw.githubusercontent.com/epimediahub/EpiMediaHub/raspberry-v0.8.2-skip-markers/server/epimediahub_provisioning/deploy/upgrade_to_v082.sh -o /tmp/epimediahub-v082.sh
sudo bash /tmp/epimediahub-v082.sh
```

The installer uses the established backup/rollback upgrader, preserves existing
accounts, playlists and credentials, installs FFmpeg/libchromaprint and enables
the analysis timer. Analysis stays disabled for every playlist until selected in
the dashboard. `/health` reports `0.8.2` after installation. Publishing this
branch does not itself update a running Raspberry.

Validation: run `tests/smoke_v082.py` with the Python requirements, FFmpeg and
libchromaprint installed. Tests create an isolated database and include actual
audio decoding/fingerprint matching at different intro offsets. The existing
dashboard regression test accepts
`EPIMEDIAHUB_EXPECTED_API_VERSION=0.8.2 python tests/smoke_v080.py`.

## Security model

- Admin endpoints require `Authorization: Bearer <EPIMEDIAHUB_ADMIN_TOKEN>`.
- Setup codes are random, short-lived and stored only as SHA-256 hashes.
- Activation URLs contain a separate high-entropy token.
- A setup code can be redeemed exactly once.
- Successful redemption returns a per-device session token; activation codes are not reusable credentials.
- Production traffic must be exposed through HTTPS reverse proxy/tunnel. The Flask service itself listens only on `127.0.0.1:8787`.

## Environment

```text
EPIMEDIAHUB_ADMIN_TOKEN=<long-random-secret>
EPIMEDIAHUB_PUBLIC_URL=https://your-public-setup-host.example
EPIMEDIAHUB_DATA_DIR=/var/lib/epimediahub
PORT=8787
```

## API v1

Version 0.7.0 separates the hierarchy cleanly: customers own devices and every
device owns any number of playlists. Existing customer-level playlist data is
copied to the associated devices automatically during the schema migration.
The device config response contains a `playlists` array and mirrors its first
entry at the top level for compatibility with older app versions.

### Create customer
`POST /v1/admin/customers`

```json
{
  "name": "Testkunde",
  "config": {
    "playlist_url": "https://provider.example/playlist.m3u"
  }
}
```

### Generate activation
`POST /v1/admin/customers/{customer_id}/activation`

Optional body: `{ "ttl_minutes": 60 }`

Response contains `code`, `activation_url`, `qr_payload`, `expires_at`. QR and URL point to the same activation reference; the human-readable code is the remote-support alternative.

### Android/Enigma setup redemption
`POST /v1/setup/redeem`

```json
{
  "code": "ABCD-EFGH-JKLM",
  "device_id": "device-generated-stable-id",
  "platform": "android"
}
```

Status semantics expected by Android v0.4.13:

- `404` invalid code
- `409` already used
- `410` expired
- `200` returns customer configuration and a device session token

## Next deployment step

When the Raspberry Pi is available, create a Python virtual environment, install `requirements.txt`, set the environment variables, start the service under systemd, and put an HTTPS reverse proxy or secure tunnel in front of it. Do not expose Flask's development server directly to the internet.
