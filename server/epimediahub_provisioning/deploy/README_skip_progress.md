# Intro-Erkennung: kürzere Warteschlange und App-Unterstützung

Der Stand baut auf der bereits eingebundenen Policy `chromaprint_fft_v3_1` auf. V3.1 wird nicht erneut als neues Verfahren angekündigt. Das bisher im Installer eingebettete Modul liegt jetzt auch als normale Quelldatei vor.

- Der Timer verarbeitet bis zu vier unterschiedliche Jobs nacheinander. Eine weiterhin aktive Wiedergabe lässt den betroffenen Job unverbraucht in der Queue; derselbe Job wird innerhalb einer Gruppe nicht erneut ausgewählt. Das gemeinsame Zeitbudget wird auch während der Audio-/Proxyarbeit geprüft: bei Ablauf bleibt der Job ohne verbrauchten Versuch in der Queue, vollständige Fenster bleiben gespeichert. Es entstehen keine parallelen Anbieter-Verbindungen.
- Zwischen Gruppen werden 30 Sekunden statt zwei Minuten gewartet. Der Tageszähler und die strenge Reihenfolge Deutsch/Italienisch bleiben erhalten. Fehler werden weiterhin im vorhandenen Verkehrsbudget gezählt.
- Vollständige, höchstens eine Stunde alte Anfangs-/Endfenster werden nach erneuter Laufzeitprüfung wiederverwendet. Unvollständige, beschädigte und abweichende Fenster werden neu gelesen. Dies spart erneute Audioextraktion; es garantiert keine bestimmte Erkennungsdauer.
- App 1.0.25 meldet den Abschluss einer Player-Sitzung mit `active=false`. Die Sitzung ist mit einer ID an Gerät und Playlist gebunden. Ein verspätetes Ende der vorherigen Folge darf eine neue Wiedergabe nicht freigeben. Bei Absturz/offline bleibt das bisherige 70-Sekunden-Ablaufverfahren wirksam.
- Die App lädt zentrale, freigegebene Marker während der Wiedergabe alle 30 Sekunden nach. Es werden dabei keine weiteren Anbieter-Streams geöffnet. Die schwere Erkennung bleibt auf dem Server.

`install_skip_progress.sh` lädt und prüft die Dateien vor dem Wechsel, wartet auf den aktiven Worker, sichert die Datenbank konsistent und stellt bei Fehlern Code und Systemd-Dropins wieder her. Es ersetzt weder `app.py` noch den Lizenz-/Credit-Backend. Vorhandene CPU-/RAM-Begrenzungen werden nicht erhöht.

Die tatsächlichen Anfangs- und Endfenster im bisherigen Worker sind **jeweils bis zu zwölf Minuten**, zusammen bis zu 24 Minuten decodiertes Audio pro Folge. Netzwerkbytes hängen vom Container, Seek-/Range-Unterstützung und den Anbieterantworten ab. Das ist kein Download von nur zwölf Minuten Audio insgesamt und kein festes Array von 23 KB für beide Fenster.

Native Chromaprint-Erfassung am PCM-Pfad der Android-App ist ein weiterer Ausbau und in 1.0.25 nicht enthalten. Er benötigt Tests für Zeitbasis, Suchsprünge, Sprachwechsel, die Audioausgabe und die CPU-Belastung der TV-Geräte. Eine Live-Diagnose des Raspberry wurde durch die Codeprüfung nicht ersetzt.
