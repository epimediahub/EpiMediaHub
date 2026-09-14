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

private fun isFamilyGroup(id: String, label: String): Boolean {
    val a = id.lowercase()
    val b = label.lowercase()
    return a.contains("family") || a.contains("familie") || b.contains("family") || b.contains("familie")
}

@Composable
fun V045ThemesScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val cat = u.themeCatalog ?: return
    var pendingTheme by remember { mutableStateOf<String?>(null) }
    var showFamilySettings by remember { mutableStateOf(false) }
    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("DESIGNS", R.drawable.brand_header, { vm.back() }, actions = {
            TextButton(onClick = { showFamilySettings = true }) {
                Icon(
                    if (u.familyProtectionEnabled) Icons.Default.Lock else Icons.Default.LockOpen,
                    null,
                    tint = if (u.familyProtectionEnabled) accent else Color.White.copy(.78f)
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    if (u.familyProtectionEnabled) "Family-Skins geschützt" else "Family-Sperre einrichten",
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
                val family = isFamilyGroup(group.id, group.label)
                item(key = "group:${group.id}") {
                    Row(
                        Modifier.fillMaxWidth().padding(top = 14.dp, bottom = 2.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(group.label, color = accent, fontSize = 20.sp, fontWeight = FontWeight.Black)
                        if (family && u.familyProtectionEnabled) {
                            Spacer(Modifier.width(8.dp))
                            Icon(Icons.Default.Lock, null, tint = accent, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(5.dp))
                            Text("PIN", color = Color.White.copy(.78f), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
                items(group.themes, key = { it }) { id ->
                    val theme = cat.themes[id] ?: return@items
                    V045ThemePreview(
                        title = theme.label,
                        active = id == u.themeId,
                        locked = family && u.familyProtectionEnabled,
                        accent = color(theme.accent),
                        backgroundRes = vm.themeRepo().backgroundRes(id),
                        motifRes = vm.themeRepo().homeMotifRes(id).takeIf { it != 0 } ?: vm.themeRepo().markRes(id),
                        onClick = {
                            if (family && u.familyProtectionEnabled) pendingTheme = id else vm.selectTheme(id)
                        }
                    )
                }
            }
        }
    }

    pendingTheme?.let { id ->
        V045UnlockFamilyDialog(
            onDismiss = { pendingTheme = null },
            onUnlock = { pin ->
                if (vm.verifyFamilyPin(pin)) {
                    vm.selectTheme(id)
                    pendingTheme = null
                    true
                } else false
            }
        )
    }

    if (showFamilySettings) {
        V045FamilySettingsDialog(
            enabled = u.familyProtectionEnabled,
            onDismiss = { showFamilySettings = false },
            onEnable = { pin -> vm.enableFamilyPin(pin) },
            onDisable = { pin -> vm.disableFamilyPin(pin) },
            onChange = { oldPin, newPin -> vm.changeFamilyPin(oldPin, newPin) }
        )
    }
}

@Composable
private fun V045ThemePreview(
    title: String,
    active: Boolean,
    locked: Boolean,
    accent: Color,
    backgroundRes: Int,
    motifRes: Int,
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
                if (locked) {
                    Spacer(Modifier.width(8.dp))
                    Icon(Icons.Default.Lock, null, tint = accent, modifier = Modifier.size(19.dp))
                }
            }
            Spacer(Modifier.height(5.dp))
            Text(
                when {
                    active -> "AKTIV · angewendet"
                    locked -> "PIN erforderlich"
                    else -> "Antippen zum Anwenden"
                },
                color = if (active || locked) accent else Color.White.copy(.90f),
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
private fun V045UnlockFamilyDialog(onDismiss: () -> Unit, onUnlock: (String) -> Boolean) {
    var pin by remember { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(Icons.Default.Lock, null) },
        title = { Text("Family-Skin entsperren") },
        text = {
            Column {
                Text("Gib die Admin-PIN ein, um diesen Family-Skin zu aktivieren.")
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = pin,
                    onValueChange = { pin = it.filter(Char::isDigit).take(8); error = false },
                    singleLine = true,
                    label = { Text("PIN") },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword)
                )
                if (error) Text("PIN ist falsch.", color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 6.dp))
            }
        },
        confirmButton = {
            Button(onClick = { if (!onUnlock(pin)) error = true }) { Text("Entsperren") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } }
    )
}

@Composable
private fun V045FamilySettingsDialog(
    enabled: Boolean,
    onDismiss: () -> Unit,
    onEnable: (String) -> Boolean,
    onDisable: (String) -> Boolean,
    onChange: (String, String) -> Boolean
) {
    var currentPin by remember { mutableStateOf("") }
    var newPin by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(if (enabled) Icons.Default.Lock else Icons.Default.LockOpen, null) },
        title = { Text(if (enabled) "Family-Sperre verwalten" else "Family-Skins schützen") },
        text = {
            Column {
                Text(if (enabled) "Zum Ändern oder Abschalten zuerst die aktuelle Admin-PIN eingeben." else "Lege eine 4–8-stellige Admin-PIN fest. Family-Skins lassen sich danach nur mit dieser PIN aktivieren.")
                Spacer(Modifier.height(10.dp))
                if (enabled) {
                    OutlinedTextField(
                        value = currentPin,
                        onValueChange = { currentPin = it.filter(Char::isDigit).take(8); error = "" },
                        singleLine = true,
                        label = { Text("Aktuelle PIN") },
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword)
                    )
                    Spacer(Modifier.height(8.dp))
                }
                OutlinedTextField(
                    value = newPin,
                    onValueChange = { newPin = it.filter(Char::isDigit).take(8); error = "" },
                    singleLine = true,
                    label = { Text(if (enabled) "Neue PIN (optional)" else "Neue PIN") },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword)
                )
                if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 6.dp))
            }
        },
        confirmButton = {
            if (enabled) {
                Button(onClick = {
                    if (newPin.length !in 4..8) error = "Neue PIN muss 4–8 Ziffern haben."
                    else if (onChange(currentPin, newPin)) onDismiss() else error = "Aktuelle PIN ist falsch."
                }) { Text("PIN ändern") }
            } else {
                Button(onClick = {
                    if (newPin.length !in 4..8) error = "PIN muss 4–8 Ziffern haben."
                    else if (onEnable(newPin)) onDismiss() else error = "PIN konnte nicht gespeichert werden."
                }) { Text("Schutz aktivieren") }
            }
        },
        dismissButton = {
            Row {
                if (enabled) {
                    TextButton(onClick = {
                        if (onDisable(currentPin)) onDismiss() else error = "Aktuelle PIN ist falsch."
                    }) { Text("Schutz entfernen") }
                }
                TextButton(onClick = onDismiss) { Text("Schließen") }
            }
        }
    )
}
