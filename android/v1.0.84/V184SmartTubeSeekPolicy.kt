package de.epimediahub.app.ui

/** Short D-pad click 10 s; held key, repeated by Android, 30 s per key-repeat. */
internal object V184SmartTubeSeekPolicy {
    fun deltaMs(direction: Int, repeatCount: Int): Long {
        require(direction == -1 || direction == 1)
        return direction * if (repeatCount > 0) 30_000L else 10_000L
    }
}
