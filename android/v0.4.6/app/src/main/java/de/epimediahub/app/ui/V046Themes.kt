package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
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
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R

@Composable
fun V046ThemesScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val cat = u.themeCatalog ?: return
    var requestFamilyUnlock by remember { mutableStateOf(false) }
    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("DESIGNS", R.drawable.brand_header, { vm.back() }, actions = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    if (u.familySkinsUnlocked) Icons.Default.LockOpen else Icons.Default.Lock,
                    null,
                    tint = if (u.familySkinsUnlocked) accent else Color.White.copy(.78f),
                    modifier = Modifier.size(18.dp)
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    if (u.familySkinsUnlocked) "Family freigeschaltet" else "Family gesperrt",
                    color = Color.White,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        })

        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal = if (isTv) 46.dp else 12.dp, vertical = 4.dp),
            contentPadding = PaddingValues(bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            cat.groups.forEach { group ->
                val allThemes = group.themes.mapNotNull { cat.themes[it] }
                val normalThemes = allThemes.filterNot { it.family }
                val familyThemes = allThemes.filter { it.family }
                val hasVisibleContent = normalThemes.isNotEmpty() || familyThemes.isNotEmpty()
                if (!hasVisibleContent) return@forEach

                item(key = "group:${group.id}") {
                    Text(
                        group.label,
                        color = accent,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Black,
                        modifier = Modifier.padding(top = 14.dp, bottom = 2.dp)
                    )
                }

                items(normalThemes, key = { it.id }) { theme ->
                    V046ThemePreview(
                        title = theme.label,
                        active = theme.id == u.themeId,
                        accent = color(theme.accent),
                        backgroundRes = vm.themeRepo().backgroundRes(theme.id),
                        motifRes = vm.themeRepo().homeMotifRes(theme.id).takeIf { it != 0 } ?: vm.themeRepo().markRes(theme.id),
                        family = false,
                        onClick = { vm.selectTheme(theme.id) }
                    )
                }

                if (familyThemes.isNotEmpty() && !u.familySkinsUnlocked) {
                    item(key = "family-lock:${group.id}") {
                        V046FamilyLockedCard(accent = accent, onClick = { requestFamilyUnlock = true })
                    }
                } else if (familyThemes.isNotEmpty()) {
                    items(familyThemes, key = { it.id }) { theme ->
                        V046ThemePreview(
                            title = theme.label,
                            active = theme.id == u.themeId,
                            accent = color(theme.accent),
                            backgroundRes = vm.themeRepo().backgroundRes(theme.id),
                            motifRes = vm.themeRepo().homeMotifRes(theme.id).takeIf { it != 0 } ?: vm.themeRepo().markRes(theme.id),
                            family = true,
                            onClick = { vm.selectTheme(theme.id) }
                        )
                    }
                }
            }
        }
    }

    if (requestFamilyUnlock) {
        V046FamilyPinDialog(
            title = "Family-Skins freischalten",
            message = "Dieser Bereich ist wie bei der Enigma-Version mit der speziellen Family-PIN geschützt.",
            onDismiss = { requestFamilyUnlock = false },
            onVerify = { pin ->
                val ok = vm.unlockFamilySkins(pin)
                if (ok) requestFamilyUnlock = false
                ok
            }
        )
    }
}

@Composable
private fun V046FamilyLockedCard(accent: Color, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(18.dp)
    Row(
        Modifier.fillMaxWidth().height(112.dp)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clip(shape)
            .background(Color(0xB0070D15))
            .border(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.15f), shape)
            .clickable(onClick = onClick)
            .padding(horizontal = 24.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(Icons.Default.Lock, null, tint = accent, modifier = Modifier.size(36.dp))
        Spacer(Modifier.width(18.dp))
        Column(Modifier.weight(1f)) {
            Text("FAMILY-BEREICH", color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Black)
            Spacer(Modifier.height(4.dp))
            Text("Spezielle Family-PIN erforderlich · Antippen zum Freischalten", color = Color.White.copy(.88f), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun V046ThemePreview(
    title: String,
    active: Boolean,
    accent: Color,
    backgroundRes: Int,
    motifRes: Int,
    family: Boolean,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(18.dp)
    Box(
        Modifier.fillMaxWidth().height(126.dp)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clip(shape)
            .background(Color(0x98070D15))
            .border(if (active || focused) 2.dp else 1.dp, if (active || focused) accent else Color.White.copy(.14f), shape)
            .clickable(onClick = onClick)
    ) {
        if (backgroundRes != 0) Image(painterResource(backgroundRes), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        Box(Modifier.fillMaxSize().background(Brush.horizontalGradient(listOf(Color.Black.copy(.24f), Color.Black.copy(.04f), Color.Black.copy(.54f)))))
        if (motifRes != 0) Image(painterResource(motifRes), null, Modifier.align(Alignment.CenterEnd).fillMaxHeight().fillMaxWidth(.64f), contentScale = ContentScale.Fit)
        Box(Modifier.align(Alignment.CenterStart).fillMaxHeight().width(if (active || focused) 8.dp else 3.dp).background(if (active || focused) accent else accent.copy(.48f)))
        Column(Modifier.align(Alignment.CenterStart).padding(start = 24.dp, end = 16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(title, color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Black, maxLines = 1)
                if (family) {
                    Spacer(Modifier.width(8.dp))
                    Icon(Icons.Default.LockOpen, null, tint = accent, modifier = Modifier.size(18.dp))
                }
            }
            Spacer(Modifier.height(5.dp))
            Text(
                if (active) "AKTIV · angewendet" else if (family) "FAMILY · freigeschaltet" else "Antippen zum Anwenden",
                color = if (active || family) accent else Color.White.copy(.90f),
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
fun V046FamilyPinDialog(
    title: String,
    message: String,
    onDismiss: () -> Unit,
    onVerify: (String) -> Boolean
) {
    var pin by remember { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(Icons.Default.Lock, null) },
        title = { Text(title) },
        text = {
            Column {
                Text(message)
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = pin,
                    onValueChange = { pin = it.filter(Char::isDigit).take(4); error = false },
                    singleLine = true,
                    label = { Text("Family-PIN") },
                    placeholder = { Text("4 Ziffern") },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword)
                )
                if (error) Text("Family-PIN ist falsch.", color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 6.dp))
            }
        },
        confirmButton = {
            Button(
                enabled = pin.length == 4,
                onClick = { if (!onVerify(pin)) error = true }
            ) { Text("Freischalten") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } }
    )
}
