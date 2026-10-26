package de.epimediahub.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import de.epimediahub.app.data.V112PlaylistProbe
import de.epimediahub.app.model.PlaylistProfile
import de.epimediahub.app.model.PlaylistType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.runInterruptible
import kotlinx.coroutines.supervisorScope
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.ConcurrentHashMap

internal enum class V112PlaylistStatus { CHECKING, ONLINE, OFFLINE }

private object V112PlaylistHealthCache {
    data class Entry(val profile: PlaylistProfile, val status: V112PlaylistStatus, val checkedAt: Long)
    val entries = ConcurrentHashMap<String, Entry>()
    fun fresh(profile: PlaylistProfile): V112PlaylistStatus? = entries[profile.id]?.takeIf {
        it.profile == profile && System.currentTimeMillis() - it.checkedAt in 0L..59_999L
    }?.status
}

@Composable
internal fun rememberV112PlaylistHealth(profiles: List<PlaylistProfile>): Map<String, V112PlaylistStatus> {
    val statuses = remember { mutableStateMapOf<String, V112PlaylistStatus>() }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(profiles, lifecycle) {
        val ids = profiles.map { it.id }.toSet()
        statuses.keys.toList().filterNot { it in ids }.forEach { statuses.remove(it) }
        V112PlaylistHealthCache.entries.keys.toList().filterNot { it in ids }.forEach {
            V112PlaylistHealthCache.entries.remove(it)
        }
        profiles.forEach { statuses[it.id] = V112PlaylistHealthCache.fresh(it) ?: V112PlaylistStatus.CHECKING }
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            val parallel = Semaphore(4)
            while (isActive) {
                supervisorScope {
                    profiles.forEach { profile ->
                        launch {
                            parallel.withPermit {
                                val cached = V112PlaylistHealthCache.fresh(profile)
                                if (cached != null) {
                                    statuses[profile.id] = cached
                                } else {
                                    val rawUrl = if (profile.type == PlaylistType.XTREAM)
                                        profile.server.ifBlank { profile.originalUrl } else profile.originalUrl
                                    val online = withTimeoutOrNull(5_000L) {
                                        runInterruptible(Dispatchers.IO) { V112PlaylistProbe.online(rawUrl) }
                                    } ?: false
                                    val status = if (online) V112PlaylistStatus.ONLINE else V112PlaylistStatus.OFFLINE
                                    V112PlaylistHealthCache.entries[profile.id] = V112PlaylistHealthCache.Entry(
                                        profile, status, System.currentTimeMillis()
                                    )
                                    statuses[profile.id] = status
                                }
                            }
                        }
                    }
                }
                delay(60_000L)
            }
        }
    }
    return statuses
}

@Composable
internal fun V112PlaylistStatusLight(status: V112PlaylistStatus) {
    val color = when (status) {
        V112PlaylistStatus.ONLINE -> Color(0xFF39FF88)
        V112PlaylistStatus.OFFLINE -> Color(0xFFFF5252)
        V112PlaylistStatus.CHECKING -> Color(0xFFB7C4D5)
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier.size(48.dp).background(
                Brush.radialGradient(listOf(color.copy(.55f), color.copy(.18f), Color.Transparent)),
                CircleShape
            ), contentAlignment = Alignment.Center
        ) {
            Box(Modifier.size(25.dp).background(color, CircleShape).border(2.dp, color.copy(.85f), CircleShape))
        }
        Text(
            when (status) {
                V112PlaylistStatus.ONLINE -> "ONLINE"
                V112PlaylistStatus.OFFLINE -> "OFFLINE"
                V112PlaylistStatus.CHECKING -> "PRÜFT …"
            }, color = color, fontSize = 15.sp, fontWeight = FontWeight.Black
        )
    }
}
