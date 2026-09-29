package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.model.ThemeGroup
import de.epimediahub.app.model.ThemeInfo

private data class V099Category(val group: ThemeGroup, val themes: List<ThemeInfo>)

private val V099LeagueIds = setOf(
    "england", "italy", "spain", "germany", "france", "netherlands",
    "turkey", "portugal", "scotland"
)

private fun V099CategoryName(id: String): String = when (id) {
    "england" -> "Premier League"
    "italy" -> "Serie A"
    "spain" -> "La Liga"
    "germany" -> "Bundesliga"
    "france" -> "Ligue 1"
    "netherlands" -> "Eredivisie"
    "turkey" -> "Süper Lig"
    "portugal" -> "Primeira Liga"
    "scotland" -> "Scottish Premiership"
    "national_teams" -> "Nationalmannschaften"
    "formula_1" -> "Formel 1"
    "cars" -> "Automarken"
    else -> id
}

@Composable
fun V079ThemesScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val catalog = u.themeCatalog ?: return
    var selectedGroupId by rememberSaveable { mutableStateOf<String?>(null) }
    var unlockDialog by remember { mutableStateOf(false) }
    val categories = remember(catalog, u.familySkinsUnlocked) {
        if (!u.familySkinsUnlocked) emptyList() else catalog.groups.mapNotNull { group ->
            if (group.id !in V099LeagueIds && group.id !in setOf("national_teams", "formula_1", "cars")) {
                return@mapNotNull null
            }
            val originals = group.themes.mapNotNull { catalog.themes[it] }
                .filter { it.family && vm.themeRepo().officialMarkRes(it.id) != 0 }
            if (originals.isEmpty()) null else V099Category(group, originals)
        }
    }
    val selected = categories.firstOrNull { it.group.id == selectedGroupId }
    BackHandler {
        if (selectedGroupId != null) selectedGroupId = null else vm.back()
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            selected?.let { V099CategoryName(it.group.id).uppercase() } ?: "PRIVATE SKINS",
            R.drawable.brand_header,
            { if (selectedGroupId != null) selectedGroupId = null else vm.back() },
            actions = {
                OutlinedButton(
                    onClick = {
                        if (u.familySkinsUnlocked) {
                            selectedGroupId = null
                            vm.lockPrivateSkins()
                        } else unlockDialog = true
                    },
                    modifier = Modifier.v070TvFocus(accent),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)
                ) {
                    Icon(if (u.familySkinsUnlocked) Icons.Default.LockOpen else Icons.Default.Lock, null,
                        modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(if (u.familySkinsUnlocked) "SPERREN" else "FREISCHALTEN",
                        fontSize = 11.sp, fontWeight = FontWeight.Black)
                }
            }
        )

        when {
            !u.familySkinsUnlocked -> {
                Column(
                    Modifier.fillMaxSize().padding(if (isTv) 48.dp else 20.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(Icons.Default.Lock, null, tint = accent, modifier = Modifier.size(48.dp))
                    Spacer(Modifier.height(18.dp))
                    Text("PRIVATE SKINS", color = Color.White,
                        fontSize = if (isTv) 27.sp else 21.sp, fontWeight = FontWeight.Black)
                    Spacer(Modifier.height(8.dp))
                    Text("Vereine, Nationalteams, Formel 1 und Automarken nach Passwortfreigabe",
                        color = Color.White.copy(.70f), fontSize = if (isTv) 15.sp else 12.sp)
                    Spacer(Modifier.height(22.dp))
                    Button(onClick = { unlockDialog = true }, modifier = Modifier.v070TvFocus(accent)) {
                        Text("SKINS FREISCHALTEN")
                    }
                }
            }
            selected != null -> {
                LazyColumn(
                    Modifier.fillMaxSize().padding(horizontal = if (isTv) 44.dp else 12.dp),
                    contentPadding = PaddingValues(top = 8.dp, bottom = 28.dp),
                    verticalArrangement = Arrangement.spacedBy(if (isTv) 12.dp else 9.dp)
                ) {
                    item(key = "back") {
                        TextButton(onClick = { selectedGroupId = null }, modifier = Modifier.v070TvFocus(accent)) {
                            Icon(Icons.Default.ArrowBack, null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(7.dp))
                            Text("ALLE KATEGORIEN")
                        }
                    }
                    items(selected.themes, key = { it.id }) { theme ->
                        V099ThemePreview(
                            vm, theme, theme.id == u.themeId, isTv,
                            onClick = { vm.selectTheme(theme.id) }
                        )
                    }
                }
            }
            else -> {
                val leagues = categories.filter { it.group.id in V099LeagueIds }
                val national = categories.filter { it.group.id == "national_teams" }
                val motorsport = categories.filter { it.group.id in setOf("formula_1", "cars") }
                LazyColumn(
                    Modifier.fillMaxSize().padding(horizontal = if (isTv) 44.dp else 12.dp),
                    contentPadding = PaddingValues(top = 9.dp, bottom = 30.dp),
                    verticalArrangement = Arrangement.spacedBy(if (isTv) 9.dp else 7.dp)
                ) {
                    item { V099SectionHeading("FUSSBALL · LIGEN", isTv) }
                    items(leagues, key = { it.group.id }) { item ->
                        V099CategoryCard(item, isTv, accent) { selectedGroupId = item.group.id }
                    }
                    if (national.isNotEmpty()) {
                        item { V099SectionHeading("NATIONALMANNSCHAFTEN", isTv) }
                        items(national, key = { it.group.id }) { item ->
                            V099CategoryCard(item, isTv, accent) { selectedGroupId = item.group.id }
                        }
                    }
                    if (motorsport.isNotEmpty()) {
                        item { V099SectionHeading("MOTORSPORT & AUTOS", isTv) }
                        items(motorsport, key = { it.group.id }) { item ->
                            V099CategoryCard(item, isTv, accent) { selectedGroupId = item.group.id }
                        }
                    }
                }
            }
        }
    }

    if (unlockDialog) {
        V099PrivatePasswordDialog(
            onDismiss = { unlockDialog = false },
            onVerify = { password ->
                vm.unlockFamilySkins(password).also { if (it) unlockDialog = false }
            }
        )
    }
}

@Composable
private fun V099SectionHeading(title: String, isTv: Boolean) {
    Text(title, color = Color.White.copy(.85f),
        fontSize = if (isTv) 15.sp else 12.sp,
        fontWeight = FontWeight.Black, letterSpacing = 1.sp,
        modifier = Modifier.padding(top = 11.dp, bottom = 3.dp))
}

@Composable
private fun V099CategoryCard(item: V099Category, isTv: Boolean, accent: Color, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.015f else 1f, label = "categoryFocus")
    val world = V097SkinWorldFor("", "", item.group.id)
    val shape = RoundedCornerShape(if (isTv) 16.dp else 12.dp)
    Box(
        Modifier.fillMaxWidth().height(if (isTv) 108.dp else 88.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .onFocusChanged { focused = it.isFocused }
            .focusable().clip(shape)
            .border(if (focused) 2.dp else 1.dp,
                if (focused) Color.White else Color.White.copy(.20f), shape)
            .clickable(onClick = onClick)
    ) {
        V097SkinEnvironment(world, accent)
        Box(Modifier.fillMaxSize().background(
            Brush.horizontalGradient(listOf(Color(0xE600050A), Color(0x9900050A), Color(0x4300050A)))))
        Column(Modifier.align(Alignment.CenterStart).padding(start = if (isTv) 24.dp else 15.dp)) {
            Text(V099CategoryName(item.group.id), color = Color.White,
                fontSize = if (isTv) 22.sp else 17.sp, fontWeight = FontWeight.Black)
            Text("${item.themes.size} Original-Skins · Privat", color = Color.White.copy(.72f),
                fontSize = if (isTv) 12.sp else 10.sp)
        }
        Text("›", modifier = Modifier.align(Alignment.CenterEnd).padding(end = 22.dp),
            color = if (focused) Color.White else accent, fontSize = 32.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun V099ThemePreview(vm: MainViewModel, theme: ThemeInfo, active: Boolean,
                             isTv: Boolean, onClick: () -> Unit) {
    val logoRes = vm.themeRepo().officialMarkRes(theme.id)
    val world = V097SkinWorldFor(theme.id, theme.label, theme.group)
    val accent = color(theme.accent)
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.015f else 1f, label = "skinFocus")
    val shape = RoundedCornerShape(if (isTv) 16.dp else 12.dp)
    Box(
        Modifier.fillMaxWidth().height(if (isTv) 172.dp else 133.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .onFocusChanged { focused = it.isFocused }
            .focusable().clip(shape)
            .border(if (focused) 3.dp else if (active) 2.dp else 1.dp,
                if (focused) Color.White else if (active) accent else Color.White.copy(.20f), shape)
            .clickable(onClick = onClick)
    ) {
        V097SkinEnvironment(world, accent)
        Box(Modifier.fillMaxSize().background(
            Brush.horizontalGradient(listOf(Color(0xD700050A), Color(0x6100050A), Color(0x4400050A)))))
        if (world == V097SkinWorld.GARAGE) {
            Box(Modifier.align(Alignment.Center).fillMaxHeight(.98f).fillMaxWidth(.50f)
                .background(Brush.radialGradient(
                    listOf(Color.White.copy(.44f), Color.White.copy(.12f), Color.Transparent))))
        }
        Image(
            painterResource(logoRes), contentDescription = theme.label,
            modifier = Modifier.align(Alignment.Center)
                .fillMaxHeight(.85f).fillMaxWidth(if (isTv) .42f else .45f)
                .graphicsLayer { alpha = .92f },
            contentScale = ContentScale.Fit
        )
        Column(Modifier.align(Alignment.BottomStart).padding(start = 20.dp, bottom = 14.dp)) {
            Text(theme.label, color = Color.White, fontSize = if (isTv) 22.sp else 16.sp,
                fontWeight = FontWeight.Black, maxLines = 1)
            Text(if (active) "AKTIV" else "PRIVAT · AUSWÄHLEN", color = if (active) accent else Color.White.copy(.78f),
                fontSize = if (isTv) 11.sp else 9.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun V099PrivatePasswordDialog(onDismiss: () -> Unit, onVerify: (String) -> Boolean) {
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(Icons.Default.Lock, null) },
        title = { Text("Private Skins") },
        text = {
            Column {
                Text("Die Original-Skins sind nach Passwortfreigabe sichtbar, bis du sie wieder sperrst.")
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it.filter(Char::isDigit).take(4); error = false },
                    singleLine = true,
                    label = { Text("Private-Passwort") },
                    placeholder = { Text("4 Ziffern") },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword)
                )
                if (error) Text("Private-Passwort ist falsch.", color = MaterialTheme.colorScheme.error)
            }
        },
        confirmButton = {
            Button(enabled = password.length == 4,
                onClick = { if (!onVerify(password)) error = true }) { Text("Freischalten") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } }
    )
}
