# GalaBox-only VPN MTU A/B test (private APK 1.0.76)

The Finnish WireGuard host, its wg0 MTU, all other customer peers,
the existing permanent Fire TV tunnel, VPN licenses, device session tokens,
and all encryption keys remain unchanged. No in-app updater publication.

The selector is visible ONLY when both manufacturer or model contain
"galabox" and the Android package is the official non-Amazon app.

The default selection "Automatisch (bisherig)" produces exactly the
previous Interface profile string; selecting a value adds one MTU line
to the local [Interface] section. There is no server-side change.

## Test with one GalaBox

1. Before choosing a new value, use the app speedtest on THE BEST VPN
   and note single/dual/four-stream readings and HTTP latency.
2. In settings VPN & Netzwerk, press GalaBox MTU-Test once
   ("Automatisch" to 1360 Bytes).
3. Explicitly tap "VPN trennen · Direktverbindung", wait for confirmation.
   Without this, the active Android TUN may keep its old MTU.
4. Tap "Finnland-VPN verbinden / prüfen" and require the known Finnish
   exit IP 37.27.42.215 before any measurement or IPTV playback.
5. Run the *same* speedtest twice, recording four-stream throughput
   and the endpoint.
6. Repeat for 1280 and 1420 Bytes if necessary. One click cycles:
   automatic -> 1360 -> 1280 -> 1420 -> automatic.
7. Restore "Automatisch (bisherig)" and reconnect before concluding,
   unless one stable setting is explicitly chosen for GalaBox use.

If the test value prevents tunnel establishment, do not relax kill-switch
routing or remove the license. Choose the next test value or revert
to automatic, and reconnect manually. Never test by disabling the VPN
in the background or changing any Fire TV client.

A speed increase from 32.6 Mbit/s is not guaranteed. Repeated identical
testserver measurements are needed to distinguish noise from a real MTU effect.
