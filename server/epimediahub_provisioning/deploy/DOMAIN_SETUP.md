# EpiMediaHub production domain setup

Target architecture:

- `setup.epimediahub.com` -> public provisioning / QR links
- `api.epimediahub.com` -> device provisioning + config sync API
- `admin.epimediahub.com` -> administrator dashboard
- Flask/Gunicorn stays local on `127.0.0.1:8787`
- Cloudflare Tunnel is the only public ingress. No router port forwarding is required.
- Tailscale remains separate for private receiver/maintenance networking.

## 1. Move DNS authority from checkdomain to Cloudflare

The domain remains registered at checkdomain. Add `epimediahub.com` to Cloudflare and copy the two Cloudflare-assigned nameservers. In checkdomain open the domain configuration, choose custom/external nameservers and replace the checkdomain nameservers with those two Cloudflare values.

Do not delete MX/TXT records if mail is already configured; copy existing DNS records into Cloudflare before changing nameservers.

## 2. Create the tunnel

In Cloudflare: Networking -> Tunnels -> Create Tunnel. Name it `epimediahub-production`.

Install the connector command shown by Cloudflare on the Raspberry. For a remotely managed tunnel this is normally:

```bash
sudo cloudflared service install <TUNNEL_TOKEN>
```

## 3. Published applications

Add these three routes to the same tunnel, each using service URL `http://127.0.0.1:8787`:

- `setup.epimediahub.com`
- `api.epimediahub.com`
- `admin.epimediahub.com`

Cloudflare creates the corresponding proxied DNS records.

## 4. Backend environment

Use `/etc/epimediahub/provisioning.env` with:

```text
EPIMEDIAHUB_PUBLIC_URL=https://setup.epimediahub.com
EPIMEDIAHUB_DATA_DIR=/var/lib/epimediahub
EPIMEDIAHUB_ADMIN_TOKEN=<random secret>
EPIMEDIAHUB_ADMIN_PASSWORD=<strong password>
EPIMEDIAHUB_SECRET_KEY=<random session secret>
PORT=8787
```

## 5. Verification

From outside the home network:

```text
https://setup.epimediahub.com/health
https://admin.epimediahub.com/admin/login
```

The health endpoint must return JSON with `status: ok`. Admin must show the EpiMediaHub login page. The local Flask/Gunicorn port 8787 must not be forwarded on the router.

## Release gate

Do not publish Android v0.4.18 to `android-latest` until `https://setup.epimediahub.com/health` works externally. v0.4.18 removes the old `epimedia.tail58077d.ts.net` Funnel endpoint and uses the owned domain instead.
