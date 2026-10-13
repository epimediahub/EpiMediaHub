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

## Nachtrag: vorhandene ältere VPN-Installation

Die produktive VPN-Datei vom 13.10.2026 hat den SHA-256-Fingerprint
`1417f694f32f3b66ad715efad7c3cd8f76f0d6ccdcda6445cc4c8737294ee91a`
und enthält noch keinen einmaligen 7-Tage-Test. Diese exakt geprüfte alte
Version ist im Installer nun explizit zugelassen; andere Abweichungen werden
abgewiesen. Die geprüfte neue VPN-Datei hat den Fingerprint
`e52391fe2c34c93f35e10fd1a3d2e4eaa351bd0ad55a47f63ec574c933c15c22`.

Der Installer nimmt `vpn_dashboard.py` in seine gesicherten Dateien auf und
testet zunächst ausschließlich auf einem SQLite-Snapshot. Dabei vergleicht
er vorhandene Kunden-, Lizenz-, Geräte- **und VPN-/Credit-Tabellen** vor und
nach dem Test. Existierende VPN-Geräte, Guthaben und Zuordnungen dürfen
sich dabei nicht verändern. Die neue Tabelle `vpn_trials` ist additiv;
keine bestehende VPN-Laufzeit wird automatisch verlängert. Ohne erfolgreiche
Prüfung kein `--apply`.

Prüfung der aktualisierten Version auf dem Dashboard-Host:

```bash
git -C /root/epimediahub-check pull --ff-only
git -C /root/epimediahub-check rev-parse HEAD
python3 /root/epimediahub-check/server/epimediahub_provisioning/deploy/install_control_center_beta.py --check
```

Alle Befehle einzeln ausführen. **Kein `set -e` in der interaktiven SSH-Sitzung**
und noch kein `--apply`. Fehlertext zur Diagnose ohne Session-Keys,
Tokens oder Kundeninhalte mitteilen.

## GitHub-Änderungen
- Dashboard mit API-Sicherheit und Installationsschutz: PR #56, Zweig `feature/dashboard-hetzner-control-center-20261012`.
- Android 1.0.64 mit jährlichem Lizenzstatus und Opt-in-Absturzmeldung: PR #57, Zweig `feature/v164-annual-license-ui`.
Beide PRs bleiben Draft bis alle Validierungen und der Betreiber-Test abgeschlossen sind.

## Read-only Preflight auf Hetzner (erst nach signierter APK-Qualifikation)

Weil das GitHub-Repository privat ist, müssen die GitHub-Zugangsdaten auf dem
Server einem eingeschränkten Deploy-Key oder einer bereits autorisierten
`gh auth login`-Sitzung zugeordnet werden. Zugangstoken niemals als
Befehlsargument, Git-URL, Shell-History oder Chat-Nachricht verwenden.

Das **noch nicht ausgeführte** Preflight-Verfahren ist:

```bash
set -euo pipefail
command -v gh >/dev/null
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
gh repo clone epimediahub/EpiMediaHub "$tmp/repo" -- \
  --depth 1 --filter=blob:none --sparse \
  --branch feature/dashboard-hetzner-control-center-20261012
git -C "$tmp/repo" sparse-checkout set server/epimediahub_provisioning
git -C "$tmp/repo" rev-parse HEAD
sudo python3 "$tmp/repo/server/epimediahub_provisioning/deploy/install_control_center_beta.py" --check
```

Bevor `--apply` gestattet wird, den angezeigten Commit-SHA gegen die
freigegebene GitHub-Revision vergleichen, `CHECK OK` prüfen, die
`epimediahub-provisioning.service`-Servicekonfiguration mit Host und
Persistenzpfad abgleichen und ein externes, getestetes Backup vorhalten.
Niemals auf VPN-Gateway oder separatem Analyzer ausführen. Bei Fehlern
keine automatische Ausweichinstallation versuchen.

Nur nach unabhängiger Sicherheitsfreigabe kann derselbe geprüfte
Installer mit `--apply` laufen. Er sichert vorhandene Dateien und
`provisioning.db`, stoppt den Dienst kurz, aktualisiert Code,
prüft `/health` und die Jahreslizenz-Capabilities und rollt Code bei
einem Fehler zurück. Bestehende Datenbank bleibt erhalten.

### Betreiber-Abnahmetest
Mit einem isolierten Testkunden auf dem echten Dashboard prüfen:
Kunde und Playlist anzeigen/ändern, Gerät zuordnen, einmaligen VPN-Test
ohne Credit-Abzug starten, Jahreslizenz einmal aktivieren und anschließend
erneuten Klick ohne Verlängerung, Laufzeit/Entzug und Sichtbarkeit in der
Android-App. Danach unbedingt Reseller-Rollentrennung, Abmelden/Login,
Staging-Fehlerfälle und Schutz der Playlist-Passwörter kontrollieren.

Das Erfüllen der CI beweist nur automatisierte Tests, nicht die
Erfolgsprüfung dieser betrieblichen Schritte.
