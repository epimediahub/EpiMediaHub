# VPN Finland — stage 2 implementation status (2026-10-08)

## Implemented on this development branch

- `V134VpnRoutingPolicy.kt` — fail-closed decisions for per-playlist desired route, device entitlement, expiry, and separately verified playback engine.
- `V134WireGuardDeviceTunnel.kt` — **isolated** GoBackend adapter for embedded WireGuard for Android (user VPN consent required).
- Only permits `IncludedApplications = <EpiMediaHub Android package>`; rejects configurations that would transparently tunnel every app.
- Calls `setState(UP/DOWN)` on explicit requests; **no automatic use** at app startup.
- `patch_wireguard_spike.py` — guarded opt-in patch adding Maven Central WireGuard dependency and VpnService manifest declaration into a **test** reconstruction of Android v1.0.33.
- Portable routing policy test: **16 safety cases passed locally**. Native Android bridge was NOT compiled or device-tested yet.

## Important limitations

1. Existing EpiMediaHub app (production updater / APK) has **not** been modified. No beta APK has been built.
2. App-wide VPN mode while active also affects the app's background requests (SmartTube, Radio, APIs). **Not streaming-only.** For a stream-only guarantee, further network routing work is needed.
3. Only the app is allowlisted: other apps on Fire TV should not be tunneled, subject to device verification.
4. Native libVLC, Media3, redirects, DNS, IPv6, HLS child requests and VPN handover must be tested on hardware before use.
5. An UP tunnel does not prove Finnish egress or absence of leaks; additionally probe through the intended media transport. For VPN-enabled playlists, playback must stay blocked until verified.
6. App may not have valid consent on Fire TV, and other VPN apps may conflict.
7. Existing mobile WireGuard QR is a **temporary test credential**, not a reusable commercial client profile.
8. Device-specific private keys and provisioning data must be generated and protected; **never** add test keys or QR codes to Git.
9. Paid one-device licenses, renewal, reseller credits, peer isolation, revocation, traffic controls and privacy notices are separate backend work.

## Next executable milestone

- Run a non-releasing Android CI build of the isolated WireGuard adapter against the official AAR.
- Present an explicit consent-only internal Fire TV diagnostic screen to launch or end tunnel, without touching existing media player.
- Give **one unique test peer** to the test device by a secure provisioning route, not bundled APK.
- Confirm IP address before and during VPN with authorized playback, measure latency and buffer, verify network switching and no streaming leak on tunnel failure.
- Only after these checks integrate the playlist selector and paid device entitlements.

**No changes to running Hetzner systems are part of this branch.**
