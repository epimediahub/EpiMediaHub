#!/usr/bin/env python3
import os
import re
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
path = java / "ui/V035Screens.kt"
text = path.read_text()

pattern = re.compile(
    r'@Composable\nfun V035SearchScreen\([\s\S]*?\n\}\n\n@Composable\nfun V035FavoritesScreen',
    re.MULTILINE,
)

replacement = r'''@Composable
fun V035SearchScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val kind = u.contentFilterKind
    var query by remember { mutableStateOf("") }
    val legacyFireTvKeyboard = remember { isTv && v110NeedsLegacyFireTvKeyboard() }
    var tvKeyboardOpen by remember(legacyFireTvKeyboard) { mutableStateOf(legacyFireTvKeyboard) }
    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            (kind?.let { sectionTitle35(it) + " · " }.orEmpty()) + "SUCHE",
            R.drawable.brand_header,
            { vm.back() }
        )

        if (legacyFireTvKeyboard) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 70.dp, vertical = 9.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    modifier = Modifier.weight(1f).height(56.dp),
                    color = Color(0xFF111821),
                    shape = RoundedCornerShape(12.dp),
                    border = androidx.compose.foundation.BorderStroke(
                        1.dp,
                        if (query.isBlank()) Color.White.copy(.15f) else accent.copy(.65f)
                    )
                ) {
                    Row(
                        Modifier.fillMaxSize().padding(horizontal = 14.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Search, null, tint = accent)
                        Spacer(Modifier.width(10.dp))
                        Text(
                            query.ifBlank { "Suchbegriff eingeben …" },
                            color = if (query.isBlank()) Color.White.copy(.45f) else Color.White,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1
                        )
                    }
                }
                Button(
                    onClick = { tvKeyboardOpen = true },
                    colors = ButtonDefaults.buttonColors(containerColor = accent)
                ) {
                    Text("Tastatur", fontWeight = FontWeight.Black)
                }
            }
        } else {
            OutlinedTextField(
                value = query,
                onValueChange = {
                    query = it
                    vm.search(it)
                },
                label = { Text("Suchen") },
                leadingIcon = { Icon(Icons.Default.Search, null) },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = if (isTv) 70.dp else 14.dp, vertical = 9.dp)
            )
        }

        StatusLine35(u.loading, u.error, accent)
        LazyColumn(
            Modifier
                .fillMaxSize()
                .padding(horizontal = if (isTv) 70.dp else 12.dp),
            contentPadding = PaddingValues(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(u.searchResults, key = { it.resumeKey }) { item ->
                SearchOrFavoriteRow35(vm, item, accent, isTv)
            }
        }
    }

    if (legacyFireTvKeyboard && tvKeyboardOpen) {
        V110TvKeyboardDialog(
            title = (kind?.let { sectionTitle35(it) + " · " }.orEmpty()) + "Suche",
            initialValue = query,
            accent = accent,
            onDismiss = { tvKeyboardOpen = false },
            onValueChange = {
                query = it
                vm.search(it)
            },
            onSubmit = {
                query = it
                vm.search(it)
                tvKeyboardOpen = false
            }
        )
    }
}

@Composable
fun V035FavoritesScreen'''

updated, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f"V035SearchScreen replacement count was {count}")

path.write_text(updated)

for marker in (
    "V110TvKeyboardDialog(",
    "v110NeedsLegacyFireTvKeyboard()",
    'Text("Tastatur"',
):
    if marker not in updated:
        raise SystemExit(f"missing global TV search marker: {marker}")

print("Android 1.0.10 TV-safe keyboard applied to Live TV, Movies and Series search")
