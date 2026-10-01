# Korrektur für Anbieterweiterleitungen bei der Audioanalyse

Der bisherige Analyseproxy akzeptiert Weiterleitungen nur zum ursprünglichen
Host. Anbieter, die eine Videodatei auf einem zweiten öffentlichen Streaming-Host
ausliefern, können dadurch vor der Audioauswertung als unsafe_source abgelehnt
werden. Diese Korrektur erlaubt höchstens drei Weiterleitungsschritte.

Jedes Ziel und jede Verbindung werden erneut geprüft. Alle DNS-Antworten müssen
öffentliche Adressen sein; private, lokale und Multicast-Adressen bleiben
gesperrt. Die Verbindung wird an die geprüfte IP gebunden, während bei HTTPS der
ursprüngliche TLS-Hostname und die Zertifikatsprüfung erhalten bleiben.
HTTPS-zu-HTTP-Wechsel, URL-Benutzerinformationen und andere Protokolle sind
gesperrt. Nur Range, User-Agent und Accept-Encoding werden weitergereicht.
Weiterleitungsantworten werden geschlossen, ohne ihren Inhalt unbegrenzt zu lesen.

Fehler beim Anbieterzugriff erhalten feste Kategorien und passende deutsche
Dashboard-Meldungen. Rohe Fehlertexte, Anbieter-URLs und Zugangsdaten erscheinen
nicht in diesen Meldungen. Wiedergabesperren, Zeit- und Datenlimits sowie die
Prüfung vorgeschlagener Zeitmarken gelten weiterhin.

## Installation auf einem laufenden Server 0.8.2

fix_skip_analysis_redirects.sh lädt die zwei Analysemodule und ihre Prüfungen
aus einem unveränderlichen Git-Commit und kontrolliert ihre SHA-256-Prüfsummen.
Die Prüfungen laufen vor dem Stoppen der Dienste. Anschließend legt das Skript
ein geschütztes Backup von Code und SQLite-Datenbank an, ersetzt die beiden
Module und prüft den neu gestarteten Server über seinen Health-Endpunkt.

Fehlgeschlagene Analyseaufträge bereits aktivierter Playlists werden erneut
eingeplant. Der vorherige Aktivzustand des Timers wird wiederhergestellt.
Bei einem Installationsfehler stellt das Skript den bisherigen Code wieder her.
Es spielt die Datenbank nicht zurück und überschreibt dadurch keine inzwischen
eingegangenen Geräteänderungen. Freigegebene Zeitmarken und Konfigurationen
werden durch das Skript nicht geändert.

Der Server bleibt auf API-Version 0.8.2. Die Android-App 1.0.16 kann weiter
verwendet werden; diese Korrektur erfordert kein APK-Update.

## Prüfung

Lokal bestanden 20 Prüfungen zur Diagnose und zu Anbieterweiterleitungen.
Die neuen zwölf Prüfungen umfassen echte HTTP-Weiterleitungen, Range-Zugriffe,
FFprobe und Chromaprint sowie die Sperren für private Ziele, DNS-Wechsel,
Weiterleitungsschleifen und HTTPS-Abstufungen.

Der Installer führt die zwölf Weiterleitungsprüfungen auch auf dem Raspberry
aus. Der Zugriff auf den konkreten Anbieter muss nach der Installation mit dem
erneut eingeplanten Auftrag geprüft werden.
