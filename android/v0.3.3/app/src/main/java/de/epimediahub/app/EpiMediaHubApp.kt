package de.epimediahub.app

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import de.epimediahub.app.data.AppUpdateInfo
import de.epimediahub.app.data.AppUpdateManager
import de.epimediahub.app.ui.*
import kotlinx.coroutines.launch

@Composable
fun EpiMediaHubApp(isTv: Boolean, vm: MainViewModel = viewModel()) {
    val u by vm.ui.collectAsState()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var updateInfo by remember { mutableStateOf<AppUpdateInfo?>(null) }
    var updateBusy by remember { mutableStateOf(false) }
    var updateError by remember { mutableStateOf<String?>(null) }

    val info = u.themeCatalog?.themes?.get(u.themeId)
    val accent = color(info?.accent ?: "#28A7F2")
    val scheme = darkColorScheme(
        primary = accent,
        secondary = accent,
        background = Color(0xFF080A11),
        surface = Color(0xFF0B1730),
        onBackground = Color.White,
        onSurface = Color.White
    )
    val shapes = Shapes(
        extraSmall = RoundedCornerShape(10.dp),
        small = RoundedCornerShape(14.dp),
        medium = RoundedCornerShape(20.dp),
        large = RoundedCornerShape(26.dp),
        extraLarge = RoundedCornerShape(32.dp)
    )

    val hasInternalBackTarget = u.screen != Screen.Home &&
        !(u.screen == Screen.AddPlaylist && u.playlists.isEmpty())
    BackHandler(enabled = hasInternalBackTarget) { vm.back() }

    LaunchedEffect(Unit) {
        AppUpdateManager.schedule(context.applicationContext)
        updateInfo = runCatching {
            AppUpdateManager.checkIfDue(context.applicationContext)
        }.getOrNull()
    }

    MaterialTheme(colorScheme = scheme, shapes = shapes) {
        ThemeBackdrop(vm.themeRepo(), info, u.themeId) {
            when (val s = u.screen) {
                Screen.Home -> HomeScreen(vm, isTv, accent)
                Screen.AddPlaylist -> AddPlaylistScreen(vm, accent)
                Screen.Playlists -> PlaylistsScreen(vm, accent)
                Screen.Settings -> SettingsScreen(vm, accent)
                Screen.Themes -> ThemesScreen(vm, accent, isTv)
                Screen.WebAdmin -> WebAdminScreen(vm, accent)
                Screen.Updates -> UpdateScreen(vm, accent)
                Screen.Search -> SearchScreen(vm, accent, isTv)
                Screen.Favorites -> FavoritesScreen(vm, accent, isTv)
                Screen.ContinueWatching -> ContinueWatchingScreen(vm, accent, isTv)
                is Screen.Categories -> CategoryScreen(vm, s.kind, accent, isTv)
                is Screen.Items -> ItemsScreen(vm, s.kind, s.category, accent, isTv)
                is Screen.Epg -> EpgScreen(vm, s.category, accent, isTv)
                is Screen.Episodes -> EpisodesScreen(vm, s.series, accent, isTv)
                is Screen.Player -> PlayerScreen(vm, s.item, s.episodeList, accent, isTv)
            }
        }

        updateInfo?.let { update ->
            AlertDialog(
                onDismissRequest = { if (!updateBusy) updateInfo = null },
                title = {
                    Text("EpiMediaHub ${update.version} verfügbar", fontWeight = FontWeight.Bold)
                },
                text = {
                    Text(
                        buildString {
                            append("Installiert: ${BuildConfig.VERSION_NAME}\n\n")
                            append(if (update.notes.isBlank()) "Eine neue Version ist verfügbar." else update.notes)
                            if (updateBusy) append("\n\nUpdate wird heruntergeladen und geprüft …")
                        }
                    )
                },
                confirmButton = {
                    TextButton(
                        enabled = !updateBusy,
                        onClick = {
                            scope.launch {
                                updateBusy = true
                                updateError = null
                                runCatching {
                                    val apk = AppUpdateManager.downloadApk(context.applicationContext, update)
                                    AppUpdateManager.installApk(context.applicationContext, apk)
                                }.onFailure {
                                    updateError = it.message ?: "Update konnte nicht heruntergeladen werden."
                                }
                                updateBusy = false
                            }
                        }
                    ) {
                        Text(if (updateBusy) "Wird geladen …" else "Herunterladen")
                    }
                },
                dismissButton = {
                    TextButton(enabled = !updateBusy, onClick = { updateInfo = null }) {
                        Text("Später")
                    }
                }
            )
        }

        updateError?.let { message ->
            AlertDialog(
                onDismissRequest = { updateError = null },
                title = { Text("Update fehlgeschlagen") },
                text = { Text(message) },
                confirmButton = {
                    TextButton(onClick = { updateError = null }) { Text("OK") }
                }
            )
        }
    }
}
