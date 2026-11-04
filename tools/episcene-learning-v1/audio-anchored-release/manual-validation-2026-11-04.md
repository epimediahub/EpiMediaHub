# EpiScene – Rückmeldung zur manuellen Wiedergabeprüfung (04.11.2026)

## Ergebnis
Der Nutzer hat die folgenden drei **Zeitmarkierungen in den Hauptplaylists** persönlich anhand der Wiedergabe überprüft und ausdrücklich alle drei als „Punktlandungen“ bestätigt.

| Hauptplaylist | Serie | Episode | Segment | Start | Ende | Ergebnis |
| --- | --- | --- | --- | --- | --- | --- |
| 4K IPTV | Navy CIS | S13 E4 | Intro | 02:13 | 02:41 | Nutzer bestätigt |
| 4K IPTV | Navy CIS | S13 E9 | Outro | 41:23 | 41:52 | Nutzer bestätigt |
| IPTV THE BEST | One Piece | E895 (Analyse: S20) | Intro | 00:00 | 01:57 | Nutzer bestätigt |

Die entsprechenden Fingerprint-Shadow-Kandidaten wurden zuvor in den internen Analyse-Playlists `4K ANALYSE` bzw. `THE BEST` ermittelt. **Nach ausdrücklicher Bestätigung des Nutzers sind die internen Analyse-Playlists inhaltlich identisch mit den jeweiligen Hauptplaylists** (`4K ANALYSE` ↔ `4K IPTV`, `THE BEST` ↔ `IPTV THE BEST`). Daher ist **keine erneute Wiedergabeprüfung derselben drei Episoden** erforderlich. Die automatisierte Datenbankprüfung hat noch keine eindeutige *technische Asset-Zuordnung* geliefert; das ist eine Integrationsaufgabe und kein Anlass, das Nutzerfeedback zu verwerfen. Die Zeitgrenzen sind kein Freibrief für andere Schnitte oder Anbieter.

## Evidenztrennung

- **Belegt:** Diese drei bei der Wiedergabe beobachteten Marker sind korrekt (Nutzerfeedback).
- **Belegt:** Die vorangegangenen isolierten Shadow-Läufe fanden übereinstimmende Audio-Fingerprints über unterschiedliche Episoden und hatten 12 Negativkontrollen in 4K ANALYSE ohne gemeldeten Cross-Series-Treffer.
- **Nicht belegt:** Generelle Präzision/Fehlerrate, exakte Grenzen weiterer Folgen, Bestätigung der sechs übrigen starken V4-Kandidaten oder ausreichende Kontrollen in THE BEST.
- **Nicht erfolgt:** Kein manuelles `approved` im Server, keine Änderung an `skip_records`, `skip_auto_evidence`, `skip_auto_blocks`, Worker-Versionen oder Freigabe-Gates.

## Sichere nächste Schritte

1. Die ausdrückliche Nutzerbestätigung der inhaltlich gleichen Haupt- und Analyse-Playlists als bereits erledigte manuelle Prüfung der drei benannten Episoden behandeln. **Nicht nochmals zur Wiedergabeprüfung auffordern.** Für den Eintrag in die richtige technische Analyse-Asset-ID vorhandene Quell-/Folgenreferenzen abgleichen und Unsicherheit bei abweichenden Datenbank-Laufzeiten nachvollziehbar markieren.
2. Erst nach eindeutiger Zuordnung eine verifizierte manuelle Referenz in der bestehenden Freigabe-Architektur übernehmen; niemals Titelgleichheit allein als Beweis für andere Anbieter/Versionen verwenden. Pro Folge gelten die bisherigen Sperr- und Korrekturregeln.
3. Mit diesen Referenzen die vier übrigen Navy-CIS-Outros sowie One-Piece-Intros isoliert nachtesten, inklusive vollständiger Start-/Ende-Prüfung und fremder Negativkontrollen.
4. Keine automatische Freigabe, bevor der bestehende Server-`skip_release.py`-Pfad / Worker-Versionen geprüft, ein Rollback vorbereitet und der Patch vollständig getestet sind. Danach **ein gebündelter Versionsabgleich**.

Dieser Report ist Dokumentation einer Nutzerbeobachtung, **keine technische Release-Freigabe**.
