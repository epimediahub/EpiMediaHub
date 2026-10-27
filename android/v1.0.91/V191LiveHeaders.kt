package de.epimediahub.app.ui

/** IPTV provider separator rows are catalogue headings, not watchable channels.
 * Only discard conspicuously wrapped markers; real stations remain untouched.
 */
internal object V191LiveHeaders {
    private val divider = Regex("""^[-=_*]{3,}\\s*\\S(?:.*\\S)?\\s*[-=_*]{3,}$""")

    fun isNonPlayableName(name: String): Boolean {
        val value = name.trim()
        return value.length >= 9 && divider.matches(value)
    }
}
