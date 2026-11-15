# EpiMediaHub VPN Finland – test-first integration

Base: `android-v1.0.33-storage-controls`. This branch contains a **routing-safety foundation only**.
It does NOT contain a working WireGuard client, license service, user interface, or signed APK. Production is unchanged.

## Requirements

- VPN is optional, paid, **one license per device**. First exit is Finland only.
- Playlist choices are independent: e.g. 4K DIRECT, IPTV The Best FINLAND.
- If VPN is enabled for a playlist: fail closed on missing/expired entitlement, wrong device,
  missing consent, broken tunnel, non-Finnish exit or unverified playback engine.
- When a direct playlist is selected, do not resume it while the app-wide tunnel remains on;
  shut down the old stream, reconcile the VPN, verify DIRECT, then play.
- Android `VpnService` supports VPN selection **per app, not per playlist**.
  `addAllowedApplication` must restrict to the EpiMediaHub app. Other Android apps stay direct.
- Media3 and native libVLC are two networking paths. VLC requires independent network tests.
  Other EpiMediaHub traffic (SmartTube, Radio, API, subtitling, HLS child requests) also requires
  explicit routing verification; the policy alone does not route packets.
- Keep test WireGuard QR and private keys **out of Git and the shipping APK**.
  Distinct device peers and server-enforced expiry/revocation must be issued by a secure backend.
- Audit DNS, IPv4/IPv6 leakage, redirects, connection handoffs and system VPN conflicts on Fire OS.

## Gate to implementation

1. Prove that the official WireGuard Android tunnel `GoBackend` works with the app and target Fire TV.
2. Implement lifecycle-bound, app-only `VpnService` + explicit user consent;
   never turn it on just because a playlist setting exists.
3. Add a playlist-switch state machine and VPN/direct media transport that can prove its routing.
4. Wire a verified short-lived entitlement into the routing policy (deny until device-bound proof).
5. Build signed beta APK; measure Finland IP vs direct public IP with authorized streams,
   both Media3 and VLC. Test tunnel down, revoked license, app restart, network switch and IPv6.
6. Only then expose VPN purchase, admin/reseller credits and public UI.

## Portable tests

```bash
kotlinc V134VpnRoutingPolicy.kt V134VpnRoutingPolicyTest.kt -include-runtime -d /tmp/vpn-routing-tests.jar
java -cp /tmp/vpn-routing-tests.jar de.epimediahub.app.vpn.V134VpnRoutingPolicyTest
```
