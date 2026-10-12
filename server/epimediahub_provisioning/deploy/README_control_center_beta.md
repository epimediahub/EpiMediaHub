# EpiMediaHub Dashboard Beta – Hetzner Installation (12.10.2026)

## Umfang
- Das kompakte Kunden- und Reseller-Layout zeigt Kunden, Playlists, Geräte und Aktionen ohne zusätzliche Aufklappseiten.
- Vorhandene 7-Tage-VPN-Tests erscheinen nur dem Administrator, nur für korrekt zugeordnete Geräte und ohne Credit-Abzug.
- Admin-only Fehlerdiagnose unter `/admin/diagnostics` zeigt ausschließlich aggregierte Synchronisierungs- und VPN-Kennzahlen. Es werden keine Kundennamen, Playlisten-Zugangsdaten, Tokens, WireGuard-Private-Keys oder Rohlogs an die Diagnoseansicht übergeben.
- Die App-Jahreslizenz ist **nicht Bestandteil dieser Beta**, weil das verlässliche, ablaufende Server-Entitlement und seine Android-Kompatibilität zunächst zusammen implementiert und getestet werden müssen. Nicht als Vollversion ausgeben.
- Geräte-Crash- und Player-Berichte benötigen noch eine datensparsame, vom Kunden aktivierte App-Übermittlung. Die vorhandene Diagnose darf nicht als umfassende Absturztelemetrie bezeichnet werden.
- Die Prüfung bestätigt **keine** vollständige DSGVO-Konformität. Dafür sind u. a. Löschkonzept, Auftragsverarbeitung, Backup-Aufbewahrung und operative Rechteprüfung nötig.

## Geeigneter Host
Nur auf dem Host installieren, auf dem `epimediahub-provisioning.service`
in `/opt/epimediahub/provisioning` läuft und der die Kundendatenbank besitzt.
**Nicht** auf dem reinen EpiScene-Rechenserver oder dem Finnland-VPN-Gateway.

## Installation
1. Ein festes Git-Commit im Entwicklungszweig `feature/dashboard-hetzner-control-center-20261012` holen (Git sparse clone reicht).
2. `sudo python3 server/epimediahub_provisioning/deploy/install_control_center_beta.py --check` ausführen.
3. Nur nach `CHECK OK`: denselben Befehl mit `--apply` ausführen.
4. Ausgabe `INSTALL OK`, `/health`, `/admin`, `/reseller` und `/admin/diagnostics` prüfen.
5. Der Installer erstellt ein root-privates Backup in `/var/backups/epimediahub/dashboard-beta-...`, verändert keine bestehenden App- oder VPN-Credits und stellt Code bei Startfehlern wieder her. Datenbank wird vorab als konsistente SQLite-Kopie gesichert.

## Sicherheitsgrenzen
Das Skript verweigert die Installation, wenn das aktive VPN-Backend den einmaligen Test nicht kennt, die Server-Verzeichnisse abweichen, der Dienst nicht läuft oder die Vorprüfung nicht besteht. Es überschreibt **nicht** `license_api.py` oder `vpn_dashboard.py` und bewahrt vorhandene Dashboard-Navigationslinks (z. B. Credits) auf. Das Skript ist keine automatische Migration unbekannter Fremdversionen.

## Offene Freigabekriterien
Vor breitem Kundentest sind erforderlich: bestandene CI-Tests, echte Admin-/Reseller-Tests auf einem zweiten System, ein Gerätetest der VPN-Testfreigabe und eine Prüfung der gespeicherten Kundendaten und Backups. Für die App-Jahreslizenz müssen der Server- und der Android-Client dieselben ablaufenden Lizenztypen implementieren.
