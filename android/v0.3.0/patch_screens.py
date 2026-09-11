from pathlib import Path
import sys

root = Path(sys.argv[1])
p = root / "app/src/main/java/de/epimediahub/app/ui/Screens.kt"
s = p.read_text()

s = s.replace("import androidx.compose.foundation.background\n", "import androidx.compose.foundation.background\nimport androidx.compose.foundation.border\nimport androidx.compose.foundation.focusable\nimport androidx.compose.foundation.text.selection.SelectionContainer\n")
s = s.replace("import androidx.compose.ui.Alignment\n", "import androidx.compose.ui.Alignment\nimport androidx.compose.ui.focus.onFocusChanged\n")
s = s.replace("import androidx.compose.ui.text.input.KeyboardType\n", "import androidx.compose.ui.text.input.KeyboardType\nimport androidx.compose.ui.text.input.PasswordVisualTransformation\n")

def replace_block(text, start, end, block):
    a = text.index(start)
    b = text.index(end, a)
    return text[:a] + block + "\n\n" + text[b:]

add_playlist = r'''@Composable
fun AddPlaylistScreen(vm: MainViewModel, accent: Color) {
    var mode by remember { mutableStateOf("xtream") }
    var name by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("") }
    var portal by remember { mutableStateOf("") }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val u by vm.ui.collectAsState()
    BackHandler(enabled = u.playlists.isNotEmpty()) { vm.back() }
    Box(Modifier.fillMaxSize().padding(18.dp), contentAlignment = Alignment.Center) {
        GlassPanel(Modifier.fillMaxWidth(.94f).widthIn(max = 820.dp)) {
            Column(Modifier.padding(28.dp)) {
                Text("Playlist hinzufügen", fontSize = 30.sp, fontWeight = FontWeight.Black, color = Color.White)
                Spacer(Modifier.height(6.dp))
                Text("Xtream Codes ist am bequemsten: Portal, Benutzername und Passwort reichen aus.", color = Color.White.copy(.68f))
                Spacer(Modifier.height(20.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    FilterChip(selected = mode == "xtream", onClick = { mode = "xtream" }, label = { Text("Xtream Codes") }, leadingIcon = { Icon(Icons.Default.Key, null) })
                    FilterChip(selected = mode == "m3u", onClick = { mode = "m3u" }, label = { Text("M3U / URL") }, leadingIcon = { Icon(Icons.Default.Link, null) })
                }
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(name, { name = it }, label = { Text("Name, z. B. Wohnzimmer") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(10.dp))
                if (mode == "xtream") {
                    OutlinedTextField(portal, { portal = it }, label = { Text("Portal / Domain") }, placeholder = { Text("http://server.tld:8080") }, modifier = Modifier.fillMaxWidth(), singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(username, { username = it }, label = { Text("Username") }, modifier = Modifier.weight(1f), singleLine = true)
                        OutlinedTextField(password, { password = it }, label = { Text("Passwort") }, modifier = Modifier.weight(1f), singleLine = true, visualTransformation = PasswordVisualTransformation())
                    }
                } else {
                    OutlinedTextField(url, { url = it }, label = { Text("M3U / get.php URL") }, modifier = Modifier.fillMaxWidth(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), minLines = 2)
                }
                if (u.error.isNotBlank()) Text(u.error, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 10.dp))
                Spacer(Modifier.height(18.dp))
                Button(
                    onClick = {
                        if (mode == "xtream") vm.addXtream(name, portal, username, password)
                        else vm.addPlaylist(name, url)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = accent),
                    shape = MaterialTheme.shapes.medium,
                    modifier = Modifier.fillMaxWidth().height(52.dp)
                ) { Text(if (mode == "xtream") "Xtream verbinden" else "Playlist speichern", fontWeight = FontWeight.Bold) }
                Spacer(Modifier.height(9.dp))
                Text("Tipp für Android TV: Unter Einstellungen → PC-Verwaltung kannst du diese Daten bequem am Computer eingeben.", color = Color.White.copy(.54f), fontSize = 12.sp)
            }
        }
    }
}'''

media_card = r'''@Composable
fun MediaCard(
    media: MediaEntry,
    accent: Color,
    subtitle: String = "",
    progress: Float? = null,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val shape = androidx.compose.foundation.shape.RoundedCornerShape(24.dp)
    GlassPanel(
        Modifier.height(244.dp).padding(1.dp)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .border(if (focused) 2.dp else 0.dp, if (focused) accent else Color.Transparent, shape)
            .clickable(onClick = onClick)
    ) {
        Column(Modifier.fillMaxSize()) {
            if (media.image.isNotBlank()) {
                AsyncImage(model = media.image, contentDescription = null, modifier = Modifier.fillMaxWidth().weight(1f), contentScale = ContentScale.Crop)
            } else {
                Box(
                    Modifier.fillMaxWidth().weight(1f).background(
                        androidx.compose.ui.graphics.Brush.linearGradient(listOf(accent.copy(.24f), Color(0x33234B6F)))
                    ),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Default.PlayArrow, null, tint = Color.White.copy(.9f), modifier = Modifier.size(50.dp))
                }
            }
            Column(Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 10.dp)) {
                Text(media.name, color = Color.White, fontWeight = FontWeight.ExtraBold, maxLines = 2)
                if (subtitle.isNotBlank()) Text(subtitle, color = Color.White.copy(.65f), fontSize = 12.sp, maxLines = 2)
                if (media.rating.isNotBlank()) Text("★ ${media.rating}", color = accent, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                progress?.let { LinearProgressIndicator(progress = it, modifier = Modifier.fillMaxWidth().padding(top = 7.dp)) }
            }
        }
    }
}'''

settings_and_web = r'''@Composable
fun SettingsScreen(vm: MainViewModel, accent: Color) {
    val u by vm.ui.collectAsState()
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("EINSTELLUNGEN", R.drawable.brand_header, { vm.back() })
        LazyColumn(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { FocusCard("Skin / Design", u.themeCatalog?.themes?.get(u.themeId)?.label.orEmpty(), R.drawable.icon_settings, accent = accent, onClick = { vm.navigate(Screen.Themes) }) }
            item { FocusCard("Playlists verwalten", "${u.playlists.size} gespeichert", R.drawable.icon_playlist, accent = accent, onClick = { vm.navigate(Screen.Playlists) }) }
            item {
                FocusCard(
                    "PC-Verwaltung im Browser",
                    if (u.webAdminRunning) "Aktiv · ${u.webAdminUrl}" else "Playlist und Xtream bequem am Computer eingeben",
                    R.drawable.icon_playlist,
                    accent = accent,
                    onClick = { vm.navigate(Screen.WebAdmin) }
                )
            }
            item {
                FocusCard("Bevorzugte Audiosprache", languageLabel(u.preferredAudioLanguage), R.drawable.icon_settings, accent = accent, onClick = { vm.setAudioLanguage(nextAudioLanguage(u.preferredAudioLanguage)) })
            }
            item {
                FocusCard("Bevorzugte Untertitelsprache", languageLabel(u.preferredSubtitleLanguage), R.drawable.icon_settings, accent = accent, onClick = { vm.setSubtitleLanguage(nextSubtitleLanguage(u.preferredSubtitleLanguage)) })
            }
            item {
                GlassPanel(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp)) {
                        Text("Android v0.3.0", color = Color.White, fontWeight = FontWeight.Bold)
                        Text("Modernisierte Oberfläche · Xtream-Eingabe · lokale Browser-Verwaltung · Android TV / Google TV + Mobile.", color = Color.White.copy(.66f))
                    }
                }
            }
        }
    }
}

@Composable
fun WebAdminScreen(vm: MainViewModel, accent: Color) {
    val u by vm.ui.collectAsState()
    BackHandler { vm.back() }
    LaunchedEffect(Unit) { if (!u.webAdminRunning) vm.startWebAdmin() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("PC-VERWALTUNG", R.drawable.brand_header, { vm.back() })
        Box(Modifier.fillMaxSize().padding(18.dp), contentAlignment = Alignment.TopCenter) {
            GlassPanel(Modifier.fillMaxWidth().widthIn(max = 820.dp)) {
                Column(Modifier.padding(28.dp)) {
                    Icon(Icons.Default.Computer, null, tint = accent, modifier = Modifier.size(48.dp))
                    Spacer(Modifier.height(14.dp))
                    Text("Playlist am Computer einrichten", color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.Black)
                    Spacer(Modifier.height(8.dp))
                    Text("TV/Handy und Computer müssen im selben lokalen Netzwerk sein. Öffne die Adresse im Browser und bestätige Änderungen mit dem sechsstelligen PIN.", color = Color.White.copy(.68f))
                    Spacer(Modifier.height(22.dp))
                    if (u.webAdminRunning) {
                        Text("ADRESSE", color = accent, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        SelectionContainer { Text(u.webAdminUrl, color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold) }
                        Spacer(Modifier.height(18.dp))
                        Text("PIN", color = accent, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        Text(u.webAdminPin, color = Color.White, fontSize = 38.sp, fontWeight = FontWeight.Black, letterSpacing = 6.sp)
                        Spacer(Modifier.height(20.dp))
                        Text("Im Browser kannst du wählen zwischen Xtream Codes (Portal + Username + Passwort) und einer normalen M3U/get.php-URL. Bei Xtream baut EpiMediaHub alle benötigten URLs automatisch.", color = Color.White.copy(.7f))
                        Spacer(Modifier.height(22.dp))
                        OutlinedButton(onClick = { vm.stopWebAdmin() }, shape = MaterialTheme.shapes.medium) { Text("PC-Verwaltung stoppen") }
                    } else {
                        if (u.error.isNotBlank()) Text(u.error, color = MaterialTheme.colorScheme.error)
                        Button(onClick = { vm.startWebAdmin() }, colors = ButtonDefaults.buttonColors(containerColor = accent), shape = MaterialTheme.shapes.medium) {
                            Text("PC-Verwaltung starten", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}'''

s = replace_block(s, "@Composable\nfun AddPlaylistScreen", "@Composable\nfun CategoryScreen", add_playlist)
s = replace_block(s, "@Composable\nfun MediaCard", "@Composable\nfun SearchScreen", media_card)
s = replace_block(s, "@Composable\nfun SettingsScreen", "@Composable\nfun ThemesScreen", settings_and_web)
p.write_text(s)
