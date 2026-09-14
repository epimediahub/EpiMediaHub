package de.epimediahub.app.ui

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

internal fun parityClock(s: Long): String = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(s * 1000L))
