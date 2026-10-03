# Credits und Geräte-Lizenzen für Android 1.0.20

Dieses Update ergänzt den vorhandenen Raspberry-Server 0.8.x. Die API-Version
bleibt 0.8.2, damit die bestehenden Funktionen und die Intro-Analyse unverändert
bleiben. Die Lizenz-API meldet separat `license_version: 1.0.20`.

- Neue Geräte erhalten 7 Tage Testzeit. Bereits registrierte Geräte behalten ihre
  Freischaltung; die Migration erfasst sie einmalig vor dem App-Update.
- Ein Reseller-Credit aktiviert ein Gerät dauerhaft.
- Jeder Reseller erhält seinen eigenen, vom Admin festgelegten Preis. Neue Konten
  haben keinen voreingestellten Preis. Ohne Preis können keine Credits bestellt
  werden. Bestehendes Guthaben kann weiterhin verwendet werden.
- Preisänderungen verändern keine bestehenden Bestellungen. Die Zahlungsfreigabe
  bucht eine Bestellung höchstens einmal gut.
- Endkunden ohne Reseller zahlen einmalig **10 Euro pro Gerät**. Der Admin bestätigt
  den Zahlungseingang bei der Freischaltung. Es wird kein künstliches Resellerkonto
  angelegt und kein Reseller-Guthaben abgezogen.
- Reseller können eine Lizenz zweimal kostenlos auf ein eigenes Ersatzgerät
  übertragen. Weitere Übertragungen sind über den Admin möglich.

## Installation auf dem bestehenden Raspberry

`deploy/install_credits_v120.py` enthält den geprüften Code und die beiden neuen
Templates als komprimiertes Paket mit SHA-256-Prüfsumme. Den Installer aus einem
festen Commit herunterladen und mit `sudo python3 <installer-datei>` ausführen.

Der Installer:

1. Prüft den laufenden Dienst `epimediahub-provisioning.service`, dessen
   Arbeitsverzeichnis und Python-Umgebung.
2. Liest die tatsächliche Dienstumgebung, ohne Zugangsdaten auszugeben, und sichert
   die vorhandene SQLite-Datenbank über deren Backup-API.
3. Testet die Migration und das Rendern beider Portale an einer Datenbankkopie.
   Konten, Passwörter, IDs, Geräte, Zuordnungen und Playlists müssen dabei erhalten
   bleiben.
4. Stoppt kurz den Provisioning-Dienst, installiert ausschließlich die neue API,
   zwei neue Templates sowie die Registrierung und Navigationslinks in den
   bestehenden Dateien und startet den Dienst wieder.
5. Prüft lokal die bestehenden Server-Funktionen und die Lizenz-API. Bei einem
   Fehler werden die zuvor gesicherten Serverdateien wiederhergestellt. Die
   Datenbank wird nicht automatisch zurückgesetzt, damit zwischenzeitliche
   Änderungen durch die Intro-Analyse erhalten bleiben. Additive Tabellen dürfen
   nach einem fehlgeschlagenen Versuch bestehen bleiben.

Sicherung und Diagnoseprotokolle liegen im ausgegebenen, nur für root zugänglichen
Verzeichnis unter `/var/backups/credits-v120-*`. Es werden keine bestehenden
Servermodule, Worker, Zugangsdaten oder Tunnelkonfigurationen ersetzt.

Nach erfolgreicher Installation:

- Admin: `https://admin.epimediahub.com/admin/credits`
- Reseller: `https://reseller.epimediahub.com/reseller/credits`
- Öffentliche Freigabeprüfung: `https://api.epimediahub.com/v1/license/capabilities`

Die signierte Android-Version wird erst veröffentlicht, wenn die öffentliche
Freigabeprüfung 7 Testtage, 1 Credit je Aktivierung, 1000 Cent Endkundenpreis und
individuelle Resellerpreise bestätigt. Zusätzlich muss eine leere Anfrage an
`POST /v1/license/status` mit HTTP 400 beantwortet werden. Danach kann der
fehlgeschlagene Publish-Job des Android-Release-Workflows erneut gestartet werden;
der erfolgreiche signierte Build wird dabei wiederverwendet.

## Prüfungen

`tests/test_credit_pricing.py` prüft Preisberechnung, Bestellungen, atomare
Aktivierung, direkte Endkunden, vorhandene Konten und Mandantentrennung.
`tests/test_credit_installer.py` prüft Migration mit Bestandsdaten, SQLite-WAL-Backup,
Erhaltung vorhandener Templates und Dateiwiederherstellung bei einem
fehlgeschlagenen Neustart. `tests/smoke_v080.py` prüft die bestehenden Resellerabläufe.
