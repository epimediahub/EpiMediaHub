# Sprachpriorität, Serien-/Staffelfreigabe und Gesamtkatalog für Raspberry 0.8.2

Der vorhandene Worker erfasst den vollständigen Serienbestand der aktivierten
XTREAM-Playlists, auch ohne vorheriges Abspielen. Neue oder vom Anbieter als
geändert gemeldete Folgen werden in die bestehende Audioanalyse eingeplant.
Unveränderte, bereits bearbeitete Dateien werden beim Katalogabgleich nicht
erneut eingeplant. Ein Katalogfund allein gibt keine Zeitmarke frei.

## Installation

Voraussetzung ist der laufende Raspberry-Server 0.8.2 mit Audioanalyse und
Staffelautomatik für die gewünschten Playlists. Android 1.0.16 bleibt kompatibel.

```sh
curl -fsSL https://raw.githubusercontent.com/epimediahub/EpiMediaHub/cfc403b54d35b3f851c9af165a556de0b547d708/server/epimediahub_provisioning/deploy/install_skip_catalogue.sh -o /var/tmp/epimediahub-skip-catalogue.sh &&
sudo bash /var/tmp/epimediahub-skip-catalogue.sh --wait-worker
```

Der Aufruf aktualisiert den vorhandenen Dienst und erhält Katalogeinstellungen,
Nachttermine und das Tagesbudget. Um zusätzlich die erstmalige Bestandsaufnahme
zu starten, kann `--start-catalogue` an den Bash-Aufruf angehängt werden.
Der Schalter startet ausschließlich bereits aktivierte Automatik-Playlists
mit erlaubter Audioanalyse und aktivem Kunden. TMDB-Schlüssel,
Anbieterkonfiguration, Geräte und menschliche Zeitmarken bleiben erhalten.

`--wait-worker` wartet bei einer laufenden Analyse bis zu 15 Minuten auf den
vorhandenen Worker-Lock, ohne den Durchlauf abzubrechen. Der Timer muss dafür
nicht manuell gestoppt werden. Ohne diese Option endet der Installer bei einem
belegten Lock weiterhin vor Änderungen. Beide Optionen sind kombinierbar.

Das Skript lädt siebzehn Dateien aus einem festen Commit und prüft SHA256,
Syntax sowie die tatsächlichen Richtlinien-, API- und Audiotests vor Änderungen.
Es verwendet den bestehenden Worker-Lock, sichert Code und SQLite-Datenbank
und stellt bei einem fehlgeschlagenen Neustart den vorherigen Code sowie nur
die selbst geänderten Katalogeinstellungen wieder her.

## Online-Abfragen und Fehlermeldungen

TMDB ordnet Serientitel zu Kennungen zu. Die Zeitmarken selbst kommen von
TheIntroDB; ein TMDB-Schlüssel ist kein Schlüssel für diese Zeitdatenbank.
Die ursprüngliche HTTP-Antwort bleibt jetzt auch hinter dem lokalen Relay erhalten.

- TheIntroDB HTTP 404 bedeutet fehlende Online-Zeitmarken für die Folge.
  Das Ergebnis wird einen Tag zwischengespeichert und erzeugt keine Fehlerwiederholung.
- TMDB HTTP 404 bezeichnet eine nicht vorhandene Serien-/Folgenzuordnung;
  Titel, Staffel und Folgennummer sollten überprüft werden.
- TMDB HTTP 401 zeigt einen nicht akzeptierten Schlüssel an. Beim Speichern
  eines neuen Schlüssels wird nur die TMDB-Zugriffspause aufgehoben.
- HTTP 403, Abfragelimits (HTTP 429), Server-, DNS-, TLS- und Zeitüberschreitungsfehler
  haben getrennte Meldungen. URLs, Schlüssel und Antworttexte werden nicht ausgegeben.
- Abfragelimits pausieren den gesamten betroffenen Dienst. Die gemeldete Wartezeit
  wird bis zu 24 Stunden berücksichtigt; ohne Wartezeit gilt bei HTTP 429 eine Stunde.

Alte Einträge mit der pauschalen Meldung „Online-Datenbank derzeit nicht erreichbar“
werden einmal erneut zur Prüfung vorgemerkt. Der Worker prüft im Leerlauf höchstens
eine solche Folge je Aufruf und höchstens 96 Folgen pro UTC-Tag. Auch vorübergehende
Fehler werden nach ihrer Wartezeit erneut geprüft. Diese Nachprüfungen rufen nur
Metadaten ab, laden keine Videodatei und wiederholen keine Audioanalyse. Sie laufen
auch nach Ausschöpfen des Audiolimits, erhalten dessen Zähler und alle Audiojobs.
Gemeldete Wiedergabe, ausgeschaltete Analyse sowie menschliche Entscheidungen
bleiben vorrangig. Gefundene Online-Zeiten erzeugen Vorschläge zur Prüfung.

## Ablauf

### Deutsch und Italienisch bevorzugen

Deutsch und Italienisch haben gemeinsam dieselbe erste Priorität. Danach
folgen alle anderen Serien und Serien ohne eindeutige Sprachangaben. Innerhalb
jeder Sprachgruppe behalten neue oder geänderte Folgen Vorrang vor dem alten
Bestand. Diese Reihenfolge gilt für die Katalogaufnahme, die Audio-Warteschlange,
die Staffelautomatik und fällige Online-Nachprüfungen. Noch nicht aufgenommene,
bekannt bevorzugte Serien werden vor älteren Jobs der zweiten Gruppe erfasst.

Der Raspberry ruft die Kategorien seiner aktivierten Anbieter-Playlists ab und
ordnet sie über `category_id` beziehungsweise `category_ids` den Serien zu.
Beispiele sind `de Serien`, `deutsche Seiten`, `DE: Netflix Serien`,
`IT: Netflix Serie` und `SERIE TV ITALIA`. Eindeutige Serientags wie `[DE]`,
`[GER]`, `[IT]` oder `[ITA]` sowie deklarierte Audiosprachen werden ebenfalls
berücksichtigt. Eine ausdrücklich andere angebotene Audiosprache hat Vorrang
vor Länderkennzeichnungen. Deutsch synchronisierte Serien können somit
bevorzugt werden, auch wenn das Original aus einem anderen Land stammt.

TMDBs `original_language` und das Produktionsland werden nicht zur Bestimmung
der angebotenen Sprache verwendet. Normale Serientitel wie `It`, `It Takes Two`
oder `Deutschland 83` ergeben alleine keine bevorzugte Einstufung. Die
Kategoriephrase `Series de España` wird nicht wegen des Worts `de` als Deutsch
eingestuft. Fehlende oder widersprüchliche Kategorien verhindern keine normale
Analyse; die Sprache wird nicht durch zusätzliches Herunterladen oder erneutes
Analysieren des Tons ermittelt.

Beim Upgrade werden bestehende Kataloge einmalig anhand ihrer behaltenen
Sprachtags eingestuft. Beim nächsten Leerlauf werden zusätzlich Kategorien und
Serienlisten als Metadaten neu abgefragt, damit vorhandene Warteschlangen die
aktuelle Zuordnung erhalten. Dabei bleiben Katalogcursor, Generationsnummer,
Nachttermin, Tagesbudget, bereits erledigte Audiojobs und menschliche Zeitmarken
erhalten. Ein fehlgeschlagener Metadatenabruf wird frühestens nach einer Stunde
wiederholt. Anschließend werden die Kategorien bei den regulären Nachtlisten
erneut berücksichtigt.

### Bestandsaufnahme und Nachtlauf

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
- Es werden höchstens acht Metadatenschritte pro Aufruf ausgeführt. Eine
  Serienliste kann eine zusätzliche Kategorienabfrage benötigen, also höchstens
  sechzehn Anbieterabfragen pro Aufruf; nach
  30 Sekunden beginnt kein weiterer Schritt. Jeder Abruf hat eigene Transport-
  und Größenlimits. Pro Katalog sind 20.000 Serien, pro Serie 10.000 Folgen
  und pro Staffel 200 Folgen zulässig.
- Alle Abrufe bleiben seriell und pausieren bei gemeldeter Wiedergabe desselben
  Anbieterkontos. Öffentliche Ziele, Weiterleitungen, Laufzeiten und
  Dateizuordnung werden wie bisher geprüft.
- Innerhalb jeder Sprachgruppe haben neu eingeplante Folgen aus Nachtläufen
  Vorrang vor dem alten Bestand.
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

Die Zeitmarken sind nach Serie → Staffel → Folge gegliedert. Die Titelübersicht
zeigt höchstens 20 Serien pro Seite; die Auswahl einer Staffel lädt höchstens
25 Folgen pro Seite mit sämtlichen zugehörigen Zeitmarken. Weitere Seiten
machen auch Einträge jenseits der bisherigen Grenze von 100 Markern erreichbar.
Staffeln und Folgen werden numerisch sortiert. Gleichnamige Serien mit
unterschiedlichen Quelldateizuordnungen bleiben getrennt. Filme zeigen ihre
Zeitmarken direkt, ohne künstliche Staffeln.

Die Ansichten „Zur Prüfung“, „Freigegeben“, „Abgelehnt“ und „Ersetzt“ sowie
„Letzte Analysen“ und „Letzte Online-Abfragen“ verwenden die Gruppierung.
Beim Bearbeiten bleibt der gewählte Filter erhalten; weiterhin darin sichtbare
Zeitmarken werden mit geöffneter Serie, Staffel und Folge wieder angezeigt.
Nach einer Freigabe verschwindet der Eintrag aus „Zur Prüfung“ wie bisher.

### Alle Vorschläge einer Serie oder Staffel freigeben

In „Zur Prüfung“ enthält eine geöffnete Serie den Button „Alle Vorschläge
dieser Serie freigeben“. Jede geöffnete Staffel hat zusätzlich „Alle Vorschläge
dieser Staffel freigeben“. Die Zahl am Button zählt alle offenen Zeitmarken
im gewählten Bereich. Beide Buttons erfassen auch Folgen auf weiteren Seiten;
die Serienfreigabe umfasst sämtliche Staffeln einschließlich Spezialfolgen.
Intro, Rückblick und Abspann werden zusammen geprüft. Gleichnamige Serien
mit anderer Quellenzuordnung werden nicht mit freigegeben.

Die Aktion entspricht einer menschlichen Freigabe. Sie gilt nur für zu diesem
Zeitpunkt offene Vorschläge und schaltet keine zukünftigen Freigaben ein.
Nahezu gleiche Vorschläge derselben Datei, Laufzeit und Abschnittsart werden
zu einer wirksamen Zeitmarke zusammengeführt. Widersprüchliche Grenzen,
abweichende Folgenzuordnungen und Vorschläge zu bereits freigegebenen oder
abgelehnten Abschnitten bleiben unverändert zur Einzelprüfung. Unterschiedliche
Dateifassungen können jeweils eine eigene Freigabe erhalten. Danach zeigt
das Dashboard die Anzahl freigegebener Marken, zusammengeführter Duplikate
und zurückgelassener Vorschläge.

Die gesamte Auswahl wird in einer Datenbanktransaktion verarbeitet. Ein
Fehler führt daher nicht zu einer teilweisen Freigabe. Ein erneuter Klick
auf eine bereits verarbeitete Auswahl ändert bestehende Entscheidungen nicht.
Der Button verwendet dieselbe Admin-Anmeldung und denselben Sitzungsschutz
wie eine Einzelprüfung.

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

## Doppelte Vorschläge und hohe Audiotreffer

Für dieselbe Datei, Laufzeit und Abschnittsart werden maschinelle Vorschläge
mit höchstens 500 ms Abweichung an beiden Grenzen zusammengeführt. Der stärkste
Audiovorschlag bleibt als stabiler Eintrag erhalten, auch wenn mehrere
Referenzfolgen denselben Abschnitt erkennen. Materiell widersprüchliche
Grenzen bleiben getrennt. Unterschiedliche Dateien und Laufzeiten werden
nicht zusammengelegt; mehrere Fassungen derselben Folge sind gekennzeichnet.

Eine geprüfte Referenz derselben Serie und Staffel genügt jetzt für die
automatische Freigabe ab 92 % Audioähnlichkeit. Der vollständige Fingerabdruck
muss an einer eindeutigen Position passen. Beginn und Ende des musikalischen
Ausschnitts werden rund um diese Position separat abgeglichen; kurze Motive
an anderen Stellen verhindern dadurch keine sonst eindeutige Freigabe.
Mehrere starke Referenzen dürfen einander nicht um mehr als 500 ms widersprechen.
Online-Zeiten können zusätzliche Belege liefern, sind dafür aber nicht nötig.
Für den Abspann bleibt die Kontrolle möglicher Szenen nach dem Abspann erhalten:
Die automatisch freigegebene Grenze muss bis auf eine Sekunde ans Dateiende reichen.

Aktuelle Datei, gemessene Laufzeit, unveränderte Referenz, Kunden- und
Playlistfreigabe werden vor der Veröffentlichung erneut geprüft. Eigene
Korrekturen, Ablehnungen und noch ungeprüfte eigene Marken haben Vorrang.
Maschinelle Freigaben werden erst nach tatsächlicher menschlicher Prüfung als
neue Referenz zugelassen; die Automatik bestätigt sich nicht selbst.

Beim Update werden vorhandene Doppelvorschläge einmalig nach „Ersetzt“
archiviert. Hohe, noch offene Audiovorschläge aktivierter Automatik-Playlists
werden zur erneuten normalen Analyse eingeplant. Gespeicherte Prozentwerte
allein werden nicht zur Freigabe benutzt. Tagesbudget und Wiedergabevorrang
bleiben wirksam. Auch eine menschliche Entscheidung oder automatische Freigabe
archiviert die übrigen maschinellen Vorschläge desselben Abschnitts.

## Tageslimit und App-Performance

96 ist ein Tagesbudget, keine Anzahl gleichzeitig laufender Analysen. Ein
höheres Limit startet weiterhin höchstens eine Audioanalyse pro Worker-Aufruf.
Die Berechnung erfolgt auf dem Raspberry; sie erhöht die Rechenlast der
Android-App nicht direkt. Die bereitgestellte systemd-Unit begrenzt den Worker
auf 256 MiB RAM und CPUQuota=50%, also die Hälfte eines einzelnen CPU-Kerns.
Ein höheres Budget kann die gesamte Laufzeit und den Datenverkehr erhöhen.
Bei ausgelasteter gemeinsamer Internetverbindung, Raspberry-Ressourcen oder
Anbieter-Verbindungslimits können trotzdem Auswirkungen auf Wiedergabe oder
Antwortzeiten entstehen. Die tatsächlich schaffbare Anzahl hängt vom Gerät
und Anbieter ab und wurde auf dem jeweiligen Raspberry nicht gemessen.

Die Analyse wartet bei gemeldeter Wiedergabe desselben Anbieterkontos.
Wiedergaben außerhalb der EpiMediaHub-App kann diese Meldung nicht erfassen.

## Validierung

32 zusätzliche SQLite-/API-Tests decken ungespielte Serien, mehrere Staffeln,
nächtliche Neuzugänge, unveränderte Dateien, fehlende/stale Zeitstempel,
Neustarts, doppelte Nummerierung, unsichere Dateiformate, Wiedergabevorrang,
konkurrierendes Ausschalten, Tagesbudget und Zeitumstellung ab.

Fünfzehn isolierte Installationstests prüfen Erfolg, bestehende Marker/Schlüssel,
inaktive Timer, beschädigte Downloads, Vorprüfungsfehler, laufende Worker und
Wiederherstellung von Code, Einstellungen, Termin und Budget. Die echten
Audio- und API-Prüfungen laufen zusätzlich mit den vorhandenen Backendtests
in .github/workflows/raspberry-v082-language-validate.yml.

Neun weitere SQLite-/HTML-/API-Tests prüfen die Serien- und Folgenpagination,
numerische Reihenfolge, Gruppierung aller Abschnitte derselben Folge,
gleichnamige Quellen, Filter, erhaltenen Bearbeitungskontext, gruppierte
Analyseergebnisse, HTML-Escaping und die Darstellung von Filmen.

Zwölf zusätzliche SQLite-Tests prüfen die Konsolidierung, Erhaltung menschlicher
Entscheidungen, einmalige Nachprüfung vorhandener hoher Treffer, deaktivierte
Playlists, Tagesbudget und das Verbot maschineller Selbstbestätigung. Die
Audio-/API-Tests prüfen außerdem die Freigabe mit einer Referenz, unbestätigte
Grenzen, wiederkehrende kurze Motive und die Archivierung nach manueller Prüfung.

16 weitere HTTP-/SQLite-Tests prüfen originale HTTP-Statuscodes hinter dem Relay,
fehlende Zeitmarken, TMDB-Zuordnung, ungültige Schlüssel, dienstweite Zugriffspausen,
Tageslimits, Retry-After, sichere Meldungen, Wiedergabevorrang und Nachprüfungen ohne
Videodownload. Der Installer prüft zusätzlich die Vormerkung alter Online-Fehler.
20 weitere SQLite-/API-Tests prüfen beide bevorzugten Sprachen, die vom Nutzer
genannten Kategorien, eine ausdrücklich andere Audiosprache, unbekannte
Sprachen, Metadatenaktualisierungen ohne erneute Audioanalyse, bestehende
Warteschlangen, mehrere Playlists, den einmaligen Kategorienabgleich und die
Erhaltung von Cursor, Nachttermin, Budget und menschlichen Entscheidungen.
Der Installer prüft zusätzlich die Migration der Sprachzuordnung und das
optionale Warten auf einen laufenden Worker einschließlich eines Zeitlimits.
17 zusätzliche SQLite-/HTML-/API-Tests prüfen Serien-/Staffelfreigaben über alle
Seiten, Spezialfolgen, getrennte Quellen und Dateifassungen, Duplikate,
Widersprüche, bestehende Entscheidungen, Sitzungsprüfung, erneute Klicks und
atomare Wiederherstellung bei Fehlern. Der Installer prüft außerdem, dass der
neu gestartete Server die Sammelfreigabe unterstützt.
Der vollständige Prüflauf umfasst 215 Tests ohne übersprungene Tests sowie den
bestehenden Dashboard-/Geräte-Smoke-Test.

Validierter Installer-Commit: `cfc403b54d35b3f851c9af165a556de0b547d708`.
[GitHub-Actions-Prüflauf](https://github.com/epimediahub/EpiMediaHub/actions/runs/36991521155).
