package de.epimediahub.app.ui

internal object V111MenuMemory {
    private val indices = linkedMapOf<String, Int>()
    private val ids = linkedMapOf<String, String>()
    private val texts = linkedMapOf<String, String>()

    @Synchronized
    fun remember(key: String, index: Int, id: String = "") {
        indices[key] = index.coerceAtLeast(0)
        if (id.isNotBlank()) ids[key] = id
    }

    @Synchronized
    fun index(key: String): Int = indices[key] ?: 0

    @Synchronized
    fun id(key: String): String = ids[key].orEmpty()

    @Synchronized
    fun rememberText(key: String, value: String) {
        texts[key] = value
    }

    @Synchronized
    fun text(key: String): String = texts[key].orEmpty()
}
