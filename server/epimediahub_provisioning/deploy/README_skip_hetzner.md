# Intro-/Outro-Analyse auf Hetzner

Ziel: Der Raspberry behält Datenbank, Dashboard, Auftragssteuerung, Provider-Wiedergabesperre und Veröffentlichung der Marker. Hetzner berechnet Laufzeit/Kapitel, Audio-Fingerprints, Referenzabgleiche, Grenzprüfungen und V3.1-Staffelvergleiche. Es wird keine Kundendatenbank kopiert und keine SQLite-Datei über ein Netzwerk-Dateisystem geöffnet.

## Installation in vier Schritten

1. Auf dem neuen Hetzner-Server `install_skip_hetzner.sh <öffentliche IPv4>` als root ausführen. Der Installer gibt den vollständigen Raspberry-Vorbereitungsbefehl mit dem öffentlichen WireGuard-Serverschlüssel aus.
2. Den ausgegebenen Befehl auf dem bestehenden Raspberry ausführen. Er erzeugt den privaten Client-Schlüssel ausschließlich dort, bereitet aktualisierten Analysecode vor und zeigt den öffentlichen Client-Schlüssel mit dem Hetzner-Freigabebefehl an. Die lokale Analyse bleibt aktiv.
3. Den ausgegebenen Freigabebefehl auf Hetzner ausführen. Bei einer Hetzner Cloud Firewall müssen eingehend SSH/TCP 22 und WireGuard/UDP 51820 erlaubt sein. TCP 8790 wird nicht öffentlich freigegeben.
4. Auf dem Raspberry `sudo /usr/local/sbin/epimediahub-activate-remote-analysis` ausführen. Erst nach Codeprüfung, echtem RPC, Ende des laufenden lokalen Auftrags und einer echten Anbieterprobe inklusive 20 Sekunden Audio werden die neuen Dateien und die Remote-Umgebung aktiviert.

Die Installer werden für eine Veröffentlichung auf einen unveränderlichen Git-Commit festgelegt. Private Schlüssel oder Provider-Zugangsdaten müssen nicht in den Chat kopiert werden. Es werden nur öffentliche WireGuard-Schlüssel angezeigt.

## Betrieb

Der zusätzliche Tunnel heißt `wg-epi-analysis`; er routet ausschließlich `10.87.26.1/32` zum Hetzner-Worker. Die Internetverbindung des Raspberry und die App-Verbindungen bleiben auf ihrem bisherigen Weg. Hetzners API hört ausschließlich auf der Tunneladresse `10.87.26.1:8790` und akzeptiert Berechnungsaufträge ausschließlich vom freigegebenen Peer `10.87.26.2`.

Der Raspberry-Timer bleibt als leichte Steuerung bestehen. Beim Start einer Wiedergabe bricht er die Remote-Anfrage ab. Hetzner erlaubt nur eine laufende Operation; abgebrochene Operationen behalten ihren Platz bis zum tatsächlichen Ende. Bei einem ausgefallenen Raspberry oder einer unterbrochenen Verbindung läuft die kurze Ausführungsberechtigung nach zwölf Sekunden aus. Danach wird der Decoder gestoppt. Es gibt keinen automatischen lokalen Decoder-Fallback und keine zweite parallele Provider-Analyse.

Die aktivierte Rolle wird zusätzlich in einer nicht geheimen, root-verwalteten Datei im Raspberry-App-Verzeichnis gespeichert. Dadurch verwenden auch manuelle Worker-Aufrufe die ausgelagerte Berechnung; eine fehlende oder beschädigte Dienstumgebung aktiviert nicht versehentlich wieder den lokalen Decoder.

Katalogabfragen und Online-Metadaten werden auf dem Raspberry über den vorhandenen validierten, DNS-gebundenen Anbietertransport gelesen. Die lokale Ausführung gilt nur während der begrenzten JSON-Abfrage; nach Erfolg oder Fehler bleibt die Audio-Auslagerung aktiv. Vor einer Umstellung prüft der Installer zusätzlich den echten Anbieterkatalog mit der vorbereiteten Remote-Rolle, bevor er eine Folge auf Hetzner dekodiert. Die automatisierten Regressionen prüfen echte Katalog-HTTP-Aufrufe und anschließende Hintergrundaufträge mit direktem Audioabruf, privatem Medienabruf und dauerhaft gespeicherter Remote-Rolle, einschließlich Python 3.13.

Nicht erreichbarer Worker, belegter Worker, Versionsabweichung und Transportabbruch stellen den Auftrag zurück, ohne Versuchszähler oder Tagesbudget zu verbrauchen. Dateien mit tatsächlich unlesbarem Audio behalten die bisherigen Fehler- und Freigaberegeln. Deutsch/Italienisch, menschliche Entscheidungen, konservative automatische Freigaben und das bestehende Tagesbudget bleiben erhalten. Das Tagesbudget kann nach Messung des realen Durchsatzes im Dashboard angepasst werden.

Auf Hetzner läuft die Berechnung als unprivilegierter Benutzer `epimediahub-worker`, mit bis zu 350 % CPU und 3 GB RAM. Temporäre PCM-Daten liegen nur in temporären Dateien während eines Auftrags. Provider-Adressen und Passwörter werden nicht protokolliert oder dauerhaft gespeichert; sie werden verschlüsselt über WireGuard übertragen und nur für den jeweiligen Auftrag verwendet.

## Anbieter nur vom Raspberry erreichbar

Wenn dieselben Folgen auf dem Raspberry funktionieren, der Anbieterzugriff von Hetzner aber scheitert, kann der Raspberry ausschließlich die komprimierten Mediendaten durch den bestehenden Tunnel weiterreichen. Laufzeitprüfung, Audiodekodierung, Chromaprint und Staffelvergleiche bleiben auf Hetzner. In diesem Modus bleiben Anbieter-Adressen und Zugangsdaten auf dem Raspberry; Hetzner erhält nur eine kurzlebige private Abrufadresse.

Bei einer bereits eingerichteten Verbindung zuerst den aktuellen, auf einen Commit festgelegten `install_skip_hetzner.sh` erneut auf Hetzner mit dessen öffentlicher IPv4 ausführen. Danach den dazugehörigen `install_skip_remote_client.sh --refresh-code` auf dem Raspberry ausführen. Das aktualisiert den vorbereiteten Code, ohne die vorhandenen Schlüssel, Peer-Freigaben oder Tunnelkonfigurationen zu ersetzen. Anschließend auf dem Raspberry aktivieren:

```sh
sudo /usr/local/sbin/epimediahub-activate-remote-analysis --provider-via-raspberry
```

Der Abrufdienst hört nur während eines Auftrags auf `10.87.26.2:8791`, akzeptiert ausschließlich den Hetzner-Peer `10.87.26.1` mit einem zufälligen Token und öffnet höchstens eine Anbieter-Verbindung zugleich. Sprünge in der Mediendatei werden als HTTP-Range-Anfragen weitergereicht. Eine vorhandene UFW erhält nur die passende Regel auf `wg-epi-analysis`; UFW wird auf dem Raspberry nicht aktiviert. In einer anderen lokal konfigurierten Firewall muss derselbe private Peerzugriff erlaubt sein. Die Aktivierung prüft vor der Umstellung eine echte Folge samt 20 Sekunden Audio auf Hetzner über diesen Abrufpfad und speichert ihn auch für manuelle Worker-Aufrufe.

`--provider-direct` schaltet nach derselben erfolgreichen Prüfung wieder auf den direkten Anbieterzugriff von Hetzner um. Ohne Option behält eine erneute Aktivierung den bestehenden Anbieterpfad bei.

## Prüfen

- Hetzner: `systemctl status epimediahub-analysis-worker.service` und `wg show wg-epi-analysis`.
- Raspberry: `wg show wg-epi-analysis` und `journalctl -u epimediahub-skip-analysis.service -n 40 --no-pager`.
- Die erfolgreiche Aktivierung bestätigt die Anbieterprüfung und zeigt den Sicherungsordner an. Sichtbarer Katalogfortschritt hängt weiterhin von Providerzugriff, Wiedergabesituation und Tagesbudget ab.

Wenn der private Berechnungsaufruf funktioniert, aber die Anbieterprüfung scheitert, lässt sich auf dem Raspberry `deploy/diagnose_skip_remote_provider.py` mit dessen Provisioning-Virtualenv und sudo ausführen. Der Diagnosebefehl wartet auf den bestehenden Worker, hält dessen Dateisperre und vergleicht höchstens zwei aktivierte Folgen nacheinander auf Hetzner und Raspberry. Er zeigt getrennt Laufzeit-/Audiofehler und die benötigte Zeit an. Für jede Folge werden auf jedem Gerät maximal 20 Sekunden Audio geprüft; der Vergleich hat ein Zeitbudget von drei Minuten ab dem Ende des vorherigen lokalen Auftrags. Wiedergabe-Heartbeats bleiben wirksam. Der Analyse-Timer wird anschließend in seinen vorherigen Zustand versetzt; Zugangsdaten, URLs und Fingerprint-Werte werden nicht ausgegeben.

Für eine fehlgeschlagene Aktivierung mit privatem Anbieterabruf die Diagnose mit `--provider-via-raspberry` starten. Sie verwendet den vorbereiteten, versionsgeprüften Code und prüft zuerst eine kurze Test-Audiodatei über den Rückweg `Hetzner → Raspberry`. Dafür wird kein Anbieter kontaktiert und kein Decoder auf dem Raspberry gestartet. Falls dabei keine Hetzner-Anfrage am privaten Abrufport ankommt, endet die Diagnose vor dem echten Anbieterzugriff. Bei erfolgreichem Test zeigt der anschließende Folgenvergleich zusätzlich Anfragen, Range-Anfragen, erfolgreich übertragene Medienbytes und HTTP-Statuscodes des privaten Abrufs. Die Gesamtausgabe trennt damit Laufzeitprüfung, Audiodekodierung und den tatsächlichen Datenabruf, ohne die App-Konfiguration umzuschalten.

Bei fehlgeschlagener Aktivierung werden vorheriger Code, Timer und Remote-Drop-in wiederhergestellt; die aktuelle Datenbank wird nicht durch eine Sicherung überschrieben. Eine zusätzliche SQLite-Sicherung wird vor erfolgreicher Umstellung angelegt. Das Dashboard und die Lizenz-/Credit-Dienste werden vom Installer nicht ersetzt oder neu konfiguriert.
