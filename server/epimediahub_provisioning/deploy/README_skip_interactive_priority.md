# Sprachfolge und interaktive Intropriorität

Die Auftragssteuerung bleibt auf dem Raspberry; die vorhandene Hetzner-Instanz berechnet weiterhin Audio-Fingerprints und Vergleiche. Dieses Update verändert ausschließlich die Raspberry-Steuerung und die Anzeige der Reihenfolge. Die versionsgeprüften Berechnungskomponenten und die WireGuard-Konfiguration werden nicht ersetzt.

Die Sprachfolge gilt über alle aktivierten Kunden und Playlists: zuerst Deutsch und Italienisch, danach Türkisch, zuletzt übrige oder unbekannte Audiosprachen. Ein alter Serienfokus darf diese Folge nicht umgehen. Bekannte, noch nicht inventarisierte Serien werden bei der Sprachstufe berücksichtigt. Nicht erreichbare oder ausgeschaltete Quellen blockieren die Folge nicht dauerhaft. Belegte Anbieterzugänge bleiben geschützt; solange bevorzugte Dateien dort warten, beginnt keine nachrangige Sprachgruppe.

Ein authentifizierter Episoden-Lookup setzt die zugehörige Serie vor normale Hintergrundaufträge. Dabei werden zuerst die aktuelle Staffel/Folge und die folgenden Episoden geprüft, anschließend die übrigen bereits bekannten Folgen. Ein neuer oder korrigierter, freigegebener Intro-Marker setzt zuerst einen kurzen Lernauftrag für genau seine Referenzdatei. Laufzeit und Vollständigkeit des markierten Audioausschnitts werden geprüft; die vorhandenen Freigabekriterien bleiben bestehen. Danach erhalten die passenden Folgen Vorrang. Weitere neue Referenzen können auch eine bereits priorisierte Serie unterbrechen, um zuerst deren Referenzausschnitt zu lernen.

Der Worker bleibt seriell: höchstens eine Anbieteranalyse und eine Remote-Operation laufen gleichzeitig. Neue vorrangige Anfragen pausieren einen Hintergrundauftrag an der nächsten Abbruchprüfung; bereits gespeicherte Audiofenster, Marker und Versuche bleiben erhalten. Der private Client beendet dazu die Remote-Operation. Vergleiche aus App-Fingerprints brauchen keinen weiteren Anbieterstream und können während einer Wiedergabe erfolgen, sofern die Sprachstufe erlaubt ist. Die maximale Parallelität wird ohne Durchsatzmessung nicht erhöht.

Das konfigurierte Tageslimit bleibt bestehen. Audiojobs können deshalb trotz neuer Priorität am ausgeschöpften Tagesbudget warten. Durchsatz und konkrete Antwortzeiten müssen nach Aktivierung auf den vorhandenen Geräten gemessen werden; die Änderung ist kein Nachweis einer bestimmten Geschwindigkeit.

## Aktivieren auf dem Raspberry

`deploy/install_skip_interactive_priority.sh` mit dem unveränderlichen 40-stelligen Commit dieser Änderung herunterladen und mit derselben Commit-ID als Argument per sudo ausführen. Der Installer prüft alle Downloads vor der Umstellung, pausiert die Auftragssteuerung und wartet höchstens 30 Sekunden auf den Ablauf der alten privaten Remote-Operation. Er erstellt Code- und SQLite-Sicherungen, erweitert die Sprachstufen und setzt abgebrochene laufende Jobs ohne zusätzlichen Versuch zurück in die Warteschlange.

Anschließend startet er das Dashboard neu und prüft das Gesundheitsmerkmal `skip_interactive_priority`. Bei einem Fehler wird der vorige Code wiederhergestellt; die aktive Kundendatenbank wird dabei nicht durch eine ältere Sicherung überschrieben. Ein vorher aktiver Analyse-Timer wird wieder gestartet, ein vorher deaktivierter bleibt deaktiviert. Auf Hetzner ist für dieses Update kein neuer Worker erforderlich.

Im Dashboard unter „Aktuelle Analyse & Reihenfolge“ steht die aktive Sprachgruppe. Das Worker-Journal zeigt wie bisher Status und `elapsed_seconds`. Die Playlist-Reihenfolge bleibt ein Auswahlkriterium innerhalb der Sprachgruppe; direkte Wiedergabe- und Referenzanfragen haben Vorrang.
