# EpiMediaHub Admin — EIN fertiger Releasepfad (noch nicht produktiv)

**Vereinbarung:** Keine weiteren Zwischen-APK-Installationen beim Betreiber.
Native Admin-Oberfläche, Anmeldung, Alarme, Firebase, stabil signierter Release
und In-App-Updates werden zusammen abgenommen. Die IPTV-/Reseller-App bleibt
unverändert.

## Stand des Quellcodes

- Android-Paket: `de.epimediahub.admin`, vollständig native Compose-Startseite,
  Kunden/Reseller/Playlists/Geräte, EpiScene-Status und gated Markerprüfliste,
  Meldungen, Anbieter-Ablaufberichte mit Android-Druckfunktion,
  Android-Entsperrung und Push-Opt-in; **keine eingebettete WebView**.
- Android-Updater: private HTTPS-Endpunkte
  `/admin/mobile/update/status` und `/admin/mobile/update/apk`.
  Nur mit Dashboard-Session, Paket/Version/Größe/SHA256 geprüft; APK-
  Signatur muss zu installierter App passen; Android fragt vor Installation.
- Server: `mobile_flask.py`, `mobile_updates.py`, `publish_private_release.py`,
  `sync_private_updates.py`, `admin_monitor_runner.py` und
  `deploy_admin_all.py` (einmaliger guarded Install).
- Firebase **Android-Client** wurde bereits als GitHub Secret
  `EPI_ADMIN_FIREBASE_CLIENT_JSON` eingerichtet; die **Server-Sendeidentität**
  ist davon getrennt und noch nicht installiert.
- 7 Alarmarten wurden regelbasiert implementiert. **Nur** EpiScene-Lanes 8/10
  sind bereits mit einem schreibgeschützten Live-Snapshot verbunden. Für die
  anderen echten Quellen müssen separate verifizierte Adapter entstehen.
  Ausfall des Hetzner-Hosts muss von AUSSEN geprüft werden.

## Einmalige Betreiber-Einrichtung – erst nach Code-Abnahme

1. Signatur: `create_release_signing_identity.sh` lokal **einmal** ausführen.
   Es erstellt eine dauerhafte 3072-Bit-RSA-Identität und eine private JSON-Datei.
   Den JSON-Inhalt als **ein** GitHub-Actions-Secret
   `EPI_ADMIN_RELEASE_SIGNING_JSON` setzen. JSON niemals in Chat/Git-Commits
   kopieren. Keystore und Geheimdaten separat verschlüsselt sichern.
2. Firebase: im existierenden Projekt `epimediahub-admin` eine eng begrenzte
   FCM-HTTP-v1-Sendeidentität einrichten. Nur auf Hetzner unter
   `/var/lib/epimediahub/admin-mobile/firebase-fcm-service-account.json`
   ablegen: 0600, Eigentümer bestehender **Nicht-root**-
   `epimediahub-provisioning.service`-Benutzer. Niemals ins Handy/Repo/Chat.
3. Private Release-Abholung: einen Fine-grained GitHub-Token mit minimalen
   `Actions: read` Rechten für das eine Repo unter
   `/var/lib/epimediahub/admin-mobile/github-actions.token` als 0600 ablegen,
   Eigentümer derselbe Service-Benutzer. Beide Geheimdateien liegen im
   0700-Verzeichnis `admin-mobile`.
4. Das Dashboard muss auf dem angegebenen Hetzner-Host laufen. Bevor die
   einmalige Serverinstallation erlaubt wird, prüft
   `deploy_admin_all.py --check` nicht-root-Service, sichere Session-Cookies,
   gültige Datenbank, FCM-Identität, GitHub-Token und alle bestehenden Dateien.
   Erst **ein** ausdrücklich genehmigtes
   `EPIMEDIAHUB_ADMIN_INSTALL_CONFIRMED=YES python deploy_admin_all.py --apply`
   installiert Backend und zwei Timer: 5-Minuten EpiScene-Monitor und
   stündlichen privaten Admin-Release-Abgleich. Die vorhandene Dashboard-
   API wird dafür EINMAL geschützt neu gestartet und vorher gesichert.
5. Release: nach Merge in `main` private Android-Release-GitHub-Aktion mit
   eindeutig höherem `version_code` ausführen. Die Action verlangt die
   feste Signatur und stellt das verifizierte APK im Actions-Artefakt bereit;
   der Hetzner-Timer synchronisiert es. Die App zeigt es ausschließlich einem
   angemeldeten Administrator an. Nach einer final signierten
   Erstinstallation sind alle folgenden Updates In-App-Vorgänge.

## Sicherheits- und Produktfreigabe

- **Wichtig:** Das Quell-Repository ist derzeit **PUBLIC**. GitHub-Actions-
  Artefakte können deshalb auch für andere Repo-Betrachter zugänglich sein.
  APK-Geheimhaltung nicht mit Admin-Sicherheit verwechseln: Schutz basiert
  auf Server-Admin-Session, MFA und Signaturprüfung, niemals auf versteckten
  APK-URLs. Für tatsächlich vertrauliche APK-Artefakte ist vor finaler
  Verteilung ein separates **privates** Release-Repository oder CI-Deploy
  direkt auf Hetzner erforderlich.
- Firebase-Clientdaten sind keine Server-Sendegeheimnisse.
- Testen: Signatur/Update über zwei Versionen, Gerätewechsel, Update-Abbruch,
  abgelaufene Sitzung, Push während App geschlossen ist, Token-Rotation,
  Serverneustart, Reseller- und Kundentrennung, Nginx HTTPS und Recovery.
- Ein fehlerhafter oder fehlender Telemetriesensor darf **nie** als gesund
  dargestellt werden. Nur EpiScene-Messwerte sind bisher verifiziert.
- Eine reine Android-GitHub-CI-`success` Meldung bedeutet **nicht**
  automatisch, dass die Serverinstallation, der Pushversand oder die mobile
  Darstellung aller produktiven Webseiten getestet wurden.

**Dieser Zweig ist ein Entwicklungszweig und darf vor Abschluss der
Produktionsprüfung nicht als fertiges APK freigegeben werden.**
