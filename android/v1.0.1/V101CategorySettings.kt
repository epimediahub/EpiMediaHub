package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.model.MediaKind

@Composable
fun V101CategorySettingsScreen(
    vm: MainViewModel,
    accent: Color,
    isTv: Boolean
) {
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("KATEGORIEN VERWALTEN", R.drawable.brand_header, { vm.back() })
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(if (isTv) 20.dp else 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                FocusCard(
                    "Live-TV-Kategorien",
                    "Sendergruppen ein- oder ausblenden",
                    R.drawable.icon_live,
                    accent = accent,
                    onClick = { vm.openCategoryManager(MediaKind.LIVE) }
                )
            }
            item {
                FocusCard(
                    "Film-Kategorien",
                    "Filmgruppen ein- oder ausblenden",
                    R.drawable.icon_movies,
                    accent = accent,
                    onClick = { vm.openCategoryManager(MediaKind.MOVIE) }
                )
            }
            item {
                FocusCard(
                    "Serien-Kategorien",
                    "Seriengruppen ein- oder ausblenden",
                    R.drawable.icon_series,
                    accent = accent,
                    onClick = { vm.openCategoryManager(MediaKind.SERIES) }
                )
            }
        }
    }
}
