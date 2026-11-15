Android 1.0.16 verbessert fehlende und falsche Skip-Zeitmarken.

- Nach „Intro überspringen“ startet die Wiedergabe automatisch, auch nach einer Pause.
- Unter „Intro & Abspann“ lassen sich Anfang und Ende markieren, falsche Marken ausblenden und eigene Änderungen zurücknehmen. Entwürfe bleiben beim Schließen erhalten.
- Eigene Marken gelten für die konkrete Videodatei und Laufzeit und funktionieren auch ohne Serververbindung.
- Die Titelzuordnung lässt sich anhand von Titel und Erscheinungsjahr prüfen und korrigieren. Benannte, gültige Kapitel werden als zusätzliche Quelle genutzt.
- Geprüfte zentrale Zeitmarken werden synchronisiert; ungeprüfte Vorschläge verändern keine fremden Geräte.
- Netflix-Player, Audio-/Untertitelauswahl, Staffel-/Folgenauswahl und vorhandene Navigation bleiben enthalten.

Für zentrale Freigaben und Audioanalyse ist zusätzlich Raspberry 0.8.2 erforderlich. Der fertige Installer liegt unter:
https://raw.githubusercontent.com/epimediahub/EpiMediaHub/raspberry-v0.8.2-skip-markers/server/epimediahub_provisioning/deploy/upgrade_to_v082.sh

Danach: https://admin.epimediahub.com/admin/skip . Audioanalyse pro geeigneter Xtream-Playlist einschalten, wenn eine zusätzliche Verbindung beim Anbieter erlaubt ist. Sie wartet bei aktiver App-Wiedergabe und erkennt weitere Intros anhand freigegebener Referenzen derselben Staffel. Ergebnisse müssen im Dashboard geprüft und freigegeben werden. Fehlende Referenzen, wechselnde Intros und nicht analysierbare Streams bleiben über eigene Marken nutzbar.

Eine fehlerfreie automatische Erkennung jeder Schnittfassung wird nicht behauptet. Version 1.0.16 stellt dafür die sichere Erkennung und eine gezielte Korrektur bereit.
