# EpiMediaHub Admin – eigenständige private Android-App

**Entwicklungs-Build.** Dieses Projekt hat die eigene Package-ID
`de.epimediahub.admin` und ist vollständig vom TV-/Mobile-Player und dessen
Updater getrennt. Es implementiert eine Android-Hülle für das bestehende
`https://admin.epimediahub.com` mit geschützter WebView-Navigation,
Geräteentsperrung/Biometrie und einer opt-in FCM-Registrierung.

- Startbildschirm: native Navigation zu Übersicht, EpiScene-Analyse und Fehleranalyse.
- Admin-Login erfolgt auf dem EXISTIERENDEN HTTPS-Webdashboard; Passwort,
  API-Tokens und Playlist-Zugangsdaten werden nicht in der App gespeichert.
- Nur `admin.epimediahub.com` darf in der eingebetteten WebView laden.
  Sonstige HTTPS-Links werden an den externen Browser delegiert; HTTP ist gesperrt.
- App-Zugriff verlangt nach Start und nach erneuter Öffnung die lokale
  Geräteentsperrung bzw. biometrische Authentifizierung. Das ersetzt keine
  serverseitige MFA.
- Push wird erst auf expliziten Klick des Admins registriert. Die Android-App
  führt KEINE Playlisten-/Markeränderungen, Neustarts oder Freigaben automatisch aus.
- FCM erhält ausschließlich generische Alarmkategorien; keine Kundennamen,
  Geräte-IDs, Token, Playlist-Adressen oder Zugangsdaten in Benachrichtigungen.

## Firebase/FCM: ausschließlich private App

Diese vier Build-Variablen müssen auf der privaten Release-Pipeline gesetzt sein
(keine Service-Account-JSON in der App, keine Schlüssel für FCM-Versand):
`EPI_ADMIN_FIREBASE_APP_ID`, `EPI_ADMIN_FIREBASE_API_KEY`,
`EPI_ADMIN_FIREBASE_PROJECT_ID`, `EPI_ADMIN_FIREBASE_SENDER_ID`.

Ohne diese Konfiguration startet die App mit Dashboard, aber Push bleibt
deaktiviert. Nur ein Backend mit autorisierter Firebase-Cloud-Messaging-
Serveridentität darf Benachrichtigungen senden.

## Verbindung zum Backend – vorbereitet, NICHT installiert

Im selben Entwicklungszweig liegen unter `tools/epimediahub-admin/`:
- `mobile_flask.py`: geschützte Admin-Sitzungsrouten
  `GET /admin/mobile/bootstrap`, `POST /admin/mobile/register`,
  `POST /admin/mobile/unregister`, `GET /admin/mobile/alerts`
  und `POST /admin/mobile/ack/<key>`. CSRF ist für jeden Schreibzugriff
  erforderlich. Die bestehende Web-Admin-Anmeldung bleibt die Autorität.
- `mobile_registry.py`: max. 20 Admin-Geräte; private SQLite-Registrierung,
  per Geräteaktion widerrufbar; persistente Push-Outbox für Retry.
- `monitor_rules.py` und `incident_store.py`: die sieben abgestimmten
  Kategorien, Deduplizierung, Bestätigung und Historie.
- `fcm_sender.py`: Google FCM HTTP v1 nur auf dem Server via
  `google-auth`, niemals mit Service-Account-Schlüssel in der APK.
- `live_analysis_snapshot.py`: schreibgeschützter Live-Adapter für
  EpiScene-Lanes 8/10, **ohne** IPTV-Zugangsdaten.
- `monitor_cycle.py`: verifiziert eine ausschließlich numerische,
  frische und private Snapshot-Datei und versendet kategorische Alarme
  an ausdrücklich registrierte Admin-Geräte. Fehler bleiben in der Outbox.

Alle diese Teile sind ausschließlich **GitHub-Code**. Der bestehende
`epimediahub-provisioning.service` wurde bislang nicht geändert.
Für automatische Meldungen ist noch ein geprüftes Monitoring-Schedule am
tatsächlichen Dashboard-Host erforderlich; für komplette Server-Ausfälle
braucht es einen **externen** Health-Check, nicht nur die interne Prüfung.

## Vor der produktiven Freigabe

1. Backend-Zielhost, HTTPS, bestehende Dashboard-Session und die
   vollständige Rollen-/CSRF-Trennung abnehmen. Die API darf nicht
   öffentlich ohne Admin-Login erreichbar werden.
2. Firebase-Projekt **nur für** `de.epimediahub.admin` einrichten;
   FCM-Serverzugang ausschließlich auf dem geschützten Hetzner-Host.
   Privates Service-Account-JSON nie ins Repo, Handy oder Chat kopieren.
3. Die sieben Metrikquellen anbinden und separat testen: EpiScene-
   Fortschritt (vorbereitet), Playlistablauf, Worker-Version,
   externe API-Verfügbarkeit, GitHub Builds/Sync, anonyme aggregierte
   Wiedergabefehler sowie Berlin-Tagesbericht.
4. Server-Betreiber-MFA, Backup/Restore, Logs/Retention, Push-Austritt,
   Fehlalarmtests, Benachrichtigungsberechtigung und physisches Android-
   Gerät testen; insbesondere Wiedergabefehler nur aus wirklich ausreichend
   aggregierten anonymisierten Zählwerten ableiten.
5. Eigener dauerhafter Android-Admin-Release-Key und
   unternehmensinterne private Verteilung. Keine Signatur teilen und
   niemals den Kunden-Updater für diese App verwenden.

**Keine globale Produktivfreigabe**, bevor diese Punkte abgeschlossen sind.

## Tests

GitHub Actions erstellt ein **unsigniertes/verteilungsunfähiges Release und
nur für Entwicklung signiertes Debug-APK** als temporäres QA-Artefakt.
Eine endgültige Admin-App benötigt **einen eigenen** signierten Release-Key.
Nicht im Kunden-In-App-Updater veröffentlichen.
