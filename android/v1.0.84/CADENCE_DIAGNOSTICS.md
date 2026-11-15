# EpiMediaHub v1.0.84 — isolated cadence diagnostics

This branch is **not** a customer release. It starts from the exact successful v1.0.84 release commit `662718fc598e147b746ee471a860e72d53f6b5b2`.

## Existing implementation
- `V121VodSurface.kt` already owns the Media3 frame-rate hint and reports content FPS, actual display refresh, rendered/dropped buffers and codec via `V122PlaybackSnapshot`.
- `V170LiveCadencePolicy.kt` already maps 25/50 fps to 50 Hz without changing resolution.
- `V168VlcVodPlayer.kt` is a separate playback backend; this patch intentionally does not alter VLC.
- The v1.0.84 release workflow reconstructs the app from `android/source_parts` and applies versioned Python patches. Editing legacy `android/v0.4.x` files would not affect the current release.

## Apply to a reconstructed development build only

After the v1.0.84 workflow's `python3 android/v1.0.84/patch_v184.py` step, run:

```bash
python3 android/v1.0.84/patch_cadence_diagnostics.py
```

The patch requires `PROJECT_ROOT` and fails closed if the expected controller anchor is absent. It adds a throttled `EpiMediaHubCadence` log when Media3 reports dropped video frames. Logs include aggregated drops, metadata and measured FPS, actual display Hz, the last frame-rate request and decoder. No additional display switch or clock correction is introduced.

## Before proposing a release
1. Reconstruct v1.0.84 in CI and apply this patch, compile and run existing unit tests.
2. Exercise 25-fps soccer at 50 Hz, 50-fps sports, 23.976/24-fps films, and SmartTube 30/60-fps video on Fire TV and GalaBox.
3. Record `adb logcat -s EpiMediaHubCadence EpiMediaHubVideo`, together with the existing playback snapshot. Do not log URLs, credentials or playlist tokens.
4. Check dropped-frame bursts versus actual Hz and buffering before changing audio clocks or frame-rate policies.
5. Keep all release/updater publishing steps disabled until approved.

No release workflow, production updater manifest or customer APK is changed by this branch.
