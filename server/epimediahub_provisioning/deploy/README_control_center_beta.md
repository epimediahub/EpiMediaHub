# EpiMediaHub Admin & Reseller – Release-Prüfung (12.10.2026)

## Fertiggestellter Entwicklungsumfang
- Admin-/Reseller-Oberflächen zeigen Kunden, Playlists und Geräte mit kompakten Aktionen auf derselben Seite, auch mobil.
- Der manuelle, einmalige VPN-Test für 7 Tage wird nur vom Administrator für ein zugeordnetes Gerät ausgelöst, benötigt den bestätigten Finnland-Agenten und verbraucht keine Credits.
- Separate **365-Tage-App-Lizenz** per Admin-Button, einmalig pro aktivem Zeitraum. Sie verlängert sich **nicht automatisch** durch wiederholtes Klicken, wird dokumentiert, kann manuell entzogen werden und berührt keine Lifetime- oder Reseller-Credits.
- Jahreslizenz ist an den bereits bekannten geheimen `trial_key_hash` des konkreten registrierten Geräts gebunden. Eine bloß kopierte Geräte-ID reicht nicht. Ohne vorherige Lizenzstatusmeldung ist der Freigabeknopf absichtlich gesperrt.
- Bestehende Lifetime-Lizenzen haben Vorrang und werden nicht herabgestuft. Android bis v1.0.63 erkennt die Jahresberechtigung kompatibel als aktive Laufzeit; Android v1.0.64 Entwicklungszweig interpretiert `ANNUAL_ACTIVE` und `ANNUAL_EXPIRED` einschließlich korrektem Badge.
- Geschützte Fehlerübersicht mit Synchronisierungs-, VPN- und Lizenzkennzahlen. `POST /v1/device/error-report` akzeptiert ausschließlich Kategorien mit expliziter Zustimmung und gültigem Geräte-Session-Token. Keine freien Fehlermeldungen, Stream-URLs, Stacktraces oder Zugangsdaten. Max. 25 Meldungen je Gerät/24 h, automatische Löschung der Einzelmeldungen nach 30 Tagen beim nächsten Bericht.
- Android v1.0.64 Entwicklungszweig bietet eine standardmäßig **ausgeschaltete** Option für anonyme Absturzberichte. Ein Absturz speichert lediglich ein Ja/Nein-Flag und meldet beim nächsten gesunden Start die Kategorie CRASH/OTHER; originale Android-Crashbehandlung bleibt erhalten.
- CSRF-Schutz mit geheimem Session-Token für Admin-/Reseller-Browserformulare, bestehender separater VPN-CSRF-Schutz bleibt intakt. Dashboard-Seiten liefern no-store und Schutz-Header; Reseller-Mandantentrennung bleibt erhalten.

## Wichtig: noch keine Produktionsfreigabe
Es ist **noch nichts installiert oder für Endkunden veröffentlicht**. Vor dem ersten Produktiv-Update müssen die gesamte Android-v1.0.64-Kompilierung und Android-Unit-Tests, korrekte APK-Signierung sowie reale Fire-TV-Tests abgeschlossen sein. Die separate Dashboard-GitHub-CI prüft Python, Flask, SQLite, Authentifizierung, VPN und das kompakte Layout. Eine erfolgreiche CI allein beweist keine getestete Hetzner-Installation.

Außerdem sind vor größerem Kundeneinsatz organisatorische Datenschutzaufgaben zu erledigen: TLS-/Cloudflare-Konfiguration und Zugriffsprotokolle prüfen, Backup-Retention festlegen, AV-Verträge/Datenschutzhinweise prüfen und rollenbezogene Zugriffe auf dem produktiven Server testweise verifizieren. Das ist keine pauschale DSGVO-Zertifizierung.

## Geeigneter Installationshost
Nur der Host, auf dem `epimediahub-provisioning.service` unter `/opt/epimediahub/provisioning` läuft und die Kundendatenbank vorhanden ist. Nicht der separate VPN-Gateway oder reine EpiScene-Rechenserver.

## Schutzmechanismen des Installers
`deploy/install_control_center_beta.py` hat zwei explizite Modi: `--check` (keine Produktivänderungen) und `--apply` (nach erfolgreichem Preflight mit Sicherung). Er stoppt bei unbekannten Serverversionen, fehlenden VPN-Freigaben, schwachen/flüchtigen Session-Secrets, unsicheren Cookies, fehlerhaften Lizenzrouten oder fehlgeschlagenem Datenbanksnapshot. Vorhandenes kompatibles `license_api.py` und Credit-Templates werden **nicht überschrieben**. 
Datenbankkopie und ersetzte Dateien liegen nur für root zugänglich unter `/var/backups/epimediahub/`; bei Servicefehlern rollt der Installer geänderten Code zurück, ohne bestehende Kunden, Playlists, VPN-Credits oder Lifetime-Lizenzen zu löschen. Zusätzliche neue Tabellen werden bei einem Fehler nicht automatisch aus der Datenbank entfernt.

## GitHub-Änderungen
- Dashboard mit API-Sicherheit und Installationsschutz: PR #56, Zweig `feature/dashboard-hetzner-control-center-20261012`.
- Android 1.0.64 mit jährlichem Lizenzstatus und Opt-in-Absturzmeldung: PR #57, Zweig `feature/v164-annual-license-ui`.
Beide PRs bleiben Draft bis alle Validierungen und der Betreiber-Test abgeschlossen sind.
