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

## Noch vor echter Produktion

Backend-Routen `GET /admin/mobile/bootstrap` und
`POST /admin/mobile/register` müssen auf dem **Admin-Dashboard-Host**
nach geschützter Prüfung installiert sein. Eine bloß lokal oder in GitHub
kompilierte APK aktiviert keine Servermeldungen. Die Alert-Datenadapter,
FCM-Serverversand, dauerhafte Vorfallhistorie, externe Ausfallüberwachung,
serverseitige Mehrfaktoranmeldung und signierte APK fehlen zum Teil noch
und dürfen nicht als einsatzbereit gelten.

## Tests

GitHub Actions erstellt ein **unsigniertes/verteilungsunfähiges Release und
nur für Entwicklung signiertes Debug-APK** als temporäres QA-Artefakt.
Eine endgültige Admin-App benötigt **einen eigenen** signierten Release-Key.
Nicht im Kunden-In-App-Updater veröffentlichen.
