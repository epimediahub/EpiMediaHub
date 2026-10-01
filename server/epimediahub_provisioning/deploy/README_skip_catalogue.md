# Gesamtkatalog und nächtliche Ergänzung für Raspberry 0.8.2

Der vorhandene Worker erfasst den vollständigen Serienbestand der aktivierten
XTREAM-Playlists, auch ohne vorheriges Abspielen. Neue oder vom Anbieter als
geändert gemeldete Folgen werden in die bestehende Audioanalyse eingeplant.
Unveränderte, bereits bearbeitete Dateien werden beim Katalogabgleich nicht
erneut eingeplant. Ein Katalogfund allein gibt keine Zeitmarke frei.

## Installation

Voraussetzung ist der laufende Raspberry-Server 0.8.2 mit Audioanalyse und
Staffelautomatik für die gewünschten Playlists. Android 1.0.16 bleibt kompatibel.

```sh
curl -fsSL https://raw.githubusercontent.com/epimediahub/EpiMediaHub/23c72bf90607a4d3dec9bca6badb2723d1e9d2d6/server/epimediahub_provisioning/deploy/install_skip_catalogue.sh -o /var/tmp/epimediahub-skip-catalogue.sh &&
sudo bash /var/tmp/epimediahub-skip-catalogue.sh --start-catalogue
```

Der Schalter startet ausschließlich bereits aktivierte Automatik-Playlists
mit erlaubter Audioanalyse und aktivem Kunden. Ohne Schalter werden die Dateien
installiert, ohne die Katalogprüfung neu einzuschalten. TMDB-Schlüssel,
Anbieterkonfiguration, Geräte und menschliche Zeitmarken bleiben erhalten.

Das Skript lädt zwölf Dateien aus einem festen Commit und prüft SHA256,
Syntax sowie die tatsächlichen Richtlinien-, API- und Audiotests vor Änderungen.
Es verwendet den bestehenden Worker-Lock, sichert Code und SQLite-Datenbank
und stellt bei einem fehlgeschlagenen Neustart den vorherigen Code sowie nur
die selbst geänderten Katalogeinstellungen wieder her.

## Ablauf

- Der erste Lauf nimmt alle eindeutig strukturierten Serien, Staffeln und
  Folgen auf. Der Cursor und bereits erledigte Jobs bleiben bei Neustarts erhalten.
- Danach wird ein neuer Katalogabgleich täglich ab 03:00 Uhr Europe/Berlin
  geplant. Sommer-/Winterzeit wird berücksichtigt. Der vorhandene systemd-Timer
  prüft den Termin; nach Ausfall/Neustart wird ein fälliger Lauf nachgeholt.
- Die Änderungssignatur enthält Serien-ID, Titel/Jahr und Anbieteränderungszeit.
  Neue/geänderte Serien werden über get_series_info nach neuen Dateien durchsucht.
  Ohne Anbieterzeitstempel erfolgt der Folgenlistenvergleich jede Nacht.
  Unveränderte Zeitstempel erhalten zusätzlich eine wöchentliche Kontrolle.
- Bei Anbietern mit unzuverlässigen, unveränderten Zeitstempeln kann eine neue
  Folge erst durch diese zusätzliche Kontrolle gefunden werden.
- Ein nächtlicher Lauf setzt einen noch laufenden Katalogdurchlauf nicht zurück.
  Ein großer oder langsamer Katalog wird in weiteren Worker-Aufrufen fortgesetzt.
- Es werden höchstens acht Metadatenschritte pro Aufruf ausgeführt; nach
  30 Sekunden beginnt kein weiterer Schritt. Jeder Abruf hat eigene Transport-
  und Größenlimits. Pro Katalog sind 20.000 Serien, pro Serie 10.000 Folgen
  und pro Staffel 200 Folgen zulässig.
- Alle Abrufe bleiben seriell und pausieren bei gemeldeter Wiedergabe desselben
  Anbieterkontos. Öffentliche Ziele, Weiterleitungen, Laufzeiten und
  Dateizuordnung werden wie bisher geprüft.
- Neu eingeplante Folgen aus Nachtläufen haben Vorrang vor dem alten Bestand.
  Der Gesamtdurchlauf nutzt standardmäßig höchstens 96 Audioprüfungen pro UTC-Tag;
  das Dashboard erlaubt ein globales Limit von 1 bis 500. Bestehende Installationen
  ohne eingeschalteten Gesamtkatalog behalten 24 Prüfungen pro Tag.
- Die Bestandsaufnahme läuft auch nach Ausschöpfen des Audiolimits weiter.
  Ein großer Bestand kann mehrere Tage oder länger benötigen.
- Geänderte Dateien erhalten eine neue Prüfung; eine neue Laufzeit wird nur
  für weiterhin durch den Katalog belegte, noch nicht vom Player registrierte
  Dateien übernommen. Player-Laufzeiten und menschliche Entscheidungen bleiben
  geschützt.

## Dashboard

Unter /admin/skip steht „Gesamtkatalog & Nachtprüfung“. Dort lassen sich alle
aktivierten Automatik-Playlists einplanen und das globale Tageslimit einstellen.
Pro Playlist werden Katalogfortschritt, erfasste/offene/bearbeitete Folgen,
Abfrageprobleme und der nächste Nachtlauf angezeigt. Die Bestandsaufnahme und
die eigentliche Audioanalyse haben getrennte Fortschrittszahlen.

„Weitere Katalogprüfungen ausschalten“ stoppt neue Katalogabrufe. Bereits
eingeplante Folgen bleiben in der Analysewarteschlange; „Analyse ausschalten“
stoppt die Verarbeitung der betreffenden Playlist.

Vorschläge und Freigaben bleiben in den bestehenden Ansichten. Die bisherigen
Kriterien für unabhängige Belege, exakte Datei/Laufzeit, menschliche Korrekturen
und Ablehnungen gelten unverändert. Online-Daten und wiederkehrender Ton ohne
ausreichende Belege ergeben weiterhin Vorschläge zur Prüfung.

## Validierung

32 zusätzliche SQLite-/API-Tests decken ungespielte Serien, mehrere Staffeln,
nächtliche Neuzugänge, unveränderte Dateien, fehlende/stale Zeitstempel,
Neustarts, doppelte Nummerierung, unsichere Dateiformate, Wiedergabevorrang,
konkurrierendes Ausschalten, Tagesbudget und Zeitumstellung ab.

Neun isolierte Installationstests prüfen Erfolg, bestehende Marker/Schlüssel,
inaktive Timer, beschädigte Downloads, Vorprüfungsfehler, laufende Worker und
Wiederherstellung von Code, Einstellungen, Termin und Budget. Die echten
Audio- und API-Prüfungen laufen zusätzlich mit den vorhandenen Backendtests
in .github/workflows/raspberry-v082-catalogue-validate.yml.
