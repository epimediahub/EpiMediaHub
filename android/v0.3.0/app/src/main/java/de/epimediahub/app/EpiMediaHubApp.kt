package de.epimediahub.app

import androidx.compose.material3.MaterialTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import de.epimediahub.app.ui.*

@Composable
fun EpiMediaHubApp(isTv: Boolean, vm: MainViewModel = viewModel()) {
    val u by vm.ui.collectAsState()
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
    MaterialTheme(colorScheme = scheme, shapes = shapes) {
        ThemeBackdrop(vm.themeRepo(), info, u.themeId) {
            when (val s = u.screen) {
                Screen.Home -> HomeScreen(vm, isTv, accent)
                Screen.AddPlaylist -> AddPlaylistScreen(vm, accent)
                Screen.Playlists -> PlaylistsScreen(vm, accent)
                Screen.Settings -> SettingsScreen(vm, accent)
                Screen.Themes -> ThemesScreen(vm, accent, isTv)
                Screen.WebAdmin -> WebAdminScreen(vm, accent)
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
    }
}
