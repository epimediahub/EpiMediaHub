# EpiScene — Audio- und Bildanalyse für Intro und Abspann

EpiScene ergänzt die bestehende Audioerkennung durch zeitlich geordnete Bildfingerabdrücke. Der Raspberry verwaltet weiterhin Dashboard, Warteschlange, Markierungen und Anbieterzugang. Hetzner übernimmt Videodekodierung und Bildvergleiche über die vorhandene private WireGuard-Verbindung. Die App benötigt dafür kein neues APK: Sie erhält weiterhin die freigegebenen Zeitmarken über dieselbe API.

## Erkennung

- Audio liefert mögliche Zeitbereiche; erfolgreiche Staffelvergleiche liefern ebenfalls einen Suchbereich für spätere Folgen.
- In diesen Bereichen werden zentral zugeschnittene, kleine Graubilder mit zwei Bildern pro Sekunde ausgewertet. Pro Bild werden zwei Struktur-Fingerabdrücke, Kontrast und Helligkeit gespeichert.
- Wenn Audio keinen brauchbaren Treffer liefert, beginnt EpiScene mit den ersten beziehungsweise letzten drei Minuten. Sobald eine unabhängige Vergleichsfolge vorliegt, wird nur bei fehlendem Treffer schrittweise bis auf zwölf Minuten erweitert. Eine zu kurze Vergleichsfolge kann dabei mit erweitert werden. Auch noch ungeprüfte, eindeutige Bildtreffer liefern nur einen Suchbereich für die nächste Folge und zählen niemals als menschliche Bestätigung. Der Dateiabruf erfolgt nacheinander in höchstens 60 Sekunden langen Abschnitten. Bei Zeitbudget oder Wiedergabepause bleiben fertige Abschnitte für den nächsten Lauf erhalten.
- Eine menschlich bestätigte Referenz erlaubt einen eindeutigen visuellen Volltreffer. Ohne menschliche Referenz benötigt die automatische Freigabe dieselbe wechselnde Sequenz in der Ziel- und mindestens drei weiteren, unterschiedlich nummerierten Folgen. Mehrere Videofassungen derselben Folge zählen einmal.
- Gleichmäßige Schwarzbilder und statische Logos liefern keine Freigabe. Ohne menschliche Referenz sind mindestens sechs deutlich unterschiedliche Bildstrukturen erforderlich; kleine Gesichtsbewegungen vor demselben Hintergrund reichen nicht. Mehrere plausible Positionen im ausgewerteten Bereich, abgeschnittene Suchbereiche, widersprüchliche Grenzen oder ein klarer Widerspruch zum starken Audiotreffer bleiben zur Prüfung vorgemerkt.
- Die Zeitbasis liegt bei 500 Millisekunden. Das Ende wird zusätzlich konservativ um 250 Millisekunden nach innen gelegt; bei rein visuell gefundenen, unmarkierten Sequenzen liegt es vor dem letzten vollständig belegten Intervall. Das kann einen kurzen Introrest stehen lassen, vermeidet aber ein aggressives Überspringen folgenden Inhalts. Es ist keine bildgenaue Schnitt-Erkennung.
- Ein möglicher Nachspann nach den Credits wird nicht automatisch übersprungen. Automatische Rückblick-Erkennung ist in dieser ersten EpiScene-Version nicht enthalten; vorhandene und manuelle Rückblickmarken bleiben nutzbar.

## Cache und Veröffentlichung

Der SQLite-Cache umfasst höchstens 512 Ausschnitt-Fingerabdrücke mit einer Gültigkeit von einer Stunde. Der Hetzner-Prozess behält höchstens 128 Paarvergleiche. Pixel, Audio und Anbieterpasswörter werden nicht im Cache gespeichert. Schlüssel enthalten Dateiidentität, Laufzeit, Suchbereich, Zeitbasis und Analyseversion. Vergleichsschlüssel enthalten zusätzlich die Fingerabdruckdaten und aktuelle Referenzgrenzen.

Vor automatischer Veröffentlichung werden aktive Anbieterfreigaben, aktuelle Laufzeiten, individuelle Folgen, unveränderte Cacheinhalte und menschliche Referenzmarkierungen erneut geprüft. Manuelle Korrekturen, abgelehnte Marken und deaktivierte Abschnitte bleiben maßgeblich. Wenn Bilder nicht ausgewertet werden können, bleiben neue Vorschläge zur Prüfung; alte freigegebene Marker werden nicht zurückgezogen.

Bekannte zusätzliche Videoabschnitte können die erste Analyse verlängern. Wiederverwendung von Referenzen und kurzen Suchbereichen spart spätere Arbeit. Reale Genauigkeit und Durchsatz müssen an den tatsächlichen Serien auf Hetzner gemessen werden; die Tests erzeugen eigene Videos mit bekannten Zeitbereichen, anderem Ton, veränderter Helligkeit und anderer Kompression.

## Bestehende Installation aktualisieren

Voraussetzung ist die bestehende private Hetzner-Verbindung mit dem bereits optimierten Dashboard. Das Update ändert weder WireGuard-Schlüssel noch die installierten Ressourcenlimits. Reihenfolge: **Raspberry vorbereiten → Hetzner aktualisieren → Raspberry aktivieren**. Alle drei Schritte verwenden denselben vollständigen Commit. Das Dashboard bleibt während der Vorbereitung verfügbar.

Auf dem Raspberry:

```bash
COMMIT=EPISCENE_RELEASE_COMMIT
curl -fsSL "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$COMMIT/server/epimediahub_provisioning/deploy/install_skip_scene.sh" -o /tmp/epimediahub-episcene.sh && sudo bash /tmp/epimediahub-episcene.sh prepare "$COMMIT"
```

Auf Hetzner:

```bash
COMMIT=EPISCENE_RELEASE_COMMIT
curl -fsSL "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$COMMIT/server/epimediahub_provisioning/deploy/install_skip_scene.sh" -o /tmp/epimediahub-episcene.sh && sudo bash /tmp/epimediahub-episcene.sh compute "$COMMIT"
```

Anschließend auf dem Raspberry:

```bash
sudo bash /tmp/epimediahub-episcene.sh control EPISCENE_RELEASE_COMMIT
```

Vor der Aktivierung prüft das Skript einen tatsächlichen visuellen Vergleich über die private Verbindung. Es sichert die Datenbank und den bisherigen Code. Bei einem Fehler wird der Code zurückgenommen; die Kundendatenbank wird niemals durch ein altes Backup überschrieben. Ein fehlgeschlagenes Aktivieren lässt die Analyse bis zu passenden Versionen auf beiden Geräten pausiert. Die vorherigen Timerzustände werden bei erfolgreichem Aktivieren erhalten.

Nur beim ersten Aktivieren werden bisher erfolglose Introaufträge (`no_match`/`no_reference`) aus aktiven Automatik-Playlists erneut eingeplant, sofern keine ausdrückliche menschliche Entscheidung entgegensteht. Tagesbudget und bisheriger Verbrauch bleiben erhalten. Die Sprachreihenfolge bleibt Deutsch/Italienisch → Türkisch → übrige Sprachen; Referenzen und gestartete Serien behalten ihren Vorrang.

## Validierung

```bash
python -m unittest discover -s server/epimediahub_provisioning/tests -p 'test_skip_analysis_episcene.py' -v
python -m unittest discover -s server/epimediahub_provisioning/tests -p 'test_skip_remote_episcene.py' -v
python -m unittest discover -s server/epimediahub_provisioning/tests -p 'test_skip_remote_scene_installer.py' -v
```

Die reguläre GitHub-Prüfung führt außerdem die gesamte bestehende Analyse-, API-, Queue- und Installerprüfung mit Python 3.11 und 3.13 sowie einen tatsächlichen verschlüsselten WireGuard-Vergleich aus.
