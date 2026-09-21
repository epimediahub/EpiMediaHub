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
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
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
import de.epimediahub.app.model.ThemeInfo

@Composable
fun V079ThemesScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val catalog = u.themeCatalog ?: return
    var requestPrivateUnlock by remember { mutableStateOf(false) }

    val normalGroups = remember(catalog, u.familySkinsUnlocked) {
        catalog.groups.mapNotNull { group ->
            val themes = group.themes.mapNotNull { catalog.themes[it] }.filterNot { it.family }
            if (themes.isEmpty()) null else group to themes
        }
    }
    val privateThemes = remember(catalog, u.familySkinsUnlocked) {
        if (!u.familySkinsUnlocked) emptyList()
        else catalog.groups.flatMap { group ->
            group.themes.mapNotNull { catalog.themes[it] }.filter { it.family }
        }.distinctBy { it.id }
    }

    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("DESIGNS", R.drawable.brand_header, { vm.back() }, actions = {
            if (u.familySkinsUnlocked) {
                OutlinedButton(
                    onClick = { vm.lockPrivateSkins() },
                    modifier = Modifier.v070TvFocus(accent),
                    border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(.18f)),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)
                ) {
                    Icon(Icons.Default.LockOpen, null, modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(7.dp))
                    Text("PRIVATE SPERREN", fontWeight = FontWeight.Black, fontSize = 11.sp)
                }
            } else {
                OutlinedButton(
                    onClick = { requestPrivateUnlock = true },
                    modifier = Modifier.v070TvFocus(accent),
                    border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(.18f)),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)
                ) {
                    Icon(Icons.Default.Lock, null, modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(7.dp))
                    Text("PRIVATE DESIGNS", fontWeight = FontWeight.Black, fontSize = 11.sp)
                }
            }
        })

        LazyColumn(
            Modifier.fillMaxSize().padding(
                horizontal = if (isTv) 46.dp else 12.dp,
                vertical = if (isTv) 8.dp else 4.dp
            ),
            contentPadding = PaddingValues(bottom = 34.dp),
            verticalArrangement = Arrangement.spacedBy(if (isTv) 11.dp else 8.dp)
        ) {
            item(key = "design-intro") {
                Column(Modifier.padding(top = 6.dp, bottom = 8.dp)) {
                    Text(
                        "PREMIUM SKINS",
                        color = Color.White,
                        fontSize = if (isTv) 24.sp else 19.sp,
                        fontWeight = FontWeight.Black
                    )
                    Text(
                        "Markenidentität bleibt erhalten · ruhige Flächen · klare Fokusführung · einheitliche Designsprache",
                        color = Color.White.copy(.56f),
                        fontSize = if (isTv) 13.sp else 11.sp
                    )
                }
            }

            normalGroups.forEach { (group, themes) ->
                item(key = "group:${group.id}") {
                    Text(
                        group.label.uppercase(),
                        color = accent.copy(.92f),
                        fontSize = if (isTv) 15.sp else 12.sp,
                        letterSpacing = 1.2.sp,
                        fontWeight = FontWeight.Black,
                        modifier = Modifier.padding(top = 12.dp, bottom = 1.dp)
                    )
                }
                items(themes, key = { it.id }) { theme ->
                    V079ThemePreview(
                        vm = vm,
                        theme = theme,
                        active = theme.id == u.themeId,
                        isTv = isTv,
                        privateTheme = false,
                        onClick = { vm.selectTheme(theme.id) }
                    )
                }
            }

            if (u.familySkinsUnlocked && privateThemes.isNotEmpty()) {
                item(key = "private-heading") {
                    Row(
                        Modifier.fillMaxWidth().padding(top = 20.dp, bottom = 3.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.LockOpen, null, tint = accent, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Text(
                                "PRIVATE DESIGNS",
                                color = accent,
                                fontSize = if (isTv) 16.sp else 13.sp,
                                fontWeight = FontWeight.Black,
                                letterSpacing = 1.2.sp
                            )
                            Text(
                                "Nur nach Passwortfreigabe sichtbar",
                                color = Color.White.copy(.48f),
                                fontSize = if (isTv) 12.sp else 10.sp
                            )
                        }
                    }
                }
                items(privateThemes, key = { "private:${it.id}" }) { theme ->
                    V079ThemePreview(
                        vm = vm,
                        theme = theme,
                        active = theme.id == u.themeId,
                        isTv = isTv,
                        privateTheme = true,
                        onClick = { vm.selectTheme(theme.id) }
                    )
                }
            }
        }
    }

    if (requestPrivateUnlock) {
        V079PrivatePasswordDialog(
            onDismiss = { requestPrivateUnlock = false },
            onVerify = { password ->
                val ok = vm.unlockFamilySkins(password)
                if (ok) requestPrivateUnlock = false
                ok
            }
        )
    }
}

@Composable
private fun V079ThemePreview(
    vm: MainViewModel,
    theme: ThemeInfo,
    active: Boolean,
    isTv: Boolean,
    privateTheme: Boolean,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.025f else 1f, label = "v079ThemeFocus")
    val themeAccent = color(theme.accent)
    val shape = RoundedCornerShape(if (isTv) 18.dp else 15.dp)
    val backgroundRes = vm.themeRepo().backgroundRes(theme.id)
    val motifRes = vm.themeRepo().homeMotifRes(theme.id).takeIf { it != 0 }
        ?: vm.themeRepo().markRes(theme.id)

    Box(
        Modifier.fillMaxWidth()
            .height(if (isTv) 132.dp else 108.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 24.dp else 3.dp, shape)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clip(shape)
            .background(Color(0xF20A0E14))
            .border(
                if (focused) 3.dp else if (active) 2.dp else 1.dp,
                if (focused) Color.White else if (active) themeAccent else Color.White.copy(.11f),
                shape
            )
            .clickable(onClick = onClick)
    ) {
        if (backgroundRes != 0) {
            Image(
                painterResource(backgroundRes),
                null,
                Modifier.fillMaxSize().graphicsLayer { alpha = .28f },
                contentScale = ContentScale.Crop
            )
        }
        Box(
            Modifier.fillMaxSize().background(
                Brush.horizontalGradient(
                    listOf(
                        Color(0xFB080C12),
                        Color(0xED0C1119),
                        Color(0xDB101720)
                    )
                )
            )
        )
        if (motifRes != 0) {
            Image(
                painterResource(motifRes),
                null,
                Modifier.align(Alignment.CenterEnd)
                    .fillMaxHeight(.88f)
                    .fillMaxWidth(if (isTv) .38f else .42f)
                    .padding(end = if (isTv) 18.dp else 8.dp)
                    .graphicsLayer { alpha = if (focused) .18f else .095f },
                contentScale = ContentScale.Fit
            )
        }
        Box(
            Modifier.align(Alignment.CenterStart)
                .fillMaxHeight()
                .width(if (focused || active) 6.dp else 3.dp)
                .background(if (focused || active) themeAccent else themeAccent.copy(.46f))
        )
        Column(
            Modifier.align(Alignment.CenterStart)
                .fillMaxWidth(if (isTv) .67f else .70f)
                .padding(start = if (isTv) 26.dp else 18.dp, end = 12.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    theme.label,
                    color = Color.White,
                    fontSize = if (isTv) 22.sp else 17.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 1
                )
                if (privateTheme) {
                    Spacer(Modifier.width(8.dp))
                    Icon(Icons.Default.LockOpen, null, tint = themeAccent, modifier = Modifier.size(16.dp))
                }
            }
            Spacer(Modifier.height(4.dp))
            Text(
                when {
                    active -> "AKTIV"
                    privateTheme -> "PRIVATE · FREIGESCHALTET"
                    else -> "DESIGN ANWENDEN"
                },
                color = if (active || privateTheme) themeAccent else Color.White.copy(.55f),
                fontSize = if (isTv) 12.sp else 10.sp,
                fontWeight = FontWeight.Black,
                letterSpacing = .7.sp
            )
        }
        if (focused) {
            Surface(
                modifier = Modifier.align(Alignment.BottomEnd).padding(9.dp),
                color = themeAccent,
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    "OK",
                    color = Color.Black,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Black,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                )
            }
        }
    }
}

@Composable
private fun V079PrivatePasswordDialog(
    onDismiss: () -> Unit,
    onVerify: (String) -> Boolean
) {
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(Icons.Default.Lock, null) },
        title = { Text("Private Designs") },
        text = {
            Column {
                Text("Private Skins sind vollständig verborgen. Gib das Private-Passwort ein, um sie für diese Sitzung sichtbar zu machen.")
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = password,
                    onValueChange = {
                        password = it.filter(Char::isDigit).take(4)
                        error = false
                    },
                    singleLine = true,
                    label = { Text("Private-Passwort") },
                    placeholder = { Text("4 Ziffern") },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword)
                )
                if (error) {
                    Text(
                        "Private-Passwort ist falsch.",
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.padding(top = 7.dp)
                    )
                }
            }
        },
        confirmButton = {
            Button(
                enabled = password.length == 4,
                onClick = { if (!onVerify(password)) error = true }
            ) { Text("Freischalten") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Abbrechen") }
        }
    )
}
