# EpiMediaHub Provisioning Server

Raspberry-Pi backend for customer/device provisioning used by Android first and Enigma2 later.

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
