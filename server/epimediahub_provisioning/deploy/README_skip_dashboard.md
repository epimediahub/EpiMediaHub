# Vollständigen Intro-Seitenaufruf beschleunigen

Die Raspberry-Messung vom 6. Oktober 2026 zeigte nach dem ersten Update:

| Ansicht | Lokale Gesamtzeit | Datenbankzeit |
| --- | ---: | ---: |
| Erster Seitenaufruf | 35.893 ms | 35.323 ms |
| Weiterer Seitenaufruf | 31.146 ms | 31.118 ms |
| Fortschrittsfilter | 123 ms | 120 ms |
| Fortschrittssuche | 211 ms | 208 ms |

Das erste Update beschleunigte die Fortschrittsansicht. Der komplette
Seitenaufruf führte noch Katalogzählungen über alle Folgen und die Planung des
nächsten Analyseauftrags aus. Diese Arbeiten liefen zusätzlich zu den inzwischen
schnellen Fortschrittsabfragen.

Dieses Folgeupdate legt Katalogzählungen und die Planungsübersicht in eine
persistente SQLite-Snapshot-Tabelle. Der bestehende Fortschrittsdienst
aktualisiert sie im Hintergrund mit mindestens 30 Sekunden Abstand. HTTP-GETs
berechnen diese Aggregate nicht erneut, auch wenn noch kein Snapshot vorliegt.
Dann wird die Statistik als noch ausstehend angezeigt. Ein tatsächlich laufender
Auftrag, Playlist-Namen, Einstellungen und Playlist-Reihenfolge werden weiterhin
direkt gelesen. Zeitmarken und deren Bearbeitung bleiben direkt und unverändert.

Zusätzliche Indizes decken Markerübersichten, Jobzustände, Katalogmitgliedschaft,
Sprachränge und die letzten Online-Ergebnisse ab. Die Ermittlung der Sprachstufe
kann beim ersten vorhandenen passenden Auftrag enden. Die Hintergrundübersicht
sortiert die restliche Warteschlange nicht neu, wenn ein Auftrag bereits läuft.
Die Reihenfolge Deutsch/Italienisch → Türkisch → Rest bleibt dieselbe.

Der lokale Test mit 100.000 registrierten Folgen und 20.000 gecachten Serien
ergab rund 13 ms Datenbankzeit für den vollständigen Seitenaufruf und rund 15 ms
für einen weiteren vollständigen Aufruf einschließlich Rendering. Diese Werte
stammen aus der Entwicklungsumgebung. Das Update misst die tatsächlichen Zeiten
auf dem Raspberry nach der Installation erneut. Die Messung weist nun Marker,
Quellen, letzte Jobs, Online-Ergebnisse, Katalog, Fortschritt und Planung getrennt
aus. Internet- und Cloudflare-Laufzeiten sind weiterhin nicht enthalten.

## Installation auf dem Raspberry

Voraussetzung ist das bereits installierte gemeinsame Optimierungsupdate und der
Fortschrittsdienst. Hetzner benötigt kein weiteres Update: Die sechs geprüften
Komponenten des Berechnungsprotokolls werden nicht verändert.

```bash
COMMIT=bb45877a86b81359c440ef4275646b7001612a45
curl -fsSL "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$COMMIT/server/epimediahub_provisioning/deploy/install_skip_dashboard.sh" -o /tmp/epimediahub-dashboard.sh && sudo bash /tmp/epimediahub-dashboard.sh "$COMMIT"
```

Der Installer lädt und prüft alle Dateien vor dem Dienstwechsel, pausiert die
beiden Hintergrundaufgaben, wartet auf das Ende des Remote-Auftrags und erstellt
Code- und Datenbanksicherungen. Er erstellt die Indizes und den ersten Snapshot
einmalig vor der Messung. Während dieser Vorbereitung können die Datenbankarbeiten
je nach Größe länger dauern. Danach laufen sie außerhalb der Seitenaufrufe.

Die vorhandenen CPU- und Speicherlimits des Fortschrittsdienstes bleiben
erhalten; nur seine Laufzeitgrenze wird auf 120 Sekunden erweitert, damit eine
größere Statistikberechnung abgeschlossen werden kann. Vormals aktive Timer
werden wieder gestartet, vormals pausierte bleiben pausiert. Das verbrauchte
Tagesbudget, Referenzmarken, Providerpfad und WireGuard-Schlüssel bleiben erhalten.
Bei einem Fehler werden vorheriger Code und die Dienstdatei zurückgenommen.
Die aktive Datenbank wird nicht durch eine Sicherung ersetzt.

Ein Dashboard-Umzug zu Hetzner bleibt eine Option. Die nächste Raspberry-Messung
zeigt, ob nach dem Entfernen dieser Arbeiten aus dem Seitenaufruf noch ein
wesentlicher Restengpass besteht.
