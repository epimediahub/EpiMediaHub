package de.epimediahub.app.ui

/** Only decorative, fully bracketed provider headings, not watchable channels. */
internal object V191LiveHeaders {
    private fun marker(char: Char): Boolean = char == '-' || char == '=' ||
        char == '_' || char == '*'

    fun isNonPlayableName(name: String): Boolean {
        val value = name.trim()
        val leading = value.takeWhile(::marker).length
        val trailing = value.takeLastWhile(::marker).length
        return leading >= 3 && trailing >= 3 &&
            value.length - leading - trailing >= 3
    }
}
