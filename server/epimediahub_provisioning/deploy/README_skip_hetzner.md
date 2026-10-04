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

Nicht erreichbarer Worker, belegter Worker, Versionsabweichung und Transportabbruch stellen den Auftrag zurück, ohne Versuchszähler oder Tagesbudget zu verbrauchen. Dateien mit tatsächlich unlesbarem Audio behalten die bisherigen Fehler- und Freigaberegeln. Deutsch/Italienisch, menschliche Entscheidungen, konservative automatische Freigaben und das bestehende Tagesbudget bleiben erhalten. Das Tagesbudget kann nach Messung des realen Durchsatzes im Dashboard angepasst werden.

Auf Hetzner läuft die Berechnung als unprivilegierter Benutzer `epimediahub-worker`, mit bis zu 350 % CPU und 3 GB RAM. Temporäre PCM-Daten liegen nur in temporären Dateien während eines Auftrags. Provider-Adressen und Passwörter werden nicht protokolliert oder dauerhaft gespeichert; sie werden verschlüsselt über WireGuard übertragen und nur für den jeweiligen Auftrag verwendet.

## Prüfen

- Hetzner: `systemctl status epimediahub-analysis-worker.service` und `wg show wg-epi-analysis`.
- Raspberry: `wg show wg-epi-analysis` und `journalctl -u epimediahub-skip-analysis.service -n 40 --no-pager`.
- Die erfolgreiche Aktivierung bestätigt die Anbieterprüfung und zeigt den Sicherungsordner an. Sichtbarer Katalogfortschritt hängt weiterhin von Providerzugriff, Wiedergabesituation und Tagesbudget ab.

Bei fehlgeschlagener Aktivierung werden vorheriger Code, Timer und Remote-Drop-in wiederhergestellt; die aktuelle Datenbank wird nicht durch eine Sicherung überschrieben. Eine zusätzliche SQLite-Sicherung wird vor erfolgreicher Umstellung angelegt. Das Dashboard und die Lizenz-/Credit-Dienste werden vom Installer nicht ersetzt oder neu konfiguriert.
