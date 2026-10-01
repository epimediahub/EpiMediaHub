# Genauere Intro-Zeitgrenzen

Der bisherige Audiovorschlag begann eine Sekunde nach der übertragenen Referenz
und endete eine Sekunde früher. Die neue Berechnung übernimmt die geprüften
Grenzen ohne diesen pauschalen Beschnitt. Ein bereits ausreichend ähnlicher und
eindeutiger Treffer wird zwischen benachbarten Fingerabdruckpositionen verfeinert.
Die erforderliche Bitübereinstimmung und die Ablehnung mehrdeutiger Treffer
bleiben bestehen. Es entstehen weiterhin Vorschläge zur manuellen Prüfung.

Eine Dashboard-Korrektur entfernt den abgeleiteten Fingerabdruck dieser
Zeitmarke. Der Worker prüft zusätzlich Zeitpunkt, Ausschnitt und Länge des
gespeicherten Referenztons. Wird die Marke während des Decodierens korrigiert,
kann der ältere Ton nicht der neuen Markerfassung zugeordnet werden.

## Installation auf einem vorhandenen Raspberry 0.8.2

```bash
curl -fsSL https://raw.githubusercontent.com/epimediahub/EpiMediaHub/7af4370abe58916b6d2d0228c36ecb647daa2c39/server/epimediahub_provisioning/deploy/fix_skip_analysis_boundaries.sh -o /var/tmp/epimediahub-skip-boundaries.sh &&
sudo bash /var/tmp/epimediahub-skip-boundaries.sh
```

Der Installer prüft ein unveränderliches Quellpaket mit SHA-256 und führt vor der
Änderung 28 Audio-, Dashboard-, Referenz- und Weiterleitungsprüfungen aus.
Er übernimmt die Worker-Sperre, sichert Code und SQLite-Datenbank und stellt
bei einem Fehler den vorherigen Code wieder her. Der ursprüngliche Timerzustand
bleibt erhalten. Eine laufende Analyse wird nicht unterbrochen; der Befehl kann
nach deren Abschluss erneut ausgeführt werden.

Vorhandene Zeitmarken, Freigaben und Aufträge werden durch den Installer nicht
geändert. Danach eine weitere, noch unmarkierte Folge in der App öffnen und
wieder beenden und den neuen Vorschlag im Dashboard kontrollieren.
Android 1.0.16 und die API-Version 0.8.2 bleiben kompatibel.

## Nachweis und Grenzen

https://github.com/epimediahub/EpiMediaHub/actions/runs/36846605053 bestand die
Dashboard-/Geräteprüfung, 14 Marker-/Audioprüfungen und 43 zusätzliche
Analyseprüfungen ohne ausgelassene Tests. Die neuen Audioprüfungen nutzen
nicht ganzzahlige Startzeiten, veränderte Lautstärke und AAC-Neucodierung.
Die überprüften Start- und Endzeiten weichen höchstens 150 ms vom bekannten
Referenzsignal ab. Ein wiederholtes Intro bleibt mehrdeutig und wird abgelehnt.
Korrekturen und eine Änderung während des Decodierens sind über SQLite/HTTP
abgedeckt.

Sieben isolierte Installationsprüfungen bestanden: aktiver und inaktiver Timer,
fehlerhafter Health-Check mit Codewiederherstellung, veränderte Downloads,
fehlgeschlagene Vorprüfungen, aktive Worker-Sperre und falsche Serverversion.
Die Prüfungen verwenden simulierte Dienste und Downloads sowie eine echte
SQLite-Sicherung und kontrollieren unveränderte freigegebene Zeiten.

Diese Messwerte stammen aus bekannten Testsignalen. Die Endzeit wird weiterhin
aus der geprüften Länge der Referenz abgeleitet; geänderte Intro-Schnittfassungen
erfordern eine Prüfung an der jeweiligen Folge.
