# Automatische Zeitmarken und Serienfortschritt für Raspberry 0.8.2

Der vorhandene Worker erfasst den vollständigen Serienbestand der aktivierten
XTREAM-Playlists, auch ohne vorheriges Abspielen. Neue oder vom Anbieter als
geändert gemeldete Folgen werden in die bestehende Audioanalyse eingeplant.
Unveränderte, bereits bearbeitete Dateien werden beim Katalogabgleich nicht
erneut eingeplant. Ein Katalogfund allein gibt keine Zeitmarke frei.

## Installation

Voraussetzung ist der laufende Raspberry-Server 0.8.2 mit Audioanalyse und
Staffelautomatik für die gewünschten Playlists. Android 1.0.16 und 1.0.17 bleiben kompatibel.

```sh
curl -fsSL https://raw.githubusercontent.com/epimediahub/EpiMediaHub/dcb0254c5daac9c0392c58e0e214309018e03c37/server/epimediahub_provisioning/deploy/install_skip_catalogue.sh -o /var/tmp/epimediahub-skip-catalogue.sh &&
sudo bash /var/tmp/epimediahub-skip-catalogue.sh --wait-worker --start-catalogue
```

Der Aufruf aktualisiert den vorhandenen Dienst und startet beziehungsweise setzt
die Bestandsaufnahme fort. Nachttermine, bestehende Cursor und das Tagesbudget
bleiben erhalten. Ohne `--start-catalogue` werden die Katalogeinstellungen
unverändert gelassen.
Der Schalter startet ausschließlich bereits aktivierte Automatik-Playlists
mit erlaubter Audioanalyse und aktivem Kunden. TMDB-Schlüssel,
Anbieterkonfiguration, Geräte und menschliche Zeitmarken bleiben erhalten.

`--wait-worker` wartet bei einer laufenden Analyse bis zu 15 Minuten auf den
vorhandenen Worker-Lock, ohne den Durchlauf abzubrechen. Der Timer muss dafür
nicht manuell gestoppt werden. Ohne diese Option endet der Installer bei einem
belegten Lock weiterhin vor Änderungen. Beide Optionen sind kombinierbar.

Das Skript lädt 26 Dateien aus einem festen Commit und prüft SHA256,
Syntax sowie die tatsächlichen Richtlinien-, API- und Audiotests vor Änderungen.
Es verwendet den bestehenden Worker-Lock, sichert Code und SQLite-Datenbank
und stellt bei einem fehlgeschlagenen Neustart den vorherigen Code sowie nur
die selbst geänderten Katalogeinstellungen wieder her. Vor dem Neustart wird die
Serienstatistik einmalig vorbereitet und die Intro-Maske mit einer
schreibgeschützten Kopie des vorhandenen Datenbestands vollständig gerendert;
ein erfolgreicher Health-Aufruf allein reicht nicht aus. Am Ende zeigt der
Installer getrennte Zeiten für Datenbankkopie, Aktualisierung geänderter Serien
und Rendern der Intro-Maske.

## Reparatur bei „database is locked“

Wenn die Intro-Maske einen internen Serverfehler zeigt und das Protokoll
`sqlite3.OperationalError: database is locked` meldet:

```sh
curl -fsSL https://raw.githubusercontent.com/epimediahub/EpiMediaHub/dcb0254c5daac9c0392c58e0e214309018e03c37/server/epimediahub_provisioning/deploy/install_skip_catalogue.sh -o /var/tmp/epimediahub-skip-catalogue.sh &&
sudo bash /var/tmp/epimediahub-skip-catalogue.sh --repair-database --start-catalogue
```

Der Reparaturmodus funktioniert auch bei einem nicht antwortenden Health-Endpunkt,
sofern die vorhandene Intro-API lokal als 0.8.2 erkennbar ist. Downloads,
Prüfsummen und Tests laufen vor Änderungen. Anschließend hält der Installer
Analyse und Webdienst geordnet an, erwirbt den Worker-Lock und sichert den
Datenbestand. Abgebrochene laufende Jobs werden ohne zusätzlichen Versuch oder
Rücksetzen des Tagesbudgets erneut eingeplant. Der Webdienst und ein zuvor
aktiver Analyse-Timer starten danach wieder; `--start-catalogue` aktiviert den
Timer auch dann, wenn er zuvor inaktiv war.

SQLite verwendet anschließend WAL. Leser der Übersicht verhindern damit keine
Schreib-Commits der Wiedergabemeldungen. Alle Web- und Worker-Verbindungen werden
beim Verlassen ihres Kontexts zuverlässig geschlossen, auch nach Fehlern. Ein
zusätzlicher Index findet Katalogeinträge anhand der konkreten Datei; vorher
wurde für jede Folge erneut die Playlist durchsucht. Bei 6.001 Folgen reduzierte
sich diese Abfrage im lokalen Vergleich von 1,867 auf 0,018 Sekunden. Die Laufzeit
auf dem jeweiligen Raspberry wurde nicht gemessen.

Der Worker erwirbt seinen Lock bereits vor dem Import der Anwendung, sodass
auch die dabei ausgeführten Migrationen gegen parallele Worker und Installation
geschützt sind. Korrekturen, Kunden, Geräte, Anbieterzugänge, TMDB-Schlüssel und
bereits gespeicherte Marken bleiben erhalten. Die Sicherung ersetzt niemals
pauschal die aktive Datenbank.

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

Bei einem Verbindungsfehler versucht der Netzwerkzugriff weitere validierte
öffentliche IP-Adressen desselben Hosts. IPv4 wird zuerst verwendet, IPv6 bleibt
als Alternative und für reine IPv6-Ziele unterstützt. Alle Verbindungsversuche
teilen sich ein Zeitbudget von höchstens fünf Sekunden; für weitere Adressen
bleibt auch nach einem TCP-Timeout Zeit. Hostname, TLS-Prüfung und die Ablehnung
privater oder gemischter DNS-Antworten bleiben erhalten. Das gilt für TMDB,
TheIntroDB und Anbieterabrufe. Fehler anderer Art werden weiterhin getrennt
angezeigt; der Code kann eine vollständig fehlende Internetroute nicht ersetzen.

Alte Einträge mit der pauschalen Meldung „Online-Datenbank derzeit nicht erreichbar“
werden einmal erneut zur Prüfung vorgemerkt. Der Worker prüft im Leerlauf höchstens
eine solche Folge je Aufruf und höchstens 96 Folgen pro UTC-Tag. Auch vorübergehende
Fehler werden nach ihrer Wartezeit erneut geprüft. Diese Nachprüfungen rufen nur
Metadaten ab, laden keine Videodatei und wiederholen keine Audioanalyse. Sie laufen
auch nach Ausschöpfen des Audiolimits, erhalten dessen Zähler und alle Audiojobs.
Gemeldete Wiedergabe, ausgeschaltete Analyse sowie menschliche Entscheidungen
bleiben vorrangig. Gefundene Online-Zeiten werden im automatischen Modus direkt freigegeben.

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

„Serienfortschritt“ zeigt alle erfassten Serien, unabhängig von den letzten
Analyseprotokollen. Pro Serie stehen analysierte Videofassungen, vorhandene
Intros, offene Folgen, Zugriffsfehler und fehlende Referenzen. Die Fortschrittszahl
beschreibt die Analyse; „100 % analysiert“ bedeutet nicht automatisch „alle Intros
gefunden“. Bereits analysierte Folgen ohne nutzbares Intro stehen separat.

Filter zeigen abgeschlossene Analysen, Serien mit Intros, Serien mit fehlenden
Intros und noch offene Analysen. Die Suche durchsucht Titel und Playlistnamen.
20 Serien pro Seite machen den ganzen erfassten Bestand zugänglich. Getrennte
Quellen bleiben getrennt, und mehrere Fassungen einer Folge werden mitgezählt.
Noch nicht vollständig erfasste Folgenlisten und das verbrauchte Tagesbudget
werden angezeigt. Während der Bestandsaufnahme wächst die Übersicht.

Die Fortschrittszahlen werden je Serie gespeichert. Ein Seitenwechsel oder
Filter liest diese Statistik, statt sämtliche Folgen und Intro-Marken erneut
zu durchsuchen. Änderungen an Dateien, Analysejobs, Marken und Katalogständen
markieren nur die betroffenen Serien zur Neuberechnung. Das gilt auch für
Änderungen aus einem anderen Web- oder Worker-Prozess. Kunden- und Playlistnamen,
Analyseeinstellungen sowie Tagesbudget werden weiterhin aktuell gelesen.

Dashboard und Worker aktualisieren jeweils eine begrenzte Zahl geänderter
Serien. Bei einem größeren Rückstand zeigt die Übersicht die noch zu
aktualisierende Zahl an. Die gerade ausgewählte Serie wird bevorzugt, damit
Freigaben und Korrekturen beim anschließenden Öffnen sichtbar werden. Eine
während der Berechnung geänderte Serie bleibt zur erneuten Aktualisierung
vorgemerkt; auch zwischenzeitliches Aktualisieren und erneutes Ändern können
keine veralteten Zahlen veröffentlichen. Bestehende Bestände werden bei der
Installation vor dem Neustart vollständig vorbereitet.

Im lokalen Vergleich mit 60.001 Dateien, 180.001 freigegebenen Intro-Marken und
2.001 Seriengruppen sank die Fortschrittsberechnung von 0,616 auf 0,0127 Sekunden
(rund 48-mal schneller). Die einmalige Vorbereitung brauchte 0,288 Sekunden.
Dies sind Messungen derselben lokalen Testdatenbank, keine Laufzeitgarantie für
einen Raspberry oder für das gesamte Dashboard. Die übrigen Dashboard-Abfragen
und die Datenbankkopie werden durch diesen Vergleich nicht gemessen.

Zur Messung mit dem vorhandenen Raspberry-Datenbestand:

```sh
sudo bash -c 'time timeout 60s /opt/epimediahub/provisioning/.venv/bin/python /opt/epimediahub/provisioning/deploy/check_skip_dashboard.py /var/lib/epimediahub/provisioning.db /opt/epimediahub/provisioning/templates'
```

Die drei ausgegebenen Phasenzeiten trennen Kopieren, Statistikaktualisierung
und Rendern. Der Prüfer verändert weder die aktive Datenbank noch
Authentifizierung oder Dienstkonfiguration. Eventuell noch offene Statistik
wird ausschließlich in seiner privaten Datenbankkopie vorbereitet. Die
Passworteingabe für `sudo` liegt außerhalb der hier gemessenen Laufzeit.


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

Die Aktion entspricht einer menschlichen Freigabe der aktuellen Auswahl.
Pro Datei, Laufzeit und Abschnittsart wird die stärkste gültige Variante gewählt;
auch abweichende Zeiten werden aufgelöst. Andere Vorschläge werden nach „Ersetzt“
archiviert. Bereits bestehende menschliche Korrekturen und Ablehnungen haben
Vorrang; veraltete offene Alternativen werden dabei ebenfalls erledigt. Eine
ausdrückliche offene Player-Korrektur kann eine vorherige maschinelle Freigabe
ersetzen. Unterschiedliche Videofassungen behalten eigene Zeitmarken.

Das Ergebnis zeigt die Zahl freigegebener und zusammengeführter Marken sowie
erhaltene Entscheidungen. Nach einer Freigabe öffnet sich „Freigegeben“ und die
Erfolgsmeldung steht direkt im sichtbaren Bereich. Ungültige Zeitbereiche werden
nicht veröffentlicht. Ein Klick schaltet die zukünftige Automatik nicht um.

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

## Automatische Freigabe und spätere Korrekturen

Die automatische Übernahme ist standardmäßig für aktive Analyse-Playlists
aktiviert. Erkannte Zeitmarken aus Audioanalyse, Videokapiteln, TheIntroDB und
wiederkehrendem Ton werden ohne weitere Bestätigung freigegeben. Beim ersten
Update werden auch vorhandene maschinelle Vorschläge übernommen. Die Zeiten
müssen gültig sein und zur registrierten Datei, Laufzeit, Staffel und Folge passen.
Eine fehlende Zeitmarke wird nicht durch eine erfundene Standardzeit ersetzt.

Unter „Audioanalyse pro Playlist“ kann „Erkannte Zeitmarken automatisch freigeben“
ausgeschaltet werden. Dann bleiben neue Vorschläge zur Prüfung und die bisherige
strenge Regel für hohe, eindeutige Audiotreffer bleibt verfügbar. Das Speichern
unveränderter Automatik-Einstellungen plant erledigte Folgen nicht erneut ein.

Im automatischen Modus werden Player-Korrekturen einer zugeordneten, aktiven
Playlist direkt freigegeben. Änderungen, Ablehnungen und deaktivierte Abschnitte
bleiben gegenüber der Erkennung vorrangig. Noch offene eigene Vorschläge werden
nicht von maschinellen Ergebnissen verdrängt. „Freigegeben“ im Dashboard erlaubt
weiterhin das Ändern oder Zurückziehen einer Zeitmarke. Ergebnisse aus einer
während der Analyse korrigierten Referenz werden verworfen.

Für die erste Referenz ist keine menschliche Bestätigung erforderlich:
Videokapitel, Online-Zeiten und wiederkehrender Ton aus mindestens drei Folgen
können den Einstieg liefern. Rein übertragene Audio-Zeiten werden nicht als neue
unabhängige Referenz weitergereicht. Die Quelle bleibt an die konkrete Datei
gebunden. Nur vollständig gelesene und kürzlich geprüfte Audio-Fingerabdrücke
werden bis zu einer Stunde wiederverwendet. Korrekturen löschen diesen Cache.
Ältere oder ungeprüfte Fingerabdrücke werden erneut an der Datei kontrolliert.
Erledigte Folgen werden durch eine Freigabe nicht erneut eingeplant; wartende
Folgen derselben Staffel können die neue Referenz anschließend verwenden.

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

Der vollständige Prüflauf umfasst 273 Tests ohne übersprungene Tests:
233 Richtlinien-, Katalog-, HTTP-, Sprach-, Freigabe- und Fortschrittstests,
14 Marker-/API-Tests einschließlich echter FFmpeg-/Chromaprint-Erkennung sowie
26 Installer-Tests. Zusätzlich läuft der bestehende Dashboard-/Geräte-Smoke-Test.
Die neuen Fälle prüfen die automatische Übernahme bestehender Vorschläge,
Referenzen ohne menschliche Erstfreigabe, Korrekturen im Player, geschützte
Ablehnungen, die Sammelfreigabe bei abweichenden Zeiten, vollständige Serienseiten,
fehlende Intros trotz abgeschlossener Analyse und Wiederherstellung des Codes
bei fehlenden neuen Health-Funktionen. Neue Regressionen prüfen echte parallele
Wiedergabemeldungen und Dashboard-Aufrufe bei einer offenen Lesetransaktion,
6.001 Folgen mit begrenztem SQLite-Rechenaufwand, geschlossene Verbindungen nach
Commit/Rollback, einen gesperrten Worker vor dem Anwendungsimport und die
Reparatur bei aktiver Schreibsperre beziehungsweise ausgefallenem Health-Endpunkt.
Ein Fehler beim tatsächlichen Rendern der Intro-Maske löst ebenfalls die
Wiederherstellung aus.

Zwölf zusätzliche Fortschrittstests prüfen gespeicherte Seiten ohne Zugriff auf
den Folgen-/Markenbestand, Statuswechsel, Freigaben, Korrekturen, Laufzeit- und
Quellenänderungen, unveränderte Player-Registrierung, Katalogänderungen,
Playlistlöschung, begrenzte Aktualisierung, gleichzeitige Änderungen einschließlich
zwischenzeitlicher Bereinigung sowie die getrennten Prüferzeiten ohne Änderungen
an der aktiven Datenbank. Zwei weitere Installer-Tests prüfen die vollständig
vorbereitete Statistik vor dem Neustart und Wiederherstellung bei fehlendem
Health-Merkmal `skip_progress_cache`.

Quellcommit: `990533bf76b727ccc9ff6706909adad6e53dbcac`.
Validierter Installer-Commit: `dcb0254c5daac9c0392c58e0e214309018e03c37`.
[GitHub-Actions-Prüflauf](https://github.com/epimediahub/EpiMediaHub/actions/runs/37045686053).
Workflow: `.github/workflows/raspberry-v082-automatic-validate.yml`.
