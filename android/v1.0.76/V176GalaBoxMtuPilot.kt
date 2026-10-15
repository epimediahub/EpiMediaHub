package de.epimediahub.app.vpn

import android.content.Context
import android.os.Build

/**
 * Private, explicit GalaBox-only MTU A/B test.
 *
 * There is NO default change to the WireGuard configuration: the Fire TV,
 * phones, other Android TV devices and an unconfigured GalaBox get exactly the
 * same profile string as v175. No server settings or license records change.
 * A user must manually disconnect and reconnect after choosing a test value.
 */
internal object V176GalaBoxMtuPilot {
    private const val PREFS = "galabox-only-mtu-pilot-v176"
    private const val KEY = "selected_mtu"
    private val CHOICES = setOf(0, 1280, 1360, 1420)

    internal fun matchesGalaBox(manufacturer: String, model: String): Boolean =
        manufacturer.contains("galabox", ignoreCase = true) ||
            model.contains("galabox", ignoreCase = true)

    fun eligible(context: Context): Boolean =
        V173GalaBoxKeyCompat.supported(context) &&
            matchesGalaBox(Build.MANUFACTURER ?: "", Build.MODEL ?: "")

    fun selected(context: Context): Int =
        if (eligible(context))
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getInt(KEY, 0).takeIf { it in CHOICES } ?: 0
        else 0

    /** Explicit user choice. Does not initiate a tunnel restart or clear keys. */
    fun choose(context: Context, mtu: Int) {
        check(eligible(context)) { "MTU-Test nur auf der GalaBox verfügbar" }
        require(mtu in CHOICES)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putInt(KEY, mtu).apply()
    }

    internal fun next(current: Int): Int = when (current) {
        0 -> 1360
        1360 -> 1280
        1280 -> 1420
        else -> 0
    }

    /** A zero-length suffix is intentionally byte-identical on Fire TV. */
    fun interfaceSuffix(context: Context): String =
        selected(context).takeIf { it != 0 }?.let { "\n            MTU = " + it }.orEmpty()

    fun description(context: Context): String =
        selected(context).takeIf { it != 0 }?.let { "$it Bytes" } ?: "Automatisch (bisherig)"
}
