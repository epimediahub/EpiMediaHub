# EpiMediaHub 1.0.52 – Speedtest-Kalibrierung

Diagnose: 1-Stream-Pilot unterschätzt 4-Stream-Bandbreite; dadurch wird der begrenzte Haupttest bei schnellen Verbindungen zu kurz. Die neue Testmenge wird anhand von **echten** 1- und 2-Stream-Messungen dimensioniert (Kalkulationsfaktor 1,8 für parallele Last, niemals für Ergebniswerte).

Anzeige: vollständiger Download-Durchschnitt und **über mindestens 1 Sekunde nach 750 ms Anlaufphase** gemessener Netto-Durchsatz werden getrennt ausgegeben. Ist der Test zu kurz, wird kein Dauerwert erfunden. Peak/Stabilität und Testanbieter bleiben sichtbar. Wetter/Standort, VPN-Routing und Schlüssel werden nicht verändert.

Freigabe nur nach gleichem SHA für Quelltextprüfung, signierten APK-Build, Gradle-Tests, Fernbedienungs-/Wetterregression und Messung auf realem Fire TV. Keine automatische Veröffentlichung ohne verifizierte Artefakte.