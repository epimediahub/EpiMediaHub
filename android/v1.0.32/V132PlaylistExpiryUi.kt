package de.epimediahub.app.ui

import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import de.epimediahub.app.data.V132PlaylistExpiry
import de.epimediahub.app.data.V132PlaylistExpiryRepository
import de.epimediahub.app.model.PlaylistProfile

@Composable
internal fun v132RememberPlaylistExpiry(profile: PlaylistProfile?, now: Long): V132PlaylistExpiry {
    val context = LocalContext.current
    val repository = remember(context) { V132PlaylistExpiryRepository(context) }
    val key = V132PlaylistExpiryRepository.identity(profile)
    var result by remember(key) { mutableStateOf(repository.cached(profile)) }
    LaunchedEffect(key, now/3_600_000L) { result = repository.refresh(profile, now) }
    return result
}
