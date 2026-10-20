# EpiMediaHub Admin – freigabegeschützter Deploymentplan (Entwicklung)

Diese eigenständige Android-App **ist nicht die IPTV-Kunden-App**. Ihr
Paketname lautet `de.epimediahub.admin`. Die sieben genehmigten Regeln sind
in `monitor_rules.py`. Der GitHub-Quellcode allein verschickt keine Pushs.

## 1. GitHub-Teststand

- Android: `android/admin-app`, Gradle-Build und Android Lint unter
  `.github/workflows/epimediahub-admin-android-qa.yml`.
- Admin-Backend: `tools/epimediahub-admin`, Python 3.12/Flask Regressionen.
- Test-APK: nur Debug-Signatur des einzelnen GitHub-Runners, nicht stabil
  für Updates und nicht für Kundendistribution. Der richtige APK-Schlüssel
  muss separat und dauerhaft verwaltet werden.

## 2. Sichere Serverintegration, nur Dashboard-Host

Die separat entwickelten Flask-Routen müssen in die produktive
`epimediahub-provisioning.service`-App eingebunden werden. Der vorbereitete
`install_mobile_backend.py` greift **ausschließlich** auf
`/opt/epimediahub/provisioning` zu und akzeptiert nur `--check` oder
ausdrücklich freigegeben `--apply`. Er prüft Service-Pfad, nicht-root
Servicekonto, starken dauerhaften Session-Key, Secure-Cookies und die
erwartete vorhandene Admin-/CSRF-Registrierung. Vor `--apply` muss der
Produktionsbesitzer die Änderung freigeben. Beim Apply wird die Datenbank
online gesichert und der WSGI-Hook additiv installiert, niemals bestehende
Reseller-, Lizenz- oder VPN-Dateien überschrieben.

Es erfolgt **kein** automatischer Live-Deploy durch GitHub CI. Auf dem
falschen Server (Finnland-WireGuard-Gateway, reiner Worker) darf das
Installationsskript nicht verwendet werden. Bei unbekannten Dateien
stoppt es statt lokaler Anpassungen zu überschreiben.

## 3. Firebase nur auf der Server-Seite freischalten

- Privates Firebase-Projekt für Package `de.epimediahub.admin` anlegen.
- Build-Variablen:
  `EPI_ADMIN_FIREBASE_APP_ID`,
  `EPI_ADMIN_FIREBASE_API_KEY`,
  `EPI_ADMIN_FIREBASE_PROJECT_ID`,
  `EPI_ADMIN_FIREBASE_SENDER_ID`.
- Serverseitiges `EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID` und
  eine private Google-Application-Default-Credential-Identität konfigurieren,
  die ausschließlich FCM `messages:send` autorisiert.
- `google-auth` nur in der Server-venv installieren. Den Service-Account-Key
  weder an Android ausliefern noch in GitHub committen, Chat kopieren oder
  in öffentlichen Fehlerlogs ausgeben.
- Test der expliziten `POST /admin/mobile/register`- und
  `/unregister`-Routen mit Testadmin, Überprüfung von Gerätebindung,
  Retention und erfolglosen Zustellversuchen.

## 4. Live-Alarme

`live_analysis_snapshot.py` deckt momentan den sicheren, nur lesenden
EpiScene-Fortschritt der **separaten Analyse-Playlisten 8 und 10** ab.
`monitor_cycle.py` nimmt ausschließlich eine zeitnahe numerische Snapshot-
Datei aus einem 0700-Verzeichnis an, dedupliziert Vorfälle und verwendet
die persistente 0600 Push-Outbox.

Noch anzubinden und zu testen: valide Playlistabläufe/403, Worker-Versionen,
**externes** API-Uptime-Monitoring, GitHub-Build-/Updater-Fehler, verlässlich
anonym aggregierte Kunden-Wiedergabefehler und der tägliche EpiScene-Bericht
nach Berliner Datum. Ohne echte, verlässliche Metrikquelle darf keine
Benachrichtigung als aktiv dargestellt werden.

## 5. Betreiber-Freigabe

- Login, Session-Ablauf, MFA, Biometrie und lokaler Geräteverlust.
- Gerät registrieren und widerrufen, neuer FCM-Token nach Rotation.
- Nachricht empfangen, während die App nicht sichtbar ist, auch nach
  Serverneustart und während einer FCM-Zustellstörung.
- Admin-Dashboard & Reseller-Rollentrennung, TLS, Backup und Restore.
- Eigene Release-Signierung, GitHub QA-Artefakt nie im Kunden-Updater.
- Keine automatischen Worker-Neustarts oder Freigaben durch Alarme.

**Stand:** Implementierungsbasis und CI-Tests vorhanden; wirkliche
Push-Zustellung/Produktivdeployment und Abnahme noch ausstehend.
