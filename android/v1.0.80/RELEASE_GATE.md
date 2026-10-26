# EpiMediaHub Android v1.0.80 – verbindliches Release-Gate (24.10.2026)

Der Nutzer will **keine separate Testversion** und **keine öffentliche Aktualisierung**, bevor sämtliche Anforderungen erfüllt und überprüft sind. Deshalb ist der GitHub-Actions-Workflow für reguläre Builds QA-only. Der bestehende In-App-Updater bleibt auf v1.0.78.

## Freigabe erst nach vollständiger Prüfung
- Das zuvor besprochene 34-Sekunden-EpiScene-Kinointro wird mit dem **echten App-Logo**, nicht mit einem Konzeptlogo oder generischem Text, beendet; der finale Video-Hash stimmt mit der freigegebenen Datei überein.
- Klar verständliche EpiScene-Erklärung, weniger Fokus auf gewöhnliche Live-TV/Filme/Serien-Funktionen, eigener VPN-Abschnitt.
- Musik/Herzschläge hörbar, synchron und auf **Fire TV sowie GalaBox** ruckelfrei (inkl. A/V-Sync) geprüft.
- SmartTube im Player: adaptive Bildqualität und echter Creator-Kanal über MediaServiceCore, einschließlich Fernbedienungsnavigation / Zurück, real getestet.
- GalaBox-/Player-Korrekturen (inklusive vom Nutzer genannter roter Statusschrift oben links) tatsächlich überprüft.
- Unveränderte Kundenplaylist-Zugänge, EpiScene, VPN-Routing, Lizenzierung und Fire-TV-Bildwiederholrate.
- Signierte APKs für alle Architekturen, Zertifikat, versionCode=1080, Dateinamen und monotones Updater-Manifest verifiziert.

Alle erforderlichen Prüfungen mit verifizierbaren Nachweisen in `RELEASE_GATE.json` dokumentieren. Standardmäßig sind **alle Checks false**, alle Prüfnachweise leer und release_approved=false. Nur nach erfüllten Checks, überprüfter Original-Logo-Quelle und explizit manuellem Workflow-Dispatch mit `release_to_customers=true` darf die Veröffentlichung beginnen. Ein reiner Git-Push, ein CI-Green oder der bloße Upload einer Videodatei veröffentlicht **nichts**.
