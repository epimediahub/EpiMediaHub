# EpiMediaHub Android v1.0.51 — Speedtest und Wetteranzeige

Basis: `feature/official-v150-adaptive-speed-focus-weather` (v1.0.50).

## Änderungen
- TV-Startseite: Wetter, Stadt und Temperatur wieder mittig über der Uhr. Das aufklappbare Schnellmenü bleibt darunter; die fehleranfällige zweite, rechts ausgerichtete TV-Anzeige wird entfernt.
- Wenn keine PLZ konfiguriert wurde oder keine frischen Wetterdaten ankommen, erscheint eine sichtbare Statusmeldung anstelle einer leeren Stelle. Da VPN-IP-Geolokalisierung falsche Orte anzeigen kann, bleibt die konfigurierte PLZ maßgeblich.
- Speedtest: Der Startzeitpunkt liegt unmittelbar vor Freigabe der Download-/Upload-Worker (nicht vor deren Einrichtung).
- Die Messdauer endet beim letzten empfangenen/gesendeten Nutzdatenbyte, nicht beim Abschluss von HTTP-Antwort und Sicherheitsüberprüfung. Fehlgeschlagene Downloads/Uploads und abweichendes VPN-Routing bleiben ungültig.
- Live-Tacho: gemessener gleitender Durchsatz statt ausschließlich kumulierter Geschwindigkeit. Im Ergebnis Durchschnitt, Spitzenwert und Stabilität unterscheiden.

## Einbau in einen rekonstruierten v1.0.50-Projektstand
```sh
PROJECT_ROOT=/pfad/zum/androidprojekt python3 android/v1.0.51/patch_v151.py
```
Das Skript bricht bei nicht passenden Quelltext-Ankern ab. Vorher die Projektkopie sichern; nicht direkt im produktiven Buildverzeichnis ohne Snapshot arbeiten.

## Vor Freigabe zu verifizieren
1. Kompilieren und alle Unit-/Compose-Tests ausführen, insbesondere `V150AdaptiveSpeedTest`, `V151RollingSpeedTest` und Home-Screen-Tests.
2. Fire TV 4K Max mit und ohne eingerichtete PLZ: Wetter/Ort bzw. Statusmeldung **mittig über der Uhr**, Schnellmenü bei geschlossener und geöffneter Ansicht ohne verdeckte Daten.
3. Testen mit 10, 50, 100 und mindestens 250 Mbit/s auf Direktverbindung sowie Finnland-VPN. Ergebnis ist Byte/Übertragungsdauer; Spitze darf vom Durchschnitt abweichen. Kein künstlicher Endwert und keine 0-Mbit/s-Meldung nach erfolgreichem Transfer.
4. Bewusst langsame letzte Parallelverbindung und verzögerte HTTP-Antwort testen; nur tatsächliche Nutzdatenübertragung messen. Messung bei Route-Wechsel/Abbruch unbedingt ungültig lassen.
5. Signierte APK und In-App-Update erst nach erfolgreichem CI-/Gerätetest bereitstellen. Dies ist **kein** veröffentlichter Release.
