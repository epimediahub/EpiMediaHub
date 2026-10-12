# Android v1.0.64 — Jahreslizenz und freiwillige Diagnose

Entwicklungs-Patch auf Basis von v1.0.63. Keine Freigabe über den In-App-Updater,
keine öffentliche APK, keine Änderung an EPG, VPN-Routing oder Playerwahl.

## Jahreslizenz
Nach erfolgreichem Backend-Update sendet der Client
`supported_entitlements=["ANNUAL"]` an `/v1/license/status`.
`ANNUAL_ACTIVE` erlaubt Wiedergabe und zeigt die verbleibenden Tage als
APP-LIZENZ, `ANNUAL_EXPIRED` sperrt den Inhalt und nennt die Jahreslizenz.
Bestehende 7-Tage-Testphase und Lifetime bleiben bestehen.
Es gibt keine automatische Verlängerung.

## Freiwillige Absturzmeldung
In Einstellungen gibt es eine separate Karte
**Anonyme Fehlerberichte**, standardmäßig ausgeschaltet.
Nach ausdrücklichem Einschalten wird beim Absturz lediglich ein Flag auf dem
Gerät gespeichert. Erst beim nächsten erfolgreichen Start kann mit dem
vorhandenen Geräte-Session-Token ein einzelner kategorisierter Bericht an
`/v1/device/error-report` gehen. Kein Stacktrace, keine Film-/Sendernamen,
URLs, Playlist-Zugangsdaten, Standort oder freier Text.
Ausschalten löscht den anstehenden Bericht. Die ursprüngliche Android-
Absturzbehandlung bleibt erhalten. Auf Serverseite gilt max. 25/Tag/Gerät
und 30-Tage-Retention für Einzelereignisse.

## Prüf- und Release-Grenze
Vor produktiver Verteilung:
- kompletter Kotlin-Compile und Android-Unit-Test
- drei signierte APK-Varianten und Zertifikat-/Versionsprüfung
- echte Fire-TV-/Android-TV-Prüfung inklusive Ablauf, WLAN-Ausfall,
  Geräte-Neukopplung und Kindersicherung
- live bestätigtes Jahreslizenz-/Opt-in-Bericht-Backend
- danach manuelle Freigabe des In-App-Updaters durch den Betreiber

Der isolierte Workflow `android-v164-annual-qa.yml` baut nur Debug und
führt Tests aus. Er veröffentlicht nichts.
