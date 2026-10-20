# EpiMediaHub — täglicher Xtream-Ablaufimport (HTTP, vorläufig)

Stand: 2026-10-20. Dieser Zweig ist **nicht** produktiv installiert oder als finale Android-APK freigegeben.

## Genehmigung und Sicherheitsgrenzen

Der Administrator hat ausdrücklich die tägliche HTTP-Abfrage vorhandener Xtream-Konten erlaubt. Achtung: `player_api.php` erhält dabei Benutzernamen und Passwörter in einer unverschlüsselten GET-Anfrage. Dies schützt weder die Zugangsdaten vor Mitlesen noch die Antwort vor Manipulation. Eine autorisierte HTTPS-Schnittstelle bleibt vorzuziehen.

Der neue `expiry_http_worker.py` läuft einmal täglich. Er nutzt die bestehende, schreibgeschützte Zuordnung `customer_playlists.id` → Anbieterzugang, nimmt höchstens eine Anfrage pro aktives Konto und führt keine automatische Verlängerung, Löschung, Buchung oder Änderung an IPTV-Konten durch. Er speichert ausschließlich Datum/status/UTC-Zeit/ID/HMAC in einer separaten `0600`-SQLite-Datei und ein zufällig generiertes `0600`-HMAC-Schlüsselmaterial. HTTPS-verifizierter Cache und die automatischen monatlichen **autoritativen** PDF/FCM bleiben unverändert und gesperrt, solange nicht vollständige, tatsächlich authentifizierte Daten vorliegen.

- `http_observed`: Ein plausibles Datum wurde über HTTP empfangen, **nicht authentifiziert**; im Dashboard und PDF explizit so gekennzeichnet.
- `unverified`: Kein aktuelles Datum, Provider meldet kein Datum, Zeitüberschreitung, 4xx oder andere Fehler. Nie stillschweigend als gültiges oder abgelaufenes Konto behandeln.
- Alte HTTP-Snapshots werden bei jedem Lauf **atomar vollständig ersetzt**, sodass ein fehlgeschlagener Folgelauf kein altes, scheinbar aktuelles Datum zurücklässt.
- Beim Ändern der Serveradresse oder Xtream-Zugangsdaten einer Kundenplaylist erkennt der private HMAC-Vergleich die alte Zuordnung und zeigt bis zum nächsten Import *unbekannt*.
- Nach 48 Stunden ohne erfolgreichen Lauf sind die HTTP-Angaben veraltet und werden nicht mehr als aktuelle Daten angezeigt.

## Anzeige und Ausdruck

Im nativen Admin V2 gibt es eine Kontenabdeckungsanzeige mit Anzahl authentifiziert verifizierter, per HTTP beobachteter und unbekannter Abläufe. Die **manuelle** Monatsarbeitsliste `month.preview.pdf` zeigt die jeweiligen Playlists getrennt: verifizierte Monatsdaten, vorläufige HTTP-Daten im Monatsbereich und alle Konten mit unbekanntem Ablaufdatum auf separaten Seiten, inklusive Platz für Kontakt, Termin und Notizen. Das PDF ist ausdrücklich `UNVOLLSTÄNDIG`. Die ursprünglichen Berichte `month.pdf`, `month`, `week` bleiben gegen die Vollständigkeitsprüfung abgesichert.

Die Testausgabe der letzten Live-Prüfung war 6 aktive Xtream-Verbindungen: 3 Datum erkannt, 1 ohne Datum, 1 HTTP-4xx, 1 Timeout. Diese Probe hat keine Daten gespeichert. Die Live-Daten werden erst nach freigegebener Serverinstallation beim nächsten täglichen Lauf erfasst.

## Geplante systemd-Ausführung

`install_daily_xtream_http.py` legt mit separater, expliziter Deployment-Freigabe eine systemd-oneshot-Serviceeinheit und einen Timer für **täglich 06:15 Uhr Europe/Berlin** an, unter der vorhandenen nichtprivilegierten Dashboard-Serviceidentität. Die Einheit schreibt nur in `/var/lib/epimediahub/admin-mobile`, führt keine Root-Pollingprozesse aus und begrenzt die maximale Laufzeit auf 180 Sekunden.

Die neue Installation ist ausschließlich nach erfolgreichem `upgrade_native_management_backend.py --check`/bewusstem Backend-Upgrade, gesonderter Timer-Preflight-Prüfung und realer Authentifizierungs-/Schreibzugriffsprüfung erlaubt. Für einen bereits laufenden Dienst darf kein Besitzer oder Dateimodus ungeprüft verändert werden. Im Fehlerfall ist der Timer deaktivierbar mit `systemctl disable --now epimediahub-xtream-expiry.timer`; die Player-App bleibt davon unberührt.

Für die **geschützte Produktionsfreigabe** außerdem erforderlich: FCM-Serveridentität, Original-Handler-Verträge/CSRF, tatsächliche Hetzner-Integration, kontinuierlicher Release-Signaturschlüssel, reale Android-Geräteprüfung, ein einziges signiertes Admin-V2-Release über den privaten In-App-Updater. Weder Backend-CI noch Android-Build allein erfüllen alle diese Gates.
