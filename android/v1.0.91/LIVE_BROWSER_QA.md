# EpiMediaHub 1.0.91 – Live-TV-Stabilität (nur signierter QA-Build)

## Anlass
Fire TV Stick 4K: 1.0.90 blockiert nach mehreren Live-Senderwechseln die
Fernbedienung; der sichtbare Live-Browser aus dem Video vom 27.10. zeigt
zwischenzeitlich einen kompletten Katalog-Ladebildschirm und anbieterseitige
`--- KATEGORIE ---`-Platzhalter als auswählbare Sender.

## Änderungen gegenüber dem erfolgreichen 1.0.88-Sportmodus-Baseline-Build
- Kein erzwungener HDMI-Moduswechsel während Live-TV (Cinema VOD bleibt getrennt).
- Die v188-Sport-Erkennung (weltweite Sendernamen, EPG optional, PTS-basiert
  bestätigte 50-FPS-Varianten, alle geladenen Kategorien und nur derselbe
  Anbieter) bleibt erhalten.
- Sport-Gruppen einmal außerhalb des UI-Threads vorbereiten und per
  Stream-Identität nachschlagen, statt den ganzen Katalog bei jeder
  Compose-Neuberechnung erneut durchzugehen.
- Browser mit unverändertem aktuellem Katalog öffnen, ohne ihn bei jedem
  OK/Zurück erneut zu laden.
- Eindeutige Trennzeilen `--- ... ---` nur in der Live-Senderliste verstecken;
  echte Sender, Anbieter-Daten und Kindersicherung nicht löschen.
- Bereits in v113 implementierte Fokus-Erinnerung unverändert übernehmen.

## Vor Freigabe – Gerätetests
1. Auf dem Fire Stick 40-mal zügig durch Kategorien navigieren: Fokus bleibt
   steuerbar, ausgewählte Sender erhalten den Fokus, keine erneute Ladesperre.
2. 20-mal durch echte Live-Sender wechseln; OK, Zurück und Links/Rechts prüfen.
3. In DE/IT-Sportkategorien 25-FPS-Sender wählen: nur bekannte gemessene
   50-FPS-Alternativen derselben Playlist anbieten, kein automatischer Wechsel.
4. Bei einem Anbieter mit nur einem gleichzeitigen Zugang keine zweite
   Stream-Verbindung zur FPS-Prüfung öffnen.
5. Prüfen: Intro, SmartTube, Filme, Serien, EpiScene, VPN, Fire-TV-Lizenz,
   Playlisten und In-App-Updater unverändert.
6. Falls Freeze: ADB logcat + ANR traces erfassen, keine weitere öffentliche
   Freigabe ohne Ursachenanalyse.

## Einschränkung
Der Build korrigiert plausible CPU-/Focus-/Reload-Probleme aus dem Code.
Er ist kein Nachweis, dass die Freeze-Ursache auf dem Fire-TV vollständig
behoben ist. Keine automatische Kundenverteilung.
