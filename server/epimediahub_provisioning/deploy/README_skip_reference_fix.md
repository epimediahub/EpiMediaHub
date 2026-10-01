# Freigegebene Introreferenzen für die Analyse registrieren

Eine im Player gespeicherte Zeitmarke enthält die Angaben zu Playlist und
Videodatei. Bisher nutzt nur die Markerabfrage diese Angaben zur Registrierung
der Datei; der Marker-Submit speichert allein die Zeitmarke. Wird die Analyse
erst nach Beginn der Wiedergabe aktiviert oder scheitert die erste Abfrage,
kann ein freigegebener Marker ohne registrierte Referenzdatei zurückbleiben.
Die Analyse einer weiteren Folge meldet dann fälschlich, dass zuerst ein Intro
markiert werden müsse.

Der Submit registriert nun die Datei mit den bestehenden Prüfungen für
Playlistbesitz, ausdrückliche Aktivierung, numerische Datei-ID und passenden
Dateihash. Wird die Datei eines schon freigegebenen Intros später registriert,
plant der Server wartende Folgen derselben Serienzuordnung und Staffel erneut
ein. Die vorhandene Freigabe und ihre Zeiten bleiben bestehen. Andere Serien,
Staffeln, deaktivierte Quellen sowie laufende oder fehlgeschlagene Aufträge
werden durch diesen Ablauf nicht erneut eingeplant.

Für einen früher gespeicherten Marker muss die Referenzfolge gegebenenfalls
einmal in der App geöffnet und wieder beendet werden. Dadurch übermittelt die
App die fehlende Datei-ID mit ihrer Laufzeit. Die Zeiten brauchen nicht erneut
gesetzt oder freigegeben zu werden. Der Worker zeigt für diesen Fall eine
entsprechende Meldung mit Staffel und Referenzfolge an.

## Raspberry-Installation

fix_skip_analysis_references.sh benötigt einen laufenden Server 0.8.2 und
installiert die drei Marker-/Analysemodule aus einem unveränderlichen Commit
mit SHA-256-Prüfung. Vor dem Stoppen der Dienste laufen die Weiterleitungs- und
Referenzprüfungen einschließlich echter Flask-HTTP-Anfragen in einer separaten
Testdatenbank. Code und Produktionsdatenbank werden gesichert. Bei einem
Installationsfehler wird der vorherige Code wiederhergestellt.

Nach einem erfolgreichen Health-Check werden bereits wartende Aufträge
aktivierter Quellen einmal neu eingeplant. Eine zusätzliche reine Leseprüfung
zeigt, welche freigegebenen Marker zur Folge passen und ob deren Referenzdateien
registriert sind. Sie verändert keine Zeitmarken, greift nicht auf Videodateien
zu und gibt keine Anbieter-URLs oder Zugangsdaten aus.

Die API-Version bleibt 0.8.2; Android 1.0.16 unterstützt diesen Ablauf.
Die zuvor ergänzten Prüfungen öffentlicher Anbieterweiterleitungen gelten weiter.

## Validierung

Der GitHub-Lauf für Commit 1f86c3dda475ca1e83d63fd346a04fbccda5d35a bestand:
bestehende Dashboard-/Geräteprüfungen, die 14 Marker- und Audioprüfungen
und 21 zusätzliche Weiterleitungs-/Referenzprüfungen ohne ausgelassene Tests.
Die Referenztests prüfen den Submit ohne vorherigen Lookup, die erneute Abfrage
eines bereits freigegebenen Markers, die automatische Wiederaufnahme einer
wartenden Folge und die weiterhin erforderliche Freigabe des Audiovorschlags.
