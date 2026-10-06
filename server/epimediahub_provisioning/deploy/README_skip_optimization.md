# Intro-Dashboard und Audioanalyse optimieren

Das Update entfernt die Fortschrittsberechnung aus Dashboard-GETs. Eine
unabhängige Aufgabe aktualisiert die geänderten Serien alle zehn Sekunden.
Filter, Suche und Seitenwechsel laden nur die authentifizierte
Fortschrittsansicht nach. SQLite filtert und begrenzt auf 20 Serien pro Seite.
Die bestehenden Markerformulare und die Suchposition bleiben erhalten.

Hetzner übernimmt weiterhin Dekodierung, Chromaprint und Vergleiche über den
bestehenden privaten Tunnel. Der Referenzvergleich berechnet alle vollständigen
Positionen mit FFT statt einer Python-Schleife. Hamming-Abstand und Schwellenwert
bleiben gleich. Der Hetzner-Prozess verwendet einen begrenzten Vergleichscache
(256 Paare, höchstens 64 MiB FFT-Daten). Ein bestätigtes Intro wird bereits vor
der Abspannanalyse und optionalen externen Metadaten veröffentlicht.

Automatische Freigaben benötigen bestätigte Anfangs- und Endgrenzen. Schwache
Einzelvorschläge, gleich starke konkurrierende Abschnitte und uneinheitliche
Zeitgrenzen umgehen den Konsens nicht mehr. Eine menschlich freigegebene
Referenz bestätigt nur den tatsächlich markierten Bereich. Wird dieser vor der
Freigabe korrigiert oder zurückgezogen, wird das abhängige Ergebnis nicht
veröffentlicht. Vorhandene menschliche Entscheidungen werden nicht geändert.

Deutsch/Italienisch → Türkisch → übrige Sprachen, neue Referenzen und gestartete
Serien innerhalb der Sprachstufe, Wiedergabeschutz, serieller Audioabruf und das
bestehende Tageslimit bleiben erhalten. Es werden keine 60 Providerabrufe parallel
gestartet. Ein Update setzt das verbrauchte Tagesbudget nicht zurück.

## Gemeinsame Installation

Voraussetzung ist die bereits aktivierte private Hetzner-Verbindung und das
Prioritätsupdate. `COMMIT` muss der vollständige veröffentlichte Commit sein.
Beide Geräte müssen dieselbe Version erhalten; die bestehende strenge Prüfung
der Komponenten bleibt aktiv. Die drei Schritte in dieser Reihenfolge ausführen.

1. Auf dem Raspberry vorbereiten:

```bash
COMMIT=82c6588b006b63b30581d102247570f16700592e
curl -fsSL "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$COMMIT/server/epimediahub_provisioning/deploy/install_skip_optimization.sh" -o /tmp/epimediahub-optimization.sh
sudo bash /tmp/epimediahub-optimization.sh prepare "$COMMIT"
```

2. Auf Hetzner die Berechnung aktualisieren:

```bash
COMMIT=82c6588b006b63b30581d102247570f16700592e
curl -fsSL "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$COMMIT/server/epimediahub_provisioning/deploy/install_skip_optimization.sh" -o /tmp/epimediahub-optimization.sh
sudo bash /tmp/epimediahub-optimization.sh compute "$COMMIT"
```

3. Auf dem Raspberry aktivieren, mit demselben `COMMIT` aus Schritt 1:

```bash
sudo bash /tmp/epimediahub-optimization.sh control "$COMMIT"
```

Die Vorbereitung pausiert nur die Audioanalyse; das Dashboard bleibt verfügbar.
Schritt 3 prüft zuerst den privaten Peer und einen echten Berechnungsaufruf.
Danach erstellt er Code- und SQLite-Sicherungen, installiert das Dashboard und
misst dessen lokale Antwortzeiten. Eine vorher aktive Audioanalyse wird wieder
gestartet; eine vorher pausierte bleibt pausiert. Schlüssel, Providerpfad,
Sprachprioritäten und Dienst-Ressourcenlimits werden nicht neu eingerichtet.
Bei einem Fehler werden ersetzter Code und Einheiten zurückgenommen. Die aktive
Kundendatenbank wird nicht durch die Sicherung überschrieben. Schlägt Schritt 3
fehl, bleibt die Audioanalyse bis zur passenden Version auf beiden Geräten
pausiert; die vorbereiteten Dateien bleiben für einen erneuten Versuch erhalten.

## Messung und möglicher Dashboard-Umzug

Die lokale Vergleichsmessung mit synthetischen Daten ergab:

| Vorgang | Vorher | Nachher |
| --- | ---: | ---: |
| Übersicht bei belegter Schreibsperre und geänderten Seriendaten | Abbruch nach 10,015 s | 6,985 ms, 20 Zeilen |
| Suche in 20.001 gecachten Serien | 119,845 ms | 19,040 ms |
| Referenzvergleich mit 5.800 Fingerprints, Median aus fünf Aufrufen | 187,948 ms | 6,007 ms |

Diese Werte stammen aus der Entwicklungsumgebung, nicht vom Raspberry oder
Hetzner. Beim Referenzvergleich waren die Module bereits geladen; ein erster
Aufruf einschließlich der Importe dauerte 73,441 ms. Sie belegen die entfernte
Schreibsperre und die schnelleren Teiloperationen,
keinen Faktor für die gesamte Analysezeit. Providerabruf und Dekodierung können
weiterhin den größten Anteil ausmachen. Die neue Phasenmessung protokolliert
`probe`, `fingerprint_intro`, `comparison_intro`, Abspann und optionale Metadaten
ohne Provideradressen oder Zugangsdaten:

```bash
sudo journalctl -u epimediahub-skip-analysis.service --since '30 min ago' --no-pager
sudo /opt/epimediahub/provisioning/.venv/bin/python /opt/epimediahub/provisioning/deploy/check_skip_latency.py /var/lib/epimediahub/provisioning/provisioning.db
```

Bei einem abweichenden Datenverzeichnis den Pfad aus `provisioning.env` verwenden.
Die zweite Prüfung öffnet die Datenbank ausschließlich lesend und startet keinen
HTTP-Server. Sie zeigt erste und warme Seitenaufrufe, Filter und Suche. Netzwerk,
Cloudflare und Internetleitung sind nicht enthalten. HTTP-Antworten enthalten
zusätzlich `Server-Timing` für Datenbank und Rendering.

Ein eigenständiges Intro-Dashboard auf Hetzner bleibt eine Option. Mit
`GET /admin/skip/progress` gibt es bereits eine authentifizierte, begrenzte
Ansicht ohne Providerzugangsdaten. Für einen vollständigen Umzug brauchen auch
Markeränderungen und Jobsteuerung eine eigene API sowie Admin-Anmeldung und
Domain-Routing. Dieses Update verlegt weder das Dashboard noch die Kundendatenbank.
SQLite darf nicht als gemeinsam geöffnete Datei über das Netzwerk eingebunden
werden. Ob ein Umzug zusätzliche Geschwindigkeit bringt, entscheidet die Messung
auf dem tatsächlichen Gerät nach diesem Update.

## Orientierung an großen Streamingdiensten

Netflix beschreibt in [US10560506B2](https://patents.google.com/patent/US10560506B2/en)
die Vorverarbeitung und den Vergleich wiederkehrender Bildsequenzen über mehrere
Folgen sowie die Bereitstellung von Zeitbereichen an den Player. Das ist ein
öffentlich beschriebenes Verfahren und kein Beleg für die vollständige heutige
Produktionspipeline. Die hier umgesetzte Audioanalyse folgt passenden Prinzipien:
vorab analysieren, wiederkehrende Abschnitte bestätigen, Ergebnisse und
Zwischenberechnungen wiederverwenden und korrigierbare Marker an den Player senden.
Visuelle Fingerprints und eine eigene Rückblickerkennung sind in diesem Update
nicht enthalten. [Chromaprint](https://github.com/acoustid/chromaprint) bleibt die
Audio-Fingerprint-Grundlage.
