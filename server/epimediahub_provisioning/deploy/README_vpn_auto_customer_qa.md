# EpiMediaHub VPN Vollautomatik · Server- und Kundentest-Abnahme

**Gilt für:** Finnland WireGuard `wg0`, EpiMediaHub-VPN-Dashboard und offizielle Android-App v1.0.42 (interner QA-Build). **Kein allgemeiner Kundenausrolltermin ohne Hardwaretests.**

## Technischer Ablauf

1. Kunde registriert seine offizielle EpiMediaHub-App: die schon bestehende, dauerhaft gespeicherte `SetupCodeProvisioning.deviceId` wird im Dashboard erfasst. Die App erhält ein gerätegebundenes Sitzungstoken wie bisher.
2. Admin vergibt VPN kostenlos oder ein Reseller bucht mit vorhandenen VPN-Credits ein Zeitpaket. Noch nicht angemeldete VPN-Geräte erhalten einen `vpn_pending_grants`-Eintrag. Es werden **keine** privaten WireGuard-Schlüssel erzeugt oder in der Datenbank gespeichert.
3. Bei der nächsten VPN-Einrichtung erzeugt die App ein WireGuard-Ed25519/X25519-Schlüsselpaar über die offizielle WireGuard-Tunnel-Bibliothek. Nur der Public Key verlässt das Gerät, der private Schlüssel liegt AndroidKeyStore-verschlüsselt in `noBackupFilesDir`.
4. `POST /v1/device/vpn/enroll` verlangt das **bereits vorhandene** gültige Geräte-Bearer-Token und exakt die gespeicherte Geräte-ID. Der Server bindet den Public Key unveränderbar an die registrierte Datenbank-Gerätezeile, reserviert kollisionsfrei eine Tunneladresse, nimmt eine vorgemerkte Lizenz in Betrieb und verweigert heimlichen Schlüsselwechsel.
5. Der Finnland-Agent synchronisiert die zugewiesenen Peers, überprüft Sperrungen/Laufzeiten und bestätigt die tatsächlich angewendeten Firewall-/WireGuard-Regeln, den **öffentlichen** Server-Key und vom Dashboard unabhängige belegte IP-Bereiche.
6. Erst nach Agent-ACK und gültiger Laufzeit liefert `GET /v1/device/vpn/status` die autorisierte Server-IP, den öffentlichen Server-Key und die Tunneladresse an dieses Gerät. Die App erstellt lokal ihr WireGuard-Profil.
7. Android verlangt einmalig seine Systemzustimmung zur VPN-Verbindung. Danach reicht die im App-Menü gewählte VPN-Playlist; der VPN-Modus wird beim Wechsel geprüft. Bei Ausfall/Revocation kein automatischer ungeschützter Fallback.

## Server-Abnahme vor der ersten App-Installation

- Installiere/aktualisiere zunächst das VPN-Dashboard-Addon auf dem Server der bestehenden Kundendatenbank mit dem **geprüften, gepinnten Installer** dieser PR, danach den VPN-Agent auf dem Finnland-Server. Das Dashboard-Installerskript sichert vor der Migration bestehende Dateien und die SQLite-Datenbank und prüft an einer Kopie.
- Kontrolliere `epimediahub-provisioning.service` und `epimediahub-vpn-agent.service`; das Dashboard muss die Agent-Bestätigung melden. `wg0` darf nicht durch alte, unmanaged Peers überschrieben werden.
- Kontrolliere unter `/admin/vpn` die Geräte-ID und ob eine kostenlose Vergabe ohne manuelle Schlüssel möglich ist. `/reseller/vpn` muss nur eigene Kundengeräte und die vorhandenen, separat geführten VPN-Credits anzeigen.
- Die VPN-App-API muss auf fehlendes Bearer-Token mit **HTTP 401** und auf die falsche Geräte-ID mit **HTTP 403** reagieren. Niemals ein WireGuard-PrivateKey, ein Geräte-Session-Token oder Agent-Bearer in Logs, Tickets oder Screenshots übertragen.
- Der Admin kann kostenlos App-Lifetime über die separat geprüfte Credits-Lizenz-Erweiterung gewähren. Bei dieser Aktion dürfen weder Reseller-Credits reduziert noch Zahlungen behauptet werden.

## Testmatrix auf echtem Fire TV

| Prüfung | Erwartetes Ergebnis |
|---|---|
| Offizielle EpiMediaHub-App 1.0.42 über alte offizielle Version installieren | Bereits registrierte Geräte-ID, Kunde, Playlists und App-Lizenzen bleiben erhalten |
| App ohne VPN starten und beenden | Gewohntes Hauptmenü, klarer D-Pad-Fokus, **ein** Exit |
| App > Einstellungen | Geräte-ID dauerhaft sichtbar; VPN-Menü dort statt eigener Startseite |
| Noch nicht freigegebenes Gerät | Deutliche Lizenzmeldung, keine ungültigen Test-Schlüssel, normale App erreichbar |
| Admin gratis VPN vormerken | Beim Verbinden erstellt Gerät eigenen Schlüssel, Server weist IP zu; keine ADB-Datei |
| Reseller-Tarif auf Gerät buchen | Genau konfigurierte Anzahl VPN-Credits einmalig abgezogen |
| Erste VPN-Einwahl | Genau eine zulässige Android-Systemzustimmung; anschließend bestätigte Finnland-IP |
| App vollständig schließen/neustarten | Schlüssel/ID bleiben gleich, neue Sitzung wird korrekt überprüft |
| VPN mit Media3 und VLC testen | Streaming nur über bestätigte VPN-Route, keine DNS-/IPv4-/IPv6-Lecks |
| WLAN trennen / Server Peer sperren / Lizenz ablaufen lassen | Geschützte Wiedergabe stoppt; **kein** stiller DIRECT-Fallback |
| Playlist ohne VPN auswählen | Eindeutiger geprüfter Direktmodus, geschützter Stream zuvor beendet |
| Speedtest im Hauptmenü | Echte Download-/Upload-Daten und HTTP-Latenz statt Dummys |
| Zwei verschiedene Kunden-Geräte | Zwei verschiedene Public Keys und Tunneladressen, getrennte Lizenzen |
| Unautorisierter Gerätewechsel/Session-Diebstahl | Server lehnt unzulässige Umregistrierung und Peer-Tausch ab |
| Tester-Update zurücknehmen | Nur APK zurücknehmen; **keine** Analyse-, Kunden- oder Lizenzdaten löschen |

## Rollout

1. Zuerst Entwicklergerät Fire TV 4K Max mit echten Netztests prüfen.
2. Danach 2–5 freigegebene Testgeräte mit jeweils einzelnem Kundenkonto und Lizenzlaufzeit.
3. Gerätestatus, App-/VPN-Lizenz, Handshake, Wiedergabeabbrüche, Latenz, Ausfall und D-Pad-Fehler protokollieren. Keine Schlüssel oder Private-Keys protokollieren.
4. Erst bei erfolgreicher Abnahme den regulären In-App-Updater für die definierte Testergruppe nutzen; **niemals** automatisch alle Bestandskunden aktualisieren.

**Nicht behaupten:** Der separat signierte Android-APK-Build oder Flask-API-Tests beweisen keine fehlerfreie Fire-TV-VPN-Routing-Sicherheit. Android-Consent, Media3, VLC, echte IPv6/DNS-Routen und Netzwerkwechsel brauchen echte Endgerätetests.
