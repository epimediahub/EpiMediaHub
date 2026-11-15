# EpiMediaHub Android 1.0.63

OK in either Live player opens the existing `Screen.Categories(LIVE)` route and restores the playing channel, its category, scroll position and focus. The separate channel dialog is no longer opened. Repeated returns do not stack player screens.

The boot preference uses the same `FocusCard` as the other settings. Its readable Ein/Aus subtitle changes on remote OK/Enter and preserves the existing opt-in preference and boot receiver.

The playing channel requests EPG immediately, including during stream preparation and zapping. A bounded queue reserves one provider slot for playback and one for browsing, promotes queued requests without duplicating them, drops superseded waiting playback requests, and retries missing or expired guides after a cooldown. Playlist revisions prevent late results from crossing sessions. Cached current events are reused immediately; banners select events by time and refresh at programme boundaries. Existing off-thread matching and station-group safety remain in place.

The Live information panel uses a smaller logo and one current/next programme block. The description receives the remaining height, uses brighter text and can scroll with the remote. Skin marks remain available in the compact header.

Regression coverage exercises request promotion under saturation, zapping, expired/unsorted EPG, reset races, category selection, real remote activation and focus, and description geometry and scrolling on a 350 dp panel. The signed build workflow runs the complete Android unit suite and verifies package/version/signature and the approved intro for all three APKs before the public updater is advanced. UI screenshots are recorded separately from the signed APK artifact.

Provider response time and availability still determine how quickly uncached programme data arrive. Version publication must be confirmed from the workflow result.
