package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.BuildConfig
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.data.AppUpdateInfo
import de.epimediahub.app.data.AppUpdateManager
import kotlinx.coroutines.launch

@Composable
fun UpdateScreen(vm: MainViewModel, accent: Color) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var checking by remember { mutableStateOf(false) }
    var downloading by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var update by remember { mutableStateOf<AppUpdateInfo?>(null) }

    BackHandler { vm.back() }

    LaunchedEffect(Unit) {
        AppUpdateManager.schedule(context.applicationContext)
        update = AppUpdateManager.pending(context.applicationContext)
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("APP-UPDATE", R.drawable.brand_header, { vm.back() })
        Box(Modifier.fillMaxSize().padding(18.dp), contentAlignment = Alignment.TopCenter) {
            GlassPanel(Modifier.fillMaxWidth().widthIn(max = 900.dp)) {
                Column(
                    Modifier.padding(26.dp).verticalScroll(rememberScrollState()),
                    horizontalAlignment = Alignment.Start
                ) {
                    Icon(Icons.Default.SystemUpdate, null, tint = accent, modifier = Modifier.size(52.dp))
                    Text("EpiMediaHub aktualisieren", fontSize = 29.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(top = 12.dp))
                    Text(
                        "Installiert: ${BuildConfig.VERSION_NAME}  ·  Build ${BuildConfig.VERSION_CODE}",
                        color = Color.White.copy(.72f),
                        modifier = Modifier.padding(top = 6.dp)
                    )
                    Text(
                        "EpiMediaHub prüft automatisch ungefähr alle 24 Stunden auf neue Versionen. Hier kannst du die Prüfung jederzeit sofort erzwingen.",
                        color = Color.White.copy(.68f),
                        modifier = Modifier.padding(top = 14.dp, bottom = 20.dp)
                    )

                    Button(
                        onClick = {
                            scope.launch {
                                checking = true
                                message = ""
                                runCatching { AppUpdateManager.checkNow(context.applicationContext) }
                                    .onSuccess { found ->
                                        update = found
                                        message = if (found == null) "Du nutzt bereits die aktuelle Version." else "Neue Version ${found.version} gefunden."
                                    }
                                    .onFailure { message = it.message ?: "Update-Prüfung fehlgeschlagen." }
                                checking = false
                            }
                        },
                        enabled = !checking && !downloading,
                        colors = ButtonDefaults.buttonColors(containerColor = accent),
                        shape = MaterialTheme.shapes.medium,
                        modifier = Modifier.fillMaxWidth().height(54.dp)
                    ) {
                        if (checking) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = Color.White)
                        else Text("Jetzt nach Updates suchen", fontWeight = FontWeight.Bold)
                    }

                    if (message.isNotBlank()) {
                        Text(message, modifier = Modifier.padding(top = 15.dp), color = Color.White.copy(.86f), fontWeight = FontWeight.SemiBold)
                    }

                    update?.let { info ->
                        Spacer(Modifier.height(20.dp))
                        Surface(
                            color = Color(0xF20A1420),
                            shape = MaterialTheme.shapes.large,
                            border = androidx.compose.foundation.BorderStroke(1.dp, accent.copy(.55f)),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(Modifier.padding(20.dp)) {
                                Text("Version ${info.version} verfügbar", color = accent, fontSize = 21.sp, fontWeight = FontWeight.Black)
                                if (info.notes.isNotBlank()) Text(info.notes, color = Color.White.copy(.72f), modifier = Modifier.padding(top = 9.dp))
                                Button(
                                    onClick = {
                                        scope.launch {
                                            downloading = true
                                            message = "Update wird heruntergeladen und geprüft …"
                                            runCatching {
                                                val apk = AppUpdateManager.downloadApk(context.applicationContext, info)
                                                AppUpdateManager.installApk(context.applicationContext, apk)
                                            }.onFailure {
                                                message = it.message ?: "Update konnte nicht installiert werden."
                                            }
                                            downloading = false
                                        }
                                    },
                                    enabled = !downloading && !checking,
                                    modifier = Modifier.fillMaxWidth().padding(top = 16.dp).height(52.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = accent),
                                    shape = MaterialTheme.shapes.medium
                                ) {
                                    if (downloading) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = Color.White)
                                    else Text("Update herunterladen und installieren", fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }

                    Text(
                        "Hinweis: Android zeigt vor der Installation weiterhin seine normale Sicherheits-/Installationsabfrage an.",
                        color = Color.White.copy(.5f),
                        fontSize = 12.sp,
                        modifier = Modifier.padding(top = 18.dp)
                    )
                }
            }
        }
    }
}
