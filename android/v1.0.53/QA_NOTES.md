# EpiMediaHub 1.0.53 – Direkt-Playlist Regression

Problem: Bereits per Playlist auf DIREKT geschaltete Nutzer wurden nach dem Upgrade von der VPN-Zustandsprüfung blockiert, wenn der unabhängige Dienst api.ipify.org nicht erreichbar war. Dies konnte sowohl die Playlist-Auswahl als auch die Player-Oberfläche blockieren.

Korrektur: Nur der **explizite DIRECT-Modus** darf ohne externe IP-Prüfung starten, nachdem der eigene WireGuard-Tunnel tatsächlich beendet und die VPN-Prozessbindung freigegeben wurde. Der Nutzer muss dafür weder einen VPN-Zugang haben noch einen Drittanbieter-IP-Prüfdienst erreichen. VPN-Pflicht, aktive oder alte Prozessbindung und anhaltende VPN-Verluste bleiben gesperrt.

Sicherheit: Kein automatischer Fallback bei VPN-Playlists; kein Löschen von Keys, Registrierung, Playlist oder Profil. Der einmalige VPN-Fallback erfordert weiterhin eine ausdrückliche Nutzerbestätigung und getrennte IP-Prüfung. QA: Unit-Tests für den Direct-Policy-Guard, vollständige Android-Tests und offizielle Signatur.
