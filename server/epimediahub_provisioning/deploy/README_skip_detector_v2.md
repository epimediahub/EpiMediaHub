# Intro- und Abspannerkennung V2 für Raspberry 0.8.2

V2 ist in `skip_automation.analyze` des vorhandenen Analyse-Workers eingebunden.
Eine zuvor separat installierte `skip_detector_v2.py` genügte dafür nicht.
Der geprüfte Installer `install_skip_catalogue.sh` installiert jetzt alle
zusammengehörigen Module, prüft das echte Dashboard und erwartet beim Neustart
das Health-Merkmal `skip_detector_v2`.

## Erkennung und Freigabe

- Pro Datei werden die ersten und letzten zwölf Minuten untersucht. Die
  tatsächliche Chromaprint-Framedauer kommt aus der installierten Bibliothek.
- Mehrere 12-Bit-Bänder finden mögliche Verschiebungen. Nur zwölf Positionen
  werden mit vollständigen 32-Bit-Hamming-Abständen geprüft. Kurze Lücken bis
  acht Frames sind erlaubt; mindestens 78 % der Frames müssen passen.
- Gemeinsame Abschnitte müssen 15 bis 120 Sekunden lang sein. Zu lange Szenen,
  gleichförmiger Ton, stille Ränder und vergleichbare Mehrfachvorkommen werden
  verworfen. Chromaprints Übergang aus gleichförmigem Ton wird mit dem
  Filtervorlauf des verwendeten Algorithmus 1 berücksichtigt.
- Bis zu vier andere Folgen derselben Quelle und Staffel liefern unabhängige
  Vergleiche. Mehrere Fassungen derselben Folgennummer zählen einmal.
  Unterschiedliche Zeitgrenzen werden gruppiert; erst die beste Gruppe liefert
  Median-Zeiten. Gleich starke konkurrierende Gruppen werden verworfen.
- Automatische V2-Freigabe benötigt mindestens drei Vergleichsfolgen, einen
  Qualitätsscore ab 0,92, mindestens 90 % passende Frames in jedem Paar und
  höchstens eine Sekunde Streuung der Grenzen. Der Score ist keine gemessene
  Trefferwahrscheinlichkeit. Ab 0,72 bleiben unsichere Ergebnisse zur Prüfung;
  schwächere Ergebnisse erzeugen keine neue Marke. Die bestehende automatische
  Übernahme kann einen V2-Prüffall nicht umgehen.

Bereits bestätigte Marken und eigene Korrekturen bleiben maßgeblich. Vor einer
automatischen Freigabe werden Laufzeit, Staffel, Folgennummer und Fingerprint
der beteiligten Dateien nochmals geprüft. Zurückgezogene Abschnitte zählen
nicht als Beleg für andere Folgen. Pro Datei und Abschnitt wird eine wirksame
Marke verwendet; frühere Varianten bleiben als ersetzte Einträge erhalten.

Neue Vergleichsfolgen ergänzen bis zu vier frühere Folgen aus dem begrenzten
Fingerprint-Cache, ohne deren Audio erneut zu laden. Fehlende Intros werden
beim Upgrade einmal zur regulären Nachprüfung eingeplant. Wiedergabepause,
DE-/IT-Priorisierung, Tagesbudget, Nachtprüfung und vorhandener Worker bleiben
erhalten. Es wird kein zusätzlicher Analyse-Dienst eingerichtet.

## Installation

Der aktuelle kopierbare Aufruf steht in `README_skip_catalogue.md`. Das Skript
sichert Anwendungscode und Datenbank, prüft 28 Payload-Dateien anhand SHA256
und führt vor Änderungen die Richtlinien- und Audiotests aus. Bei fehlender
V2-Health-Funktion wird auch ein zuvor separat installiertes Detektormodul
wiederhergestellt.

## Validierung und Grenzen

19 neue Tests prüfen falsche Wiederholungen, Stille, lange Szenen, signierte
Kotlin-Wörter, Verschiebungen, kurze Lücken, widersprüchliche Gruppen, den
tatsächlichen Worker-Aufruf, V2-Prüffälle, Korrekturen, zurückgezogene Belege,
geänderte Dateien, Cache-Ergänzung und das Tagesbudget. Ein echter
FFmpeg-/Chromaprint-Test erkennt vier 28-Sekunden-Musiksequenzen mit
unterschiedlicher Vorlaufzeit, Lautstärke und AAC-Kompression ohne menschliche
Referenz. Die Grenzen werden dabei gegen die bekannten Zeiten geprüft.

In einem lokalen Beispiel mit zwei Fenstern zu je 5.800 Frames brauchte der
Vergleich 67.817 vollständige Wortvergleiche und 0,048 Sekunden; das Durchprobieren
aller Verschiebungen hätte 33.640.000 Wortvergleiche benötigt. Das ist eine
lokale Messung, keine Raspberry-Laufzeit oder Trefferquote im Serienbestand.
Wiederkehrende Musik beweist nicht die redaktionellen Intro-Grenzen. Serien mit
wechselnden Intros, eingeblendeten Dialogen oder abweichenden Sprachfassungen
können deshalb weiterhin Prüf- oder Fehlfälle liefern.
