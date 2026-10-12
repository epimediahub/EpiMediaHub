# EpiScene: verlässliche Zustände, Sprachpriorität und Wiederverwendung

Der Installer ergänzt den im Bericht vom 12.10.2026 identifizierten aktiven
Serverstand. Er ersetzt keine älteren Repository-Dateien über die laufenden
Analysezugänge oder den parallelen Worker. Die produktive Installation ist erst
nach `INSTALL OK` auf dem Server bestätigt.

## Änderungen

- 4K ANALYSE / 4K IPTV bevorzugt Deutsch; THE BEST / IPTV The Best bevorzugt
  Italienisch. Die Sprachen bleiben einzeln gespeichert. Unbekannte Sprachen
  werden nicht aus dem Seriennamen geraten. Bestehende parallele Analysebahnen
  bleiben erhalten; im gemeinsamen seriellen Scheduler wechseln verfügbare
  Zugänge nach einem Job. Ein pausierter oder nicht verfügbarer Zugang wird
  dadurch nicht aktiviert.
- Eine unvollständige Bildprüfung endet als `partial`, ein technischer
  Bildfehler als `failed`, ein fehlender Vergleichspartner als `no_reference`.
  `no_match` erfordert abgeschlossene Pflichtphasen. Der Bericht trennt die
  ausdrücklich unvollständigen alten Negativabschlüsse von neuen vollständig
  geprüften Ergebnissen und von alten Abschlüssen ohne vollständige Evidenz.
- Gültige Fenster und erfolgreiche Vergleiche überleben Fortsetzungen.
  Fehlgeschlagene Vergleiche erzeugen keinen erfolgreichen Checkpoint.
  Dateirevision, Inhalt, Abtastraster und Referenzgrenzen binden den Cache.
  Bestehende gültige Fenster werden nur an eine zeitlich belegte Metadatenrevision
  gebunden. Ein neuer Auftrag beginnt nicht mit weniger als 120 Sekunden
  Restbudget. Die bestehenden Gesamt-, RPC- und Szenenlimits bleiben erhalten.
- Ein zusätzlicher unabhängiger Staffelpartner kann den bestehenden Konsens
  vervollständigen. Ein Rest von mehr als einer und höchstens fünf Sekunden
  verhindert die Freigabe nicht mehr, wenn er vollständig als schwarz und stumm
  dekodiert wurde. Bestätigte Grenzen, Qualität, Streuung und unabhängiger
  Konsens bleiben erforderlich. Ton, Logos, anschließende Szenen, Mehrdeutigkeit
  und größere Reste bleiben zur Prüfung erhalten.
- Eine bestätigte Sprachfassung kann Zeitmarken derselben Folge liefern.
  Drei weit auseinanderliegende Handlungsausschnitte außerhalb der Marker und
  beide Abschnittsgrenzen müssen dieselbe Zeitabbildung bestätigen. Ein
  wiederkehrendes Intro reicht nicht als Folgenidentität. Verschiebung und
  gleichmäßige Geschwindigkeit sind begrenzt; abweichende Schnitte fallen auf
  die eigene Analyse zurück. Herkunft, tatsächliche Fenster, Revisionen und
  Grenzen werden vor Veröffentlichung erneut geprüft. Sprachfassungen derselben
  Folge liefern keine zusätzlichen unabhängigen Staffelstimmen.
- Heartbeat, erfolgreicher Probe-Zugriff, letzte Fertigstellung, konkrete
  Fehlercodes, doppelfreie Fehler-IDs, Fortsetzungen und ausgewählte Quellsprachen
  werden protokolliert. Der Tagesbericht liest Aktiv-/Pause-Schalter, ohne
  Ablaufprognosen oder automatische Änderungen an Analysezugängen einzuführen.

Kunden-Playlists, manuelle Marker, Ablehnungen und blockierte Abschnitte werden
nicht überschrieben. Der Installer setzt keine Warteschlangen oder Tageszähler
zurück. Bestehende unvollständige Jobs werden nicht pauschal erneut eingeplant.

## Installation

Auf `epimediahub-analysis`, wo Controller und Compute unter
`/opt/epimediahub/provisioning` und `/opt/epimediahub/analysis` liegen, den
**auf einen Commit festgelegten** `install_episcene_20261012.py` herunterladen.
Die genaue Download-Adresse wird mit dem veröffentlichten Paket angegeben.
Das Skript enthält alle vier geprüften Module; weitere Downloads sind unnötig.

```bash
sudo python3 /tmp/install_episcene_20261012.py --check
sudo python3 /tmp/install_episcene_20261012.py --apply
```

`--check` liest ausschließlich: aktive SHA-256, erhaltene Worker-/Scheduler-
Schnittstellen, unabhängige Zugangsidentitäten, Datenbankzustand und private RPC-
Kompatibilität. Bei einer Abweichung stoppt der Installer vor Änderungen.
Nicht mit abgeschalteter Prüfung oder einem alten Komplettinstaller fortfahren;
die dann aktuellen Quellmodule müssen zuerst als Grundlage geprüft werden.

`--apply` hält den Analyse-Timer und Worker an, sichert Originaldateien und eine
konsistente Datenbankkopie in einen privaten Sicherungsordner, installiert das
Overlay auf Controller und Compute und prüft Syntax sowie RPC-Kompatibilität.
Erst danach werden die Sprachpräferenzen geschrieben und zuvor laufende Dienste
wieder gestartet. Bei einem Fehler werden nur die vom Installer geschriebenen
Code-Dateien und seine Sprachpräferenzen zurückgesetzt. Die vollständige
Datenbank wird dabei nicht zurückgespielt, damit gleichzeitig angelegte manuelle
Marker erhalten bleiben.

Die verfügbaren Analysezugänge werden anhand ihrer Namen zugeordnet. Bei den
bisherigen IDs bedeutet dies 8 → Deutsch sowie 9/10 → Italienisch; Archiv-/Pause-
Schalter, Zugangsdaten und manuelle Erneuerung bleiben erhalten.

## Noch auf echten Medien zu prüfen

Chicago Med braucht weiterhin fünf reale Beispiele aus mehreren Staffeln mit
bekannten Introgrenzen. Die Ursache für fehlende Treffer ist nicht als
Mindestlängenproblem bewiesen. Die allgemeine 15-Sekunden-Erkennungsgrenze wird
deshalb nicht pauschal gesenkt. Bereits menschlich bestätigte kurze Marker
können über die geprüfte Fassungsübernahme wiederverwendet werden.

Die synthetischen Fälle und echte Schwarz-/Ton-Dekodierung ersetzen keinen
Nachweis an den konkreten Anbieterdateien. Der Bericht am 13.10. umfasst je nach
Installationszeitpunkt einen gemischten Zeitraum; Änderungen nach dem
Installationszeitpunkt separat bewerten.

## Vergleich am nächsten Morgen

Baseline vom 12.10.: 115 unterschiedliche Folgen, 9 neue Vorschläge, 0
automatische Freigaben, 87 Rückstellungen. 82 von 105 alten `no_match`-Abschlüssen
enthalten ausdrücklich eine unvollständige Bildprüfung. Median 241,497 s,
95. Perzentil 459,465 s; Bildcache 67,5 %, Audiocache 4,6 %.

Prüfen: tatsächlicher Build-Wechsel und Installationszeit, vollständig geprüfte
Folgen, `partial`/technische Fehler/fehlende Partner, korrekte freigegebene
Grenzen, Wiederverwendung statt erneuter Vergleiche, bestätigte Sprachübernahmen
sowie deutsche Auswahl auf 4K und italienische Auswahl auf THE BEST. Mehr
Vorschläge allein sind kein Nachweis besserer Erkennung.
