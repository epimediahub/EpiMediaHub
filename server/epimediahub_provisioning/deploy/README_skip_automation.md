# Staffelautomatik und Online-Zeitvorschläge auf Raspberry 0.8.2

Die Erweiterung plant weitere Folgen einer bereits in der App geöffneten Staffel ein, findet wiederkehrenden Ton ohne erste handgesetzte Zeitgrenze und ergänzt vorhandene Online-Zeiten. Eindeutige Audiotreffer können anhand unabhängiger Belege automatisch freigegeben werden. Unsichere Ergebnisse bleiben unter **Zur Prüfung**.

Die vorhandene Android-App 1.0.16 verwendet die freigegebenen Marker über ihre bestehende API. Die Raspberry-API bleibt auf 0.8.2 und meldet zusätzlich `skip_season_automation` und `skip_online_candidates`.

## Installation

Voraussetzung ist der laufende Raspberry-Server 0.8.2 mit FFmpeg, FFprobe und Chromaprint. Die Dateien sind auf einen unveränderlichen Commit und SHA-256-Prüfsummen festgelegt.

```sh
curl -fsSL https://raw.githubusercontent.com/epimediahub/EpiMediaHub/31603e6ce362ac9bf9e2ea6f1b79bec8d97701ad/server/epimediahub_provisioning/deploy/install_skip_automation.sh -o /var/tmp/epimediahub-skip-automation.sh &&
sudo bash /var/tmp/epimediahub-skip-automation.sh --enable-automatic
```

Die Option aktiviert Staffelautomatik und Online-Abfragen für bereits eingeschaltete, geeignete Audio-Playlists aktiver Kunden. Ohne die Option werden die Funktionen installiert; die bisherige Analyse bleibt eingestellt, bis die Staffelautomatik im Dashboard aktiviert wird.

Der Installer prüft die Audio-, Referenz-, API- und Freigabelogik vor der Installation. Ein laufender Worker behält seine gemeinsame Dateisperre; in diesem Fall kann der Installer nach Abschluss erneut ausgeführt werden. Anwendungscode und eine konsistente SQLite-Sicherung werden unter `/var/backups/epimediahub/skip-automation-*` gespeichert. Bei einem Fehler werden vorheriger Code, die vom Installer geänderten Einstellungen und Auftragszustände sowie der vorherige Timerzustand wiederhergestellt. Zeitmarken und Gerätedaten werden dabei nicht durch eine alte vollständige Datenbank ersetzt.

## Einrichtung im Dashboard

Unter [Intro, Rückblick & Abspann](https://admin.epimediahub.com/admin/skip) kann jede Playlist ihre Staffelautomatik und Online-Abfragen separat einstellen. **Letzte Analysen** zeigt die Verarbeitung; **Letzte Online-Abfragen** zeigt fehlende Zuordnungen, vorhandene Zeiten oder einen nicht erreichbaren Dienst.

Für die Suche über Namen unter **Serien über Namen zuordnen** einen eigenen [TMDB-API-Schlüssel (v3)](https://www.themoviedb.org/settings/api) eintragen. Alternativ wird `EPIMEDIAHUB_TMDB_API_KEY` aus der Serverumgebung verwendet. Der gespeicherte Schlüssel wird in der Oberfläche nicht angezeigt.

Eine bekannte Serienkennung kann bei einem Marker unter **Titelzuordnung korrigieren** gespeichert werden. Für diese direkte Zuordnung benötigen die öffentlichen TheIntroDB-Leseabfragen keinen TMDB-Suchschlüssel. Solche ausdrücklich korrigierten Kennungen haben Vorrang vor einer automatischen Suche.

## Belege und Freigaben

| Ergebnis | Verwendung |
| --- | --- |
| Passende benannte Videokapitel | Vorschlag zur Prüfung |
| TheIntroDB-Zeiten für Serie, Staffel, Folge und angefragte Dateilaufzeit | Vorschlag zur Prüfung |
| Wiederkehrender, eindeutiger Ton in mindestens drei verschiedenen Folgen | Vorschlag mit ungeprüften Zeitgrenzen |
| Ein Treffer aus einer freigegebenen Referenzfolge | Audiovorschlag zur Prüfung |
| Zwei verschiedene, einzeln geprüfte Referenzfolgen bestätigen dieselben Grenzen | Automatische Freigabe bei weiteren bestandenen Prüfungen |
| Eine geprüfte Referenz und Online-Zeiten mit bestätigter Serienkennung stimmen überein | Automatische Freigabe bei weiteren bestandenen Prüfungen |

Zur automatischen Freigabe muss jede verwendete Audioreferenz mindestens 92 % Bitübereinstimmung erreichen und einen eindeutigen Treffer liefern. Die ersten und letzten musikalischen Ausschnitte müssen denselben Versatz bestätigen; Start und Ende der unabhängigen Belege dürfen jeweils höchstens 500 ms auseinanderliegen. Referenzdateien werden erneut auf ihre Laufzeit geprüft und ihre benötigten Audioabschnitte vollständig gelesen. Die Zielgrenzen müssen innerhalb des tatsächlich decodierten Audios liegen. Diese Schwellen sind Kriterien für die Übernahme und keine statistische Fehlerwahrscheinlichkeit.

Automatisch freigegebene Marker werden erst nach ausdrücklicher menschlicher Prüfung als weitere unabhängige Referenz zugelassen. Eigene noch ungeprüfte Marker, bestehende Freigaben, Ablehnungen und „Kein Abschnitt“-Entscheidungen schützen die betreffende Datei vor einer automatischen Übernahme. Änderungen während der Analyse werden beim abschließenden Schreiben erneut geprüft. Ein Abspann, der deutlich vor dem Dateiende aufhört, bleibt wegen möglicher nachfolgender Szenen zur Prüfung.

## Zuordnung und Betriebsgrenzen

Die Anbieterserie wird anhand der bestehenden Serienkennung der App und einer passenden Katalog-ID identifiziert. Der Katalog muss die bereits geöffnete Ankerfolge mit derselben Datei, Erweiterung, Staffel und Folgennummer enthalten. Doppelte oder widersprüchliche Nummern führen zu keiner Staffelregistrierung. Bereits vom Player identifizierte Dateien werden nicht neu beschriftet. Neue Katalogfolgen erhalten ihre Laufzeit erst durch FFprobe.

Die TMDB-Suche bereinigt bekannte Sprach- und Qualitätspräfixe sowie Folgennummern und verlangt einen eindeutigen Titel, dasselbe Erscheinungsjahr und eine vorhandene Staffel/Folge. Keywords liefern Suchkandidaten. Unbestätigte Kennungen aus Client-Metadaten können Online-Vorschläge liefern, reichen aber nicht als unabhängiger Beleg zur automatischen Freigabe.

Pro Tag werden höchstens 24 Folgen bearbeitet; erneutes Einplanen setzt dieses Budget nicht zurück. Kataloge und Online-Ergebnisse werden höchstens täglich erneuert. Ein Katalog umfasst höchstens 10.000 Serien und eine Staffel höchstens 200 Folgen. Audio wird in begrenzten Fenstern am Anfang und Ende untersucht; das bisherige Datenlimit von 128 MiB je kontrolliertem Dateizugriff bleibt bestehen. Der abgeleitete Fenster-Cache ist auf 256 Einträge begrenzt. Laufende Wiedergabe desselben Anbieteraccounts hält die Analyse an.

Die [TheIntroDB-API](https://theintrodb.org/docs) erhält ausschließlich Titelkennungen, Staffel, Folge und Dateilaufzeit. Anbieterverbindungen, Zugangsdaten, Audio und eigene Marker werden nicht an die Online-Datenbank übermittelt. Die Erweiterung verwendet nur Leseabfragen. Das bisherige direkte Referenz-Diagnoseskript bleibt auf die isolierte RAM-Kopie beschränkt und deaktiviert darin die neue Automatik.

## Validierung

[GitHub Actions](https://github.com/epimediahub/EpiMediaHub/actions/runs/36919739398) prüfte die bisherige Dashboard-/Gerätefunktion, 14 ursprüngliche Marker-/Audiofälle, 77 zusätzliche Audio-, Zuordnungs-, API- und Datenbankfälle und 8 isolierte Installationsfälle. Alle 99 Tests liefen ohne übersprungene Fälle erfolgreich. Reale WAV-/AAC-Testdateien prüfen verschobene Intros, unterschiedliche Lautstärke und die automatische Übernahme; die Genauigkeit dieser synthetischen Testclips ist keine Garantie für jede Anbieterdatei.

Die öffentliche Live-Abfrage für Lie to Me S2 E13 war aus der CI-Umgebung nicht erreichbar. Deshalb ist weder die Erreichbarkeit vom Raspberry noch die Verfügbarkeit passender Online-Zeiten für diese Folge als erfolgreich geprüft angegeben. Die lokale Audioanalyse und bestätigte eigene Marker funktionieren unabhängig von diesem optionalen Dienst.
