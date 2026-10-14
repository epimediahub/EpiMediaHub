# EpiScene – 40 Referenzfolgen (14. Oktober 2026)

Diese **40 konkreten Staffel-/Folgenkombinationen** sind in den EpiScene-Tagesberichten vom 9. bis 14. Oktober 2026 nachgewiesen. Auswahl: **20 aus Playlist 8 / 4K ANALYSE (Deutsch)** und **20 aus Playlist 10 / THE BEST (Italienisch)**. Ob jede Folge zum heutigen Zeitpunkt unverändert verfügbar ist, muss die App zeigen. Die zuvor von dir markierten Folgen bei *Lie to Me*, *The Lincoln Lawyer* S1E1–5 und *MobLand* S1E1/S1E3 sind bewusst nicht Teil der 40 neuen Markierungen.

## Playlist 8 – 4K ANALYSE – 20 Folgen

- [ ] **MobLand** – S1E2, S1E4, S1E5, S1E6, S1E7 (5)
- [ ] **The Lincoln Lawyer** – S1E6, S1E7, S1E8, S2E1, S2E2, S3E1 (6)
- [ ] **Chicago Med** – S1E1, S1E2, S1E3, S2E1, S2E2 (5)
- [ ] **Fire Country** – S1E1, S1E2, S1E3, S1E4 (4)

## Playlist 10 – THE BEST – 20 Folgen

- [ ] **Il bello delle donne (IT)** – S1E1, S1E2, S1E3, S1E6, S2E1, S2E2, S3E1, S4E1 (8)
- [ ] **Berlino (Italiano)** – S1E1, S1E2, S1E3, S1E4, S1E5 (5)
- [ ] **Bridgerton** – S1E1, S1E2, S1E3, S2E1 (4)
- [ ] **Processo al male: Hitler e i nazisti** – S1E1, S1E2, S1E3 (3)

## Was markieren?

Prüfe bei jeder Folge **Intro**, **Rückblick** („Bisher geschah…“) und **Abspann**. Markiere jeweils den **tatsächlich vorhandenen** Abschnitt mit präzisen Start- und Endzeiten. **Wenn ein Markertyp in der Folge nicht existiert, keinen künstlichen Marker setzen**. Insbesondere beim Abspann den Übergang **vom letzten Inhalt zum wirklichen Abspann** erwischen – nicht erst die letzten 40 Sekunden der Datei. Notiere bitte keine Zeiten zusätzlich im Chat.

## Automatische Zuordnung

Die Datei `plan.json` enthält alle **40 einzelnen** Referenz-IDs REF-01 bis REF-40. Der optionale, SHA-256-geprüfte Installer `install.sh` registriert diese Runde auf dem Hetzner-Server. Ein stündlicher read-only Tracker beobachtet anschließend **neu eingetragene oder bearbeitete** App-/Geräte-Marker in `/var/lib/epimediahub/provisioning.db` für diese Episoden. So sind neue Markierungen eindeutig in der Auswahl wiederzufinden, und du musst sie nicht einzeln melden.

**Keine automatische Freigabe:** `source=device` beweist keine menschliche Bestätigung. Es wird nur die Erfassung überprüft. Alte Marker bleiben erhalten; das erste Aktivieren erzeugt eine Baseline. Um die neue Referenzrunde korrekt zu zählen, Installer **vor den neuen Markierungen** ausführen. Ein fehlender Rückblick/Intro kann ohne ausdrückliche negative Bestätigung nicht automatisch als erledigt bewertet werden.

Sobald du die Folge markiert hast, einfach weitermachen. Wenn du mit der Referenzrunde durch bist, reicht **einmal „40er-Runde fertig“**. Dann vergleichen wir die gespeicherten Marker mit EpiScenes Vorschlägen und übernehmen nur tatsächlich bestätigte Referenzen in die Learning Engine.

**Status:** GitHub-Dateien sind vorbereitet; Server-Tracker läuft erst nach Ausführung des Installationsbefehls. Die Android-App wird hierbei nicht verändert.