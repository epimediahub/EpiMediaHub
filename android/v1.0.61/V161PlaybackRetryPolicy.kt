package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaKind

/** Fail fast on provider access controls; bound VOD fallback attempts. */
internal object V161PlaybackRetryPolicy {
    fun providerBlocked(httpCode: Int?): Boolean =
        httpCode == 429 || httpCode == 401 || httpCode == 403

    fun shouldTryNext(kind: MediaKind, httpCode: Int?, next: Int, count: Int): Boolean {
        if (providerBlocked(httpCode) || next !in 0 until count) return false
        return kind == MediaKind.LIVE || next < 2
    }

    fun message(kind: MediaKind, httpCode: Int?, detail: String): String = when (httpCode) {
        429 -> "Der Anbieter begrenzt gerade die Anfragen (HTTP 429). Bitte etwas warten und erneut versuchen."
        401, 403 -> "Der Anbieter hat die Wiedergabe abgelehnt (HTTP " + httpCode + "). Bitte Playlist-Zugang prüfen."
        else -> if (kind == MediaKind.LIVE)
            "Sender konnte nicht gestartet werden. Letzter Fehler: " + detail + "."
        else "Film oder Folge konnte nicht gestartet werden. Letzter Fehler: " + detail + ". Bitte später erneut versuchen."
    }
}
