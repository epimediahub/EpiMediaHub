package de.epimediahub.admin

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Dashboard
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Logout
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.NotificationsActive
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Security
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging

private const val ADMIN_HOST = "admin.epimediahub.com"
private const val ADMIN_BASE = "https://admin.epimediahub.com"
private const val ALERTS_URL = "https://admin.epimediahub.com/admin/mobile/alerts"
private const val HOME = 0
private const val DASHBOARD = 1
private const val EPISCENE = 2
private const val ALERTS = 3

private val Ink = Color(0xFF080E1B)
private val InkRaised = Color(0xFF101B2D)
private val InkElevated = Color(0xFF152238)
private val Border = Color(0xFF27374D)
private val Blue = Color(0xFF59C9FA)
private val BlueMuted = Color(0xFF113D55)
private val White = Color(0xFFF1F6FF)
private val Muted = Color(0xFFA1B2CB)
private val Positive = Color(0xFF5BD7BB)
private val Warning = Color(0xFFFBBE7D)

private val AdminColors = darkColorScheme(
    primary = Blue,
    onPrimary = Ink,
    secondary = Positive,
    background = Ink,
    onBackground = White,
    surface = InkRaised,
    onSurface = White,
    surfaceVariant = InkElevated,
    onSurfaceVariant = Muted,
    outline = Border,
    error = Warning
)

private data class Destination(val title: String, val hint: String, val url: String)
private val destinations = listOf(
    Destination("Start", "Deine Schaltzentrale", ""),
    Destination("Dashboard", "Verwaltung & System", ADMIN_BASE + "/admin"),
    Destination("EpiScene", "Analyse & Marker", ADMIN_BASE + "/admin/skip"),
    Destination("Meldungen", "Alarme & Verlauf", ALERTS_URL)
)

class MainActivity : FragmentActivity() {
    private var unlocked by mutableStateOf(false)
    private var notice by mutableStateOf("")
    private var selection by mutableIntStateOf(HOME)
    private var loading by mutableStateOf(false)
    private var pushRegistered by mutableStateOf(false)
    private var updateReady by mutableStateOf<AdminUpdater.Release?>(null)
    private var updateNotice by mutableStateOf("")
    private var updateCheckedForSession = false
    private var analysisDetailWeb by mutableStateOf(false)
    private var analysisBusy by mutableStateOf(false)
    private var analysisError by mutableStateOf("")
    private var analysisSnapshot by mutableStateOf<AdminNativeStatus.Snapshot?>(null)
    private lateinit var browser: WebView

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) registerPush() else notice = "Bitte erlaube Benachrichtigungen in Android."
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        pushRegistered = getSharedPreferences("admin-push", MODE_PRIVATE)
            .getBoolean("registered", false)
        if (intent.getBooleanExtra("open_alerts", false)) selection = ALERTS

        browser = WebView(this).apply {
            setBackgroundColor(android.graphics.Color.WHITE)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.javaScriptCanOpenWindowsAutomatically = false
            settings.setSupportMultipleWindows(false)
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            settings.cacheMode = WebSettings.LOAD_NO_CACHE
            CookieManager.getInstance().setAcceptThirdPartyCookies(this, false)
            webChromeClient = WebChromeClient()
            webViewClient = object : WebViewClient() {
                override fun onPageStarted(view: WebView, url: String, favicon: android.graphics.Bitmap?) {
                    loading = true
                }

                override fun onPageFinished(view: WebView, url: String) {
                    loading = false
                    if (!updateCheckedForSession && url.startsWith(ADMIN_BASE)) {
                        val cookie = CookieManager.getInstance().getCookie(ADMIN_BASE) ?: ""
                        if (cookie.isNotBlank()) {
                            updateCheckedForSession = true
                            checkForUpdates(false)
                        }
                    }
                }

                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val uri = request.url
                    val internal = uri.scheme == "https" && uri.host == ADMIN_HOST
                    if (internal) return false
                    if (request.isForMainFrame && uri.scheme == "https") {
                        try { startActivity(Intent(Intent.ACTION_VIEW, uri)) }
                        catch (_: Exception) { notice = "Der externe Link konnte nicht geöffnet werden." }
                    }
                    return true
                }
            }
            loadUrl(if (selection == ALERTS) ALERTS_URL else ADMIN_BASE + "/admin")
        }

        setContent {
            MaterialTheme(colorScheme = AdminColors) {
                Surface(modifier = Modifier.fillMaxSize(), color = Ink) {
                    if (unlocked) AdminExperience() else LockExperience()
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.getBooleanExtra("open_alerts", false)) {
            selectDestination(ALERTS)
        }
    }

    override fun onStart() {
        super.onStart()
        requireUnlock()
    }

    override fun onStop() {
        unlocked = false
        super.onStop()
    }

    override fun onDestroy() {
        (browser.parent as? ViewGroup)?.removeView(browser)
        browser.destroy()
        super.onDestroy()
    }

    private fun selectDestination(next: Int) {
        if (next !in destinations.indices) return
        selection = next
        notice = ""
        analysisDetailWeb = false
        if (next == EPISCENE) loadEpiscene()
        else if (next != HOME) browser.loadUrl(destinations[next].url)
    }

    private fun requireUnlock() {
        if (unlocked || isFinishing) return
        val flags = BiometricManager.Authenticators.BIOMETRIC_STRONG or
            BiometricManager.Authenticators.DEVICE_CREDENTIAL
        if (BiometricManager.from(this).canAuthenticate(flags) != BiometricManager.BIOMETRIC_SUCCESS) {
            notice = "Richte zuerst eine sichere Displaysperre oder Biometrie ein."
            return
        }
        BiometricPrompt(
            this, ContextCompat.getMainExecutor(this),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    unlocked = true
                    notice = ""
                }
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    notice = "Entsperrung erforderlich."
                }
            }
        ).authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("EpiMediaHub Admin")
                .setSubtitle("Geschützten Arbeitsbereich entsperren")
                .setAllowedAuthenticators(flags)
                .build()
        )
    }

    @Composable
    private fun LockExperience() {
        Box(
            modifier = Modifier.fillMaxSize().background(
                Brush.verticalGradient(listOf(Color(0xFF142C47), Ink, Ink))
            ).statusBarsPadding().navigationBarsPadding().padding(28.dp)
        ) {
            Column(
                modifier = Modifier.align(Alignment.Center).fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                BrandMark(82)
                Spacer(Modifier.height(26.dp))
                Text("EPIMEDIAHUB", color = Blue, fontSize = 12.sp, letterSpacing = 3.sp,
                    fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(9.dp))
                Text("Command Center", color = White, fontSize = 31.sp,
                    fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
                Spacer(Modifier.height(12.dp))
                Text("Dein privater Zugang zur Verwaltung und Überwachung.",
                    color = Muted, fontSize = 14.sp, lineHeight = 21.sp,
                    textAlign = TextAlign.Center)
                Spacer(Modifier.height(36.dp))
                Button(
                    onClick = { requireUnlock() },
                    modifier = Modifier.fillMaxWidth().height(54.dp),
                    shape = RoundedCornerShape(15.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Blue, contentColor = Ink)
                ) {
                    Icon(Icons.Outlined.Lock, contentDescription = null)
                    Spacer(Modifier.width(10.dp))
                    Text("Sicher entsperren", fontWeight = FontWeight.Bold)
                }
                if (notice.isNotBlank()) {
                    Spacer(Modifier.height(20.dp))
                    Text(notice, color = Warning, fontSize = 13.sp, textAlign = TextAlign.Center)
                }
            }
            Row(modifier = Modifier.align(Alignment.BottomCenter),
                verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Security, contentDescription = null,
                    tint = Muted, modifier = Modifier.size(15.dp))
                Spacer(Modifier.width(8.dp))
                Text("Nur für autorisierte Administratoren", color = Muted, fontSize = 11.sp)
            }
        }
    }

    @Composable
    private fun AdminExperience() {
        BackHandler(enabled = selection != HOME) {
            if (selection == EPISCENE && analysisDetailWeb) analysisDetailWeb = false
            else if (selection != EPISCENE && browser.canGoBack()) browser.goBack()
            else selectDestination(HOME)
        }
        Column(
            modifier = Modifier.fillMaxSize().background(Ink)
                .statusBarsPadding().navigationBarsPadding()
        ) {
            AdminHeader()
            if (selection == HOME) {
                HomeContent(modifier = Modifier.weight(1f))
            } else if (selection == EPISCENE && !analysisDetailWeb) {
                NativeEpiscene(modifier = Modifier.weight(1f))
            } else {
                WebContent(modifier = Modifier.weight(1f))
            }
            NavigationFooter()
        }
    }

    @Composable
    private fun AdminHeader() {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 13.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            BrandMark(42)
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text("EPIMEDIAHUB", color = White, fontWeight = FontWeight.ExtraBold,
                    fontSize = 16.sp, letterSpacing = 1.6.sp)
                Text("A D M I N   C E N T E R", color = Blue,
                    fontSize = 9.sp, letterSpacing = 1.sp, fontWeight = FontWeight.SemiBold)
            }
            Surface(
                shape = RoundedCornerShape(20.dp),
                color = BlueMuted,
                border = BorderStroke(1.dp, Blue.copy(alpha = .25f))
            ) {
                Row(modifier = Modifier.padding(horizontal = 10.dp, vertical = 7.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Lock, null, tint = Blue, modifier = Modifier.size(13.dp))
                    Spacer(Modifier.width(5.dp))
                    Text("PRIVAT", color = Blue, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
        HorizontalDivider(color = Border, thickness = 1.dp)
    }

    @Composable
    private fun BrandMark(size: Int) {
        Box(
            modifier = Modifier.size(size.dp)
                .clip(RoundedCornerShape((size * .28f).dp))
                .background(Brush.linearGradient(listOf(Blue, Color(0xFF367ADD)))),
            contentAlignment = Alignment.Center
        ) {
            Text("E", color = Ink, fontWeight = FontWeight.Black,
                fontSize = (size * .57f).sp)
        }
    }

    @Composable
    private fun HomeContent(modifier: Modifier = Modifier) {
        Column(
            modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(horizontal = 19.dp, vertical = 15.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Box(
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(23.dp))
                    .background(Brush.linearGradient(
                        listOf(Color(0xFF153855), Color(0xFF10233C), InkRaised)
                    ))
            ) {
                Column(modifier = Modifier.padding(22.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(7.dp).clip(CircleShape).background(Positive))
                        Spacer(Modifier.width(9.dp))
                        Text("LOKAL ENTSPERRT", color = Positive, letterSpacing = 1.3.sp,
                            fontWeight = FontWeight.Bold, fontSize = 10.sp)
                    }
                    Spacer(Modifier.height(14.dp))
                    Text("Deine Zentrale.\nAlles im Blick.",
                        color = White, fontSize = 28.sp,
                        lineHeight = 33.sp, fontWeight = FontWeight.ExtraBold)
                    Spacer(Modifier.height(9.dp))
                    Text("Verwaltung, EpiScene und Systemmeldungen an einem Ort.",
                        color = Color(0xFFB9D0E5), lineHeight = 20.sp, fontSize = 13.sp)
                    Spacer(Modifier.height(18.dp))
                    Button(
                        onClick = { selectDestination(DASHBOARD) },
                        colors = ButtonDefaults.buttonColors(containerColor = Blue, contentColor = Ink),
                        shape = RoundedCornerShape(13.dp)
                    ) {
                        Text("Dashboard öffnen", fontWeight = FontWeight.Bold)
                        Spacer(Modifier.width(8.dp))
                        Icon(Icons.Outlined.ChevronRight, null)
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("SCHNELLZUGRIFF", color = Muted,
                    fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.6.sp)
                Spacer(Modifier.weight(1f))
                Text("3 Bereiche", color = Muted, fontSize = 11.sp)
            }
            QuickAccessCard(
                icon = { Icon(Icons.Outlined.Dashboard, null, tint = Blue) },
                title = "Verwaltung",
                subtitle = "Kunden, Reseller, Lizenzen und VPN",
                onClick = { selectDestination(DASHBOARD) }
            )
            QuickAccessCard(
                icon = { Icon(Icons.Outlined.AutoAwesome, null, tint = Positive) },
                title = "EpiScene",
                subtitle = "Analysefortschritt und Intro-/Outro-Marker",
                onClick = { selectDestination(EPISCENE) }
            )
            QuickAccessCard(
                icon = { Icon(Icons.Outlined.Notifications, null, tint = Warning) },
                title = "Meldungen",
                subtitle = "Warnungen, Ereignisse und Bestätigungen",
                onClick = { selectDestination(ALERTS) }
            )
            UpdatePanel()
            PushPanel()
            Spacer(Modifier.height(5.dp))
            Text(
                "PRIVATE ADMIN APP  ·  BUILD " + BuildConfig.VERSION_NAME,
                modifier = Modifier.fillMaxWidth(),
                color = Muted.copy(alpha = .75f),
                textAlign = TextAlign.Center, letterSpacing = 1.2.sp, fontSize = 10.sp
            )
            Spacer(Modifier.height(5.dp))
        }
    }

    @Composable
    private fun QuickAccessCard(
        icon: @Composable () -> Unit,
        title: String,
        subtitle: String,
        onClick: () -> Unit
    ) {
        Surface(
            onClick = onClick,
            shape = RoundedCornerShape(18.dp),
            color = InkRaised,
            border = BorderStroke(1.dp, Border)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 15.dp, vertical = 15.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    modifier = Modifier.size(48.dp).clip(RoundedCornerShape(13.dp))
                        .background(InkElevated),
                    contentAlignment = Alignment.Center
                ) { icon() }
                Spacer(Modifier.width(14.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(title, color = White, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(4.dp))
                    Text(subtitle, color = Muted, fontSize = 12.sp,
                        lineHeight = 17.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                Icon(Icons.Outlined.ChevronRight, null, tint = Muted,
                    modifier = Modifier.size(20.dp))
            }
        }
    }

    @Composable
    private fun UpdatePanel() {
        Surface(
            shape = RoundedCornerShape(18.dp),
            color = InkRaised,
            border = BorderStroke(1.dp, Border)
        ) {
            Column(Modifier.padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Refresh, null, tint = Positive,
                        modifier = Modifier.size(22.dp))
                    Spacer(Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text("In-App-Updates", color = White,
                            fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        Text(
                            if (updateReady != null) "Version ${updateReady!!.name} ist bereit"
                            else "Neue Versionen direkt in dieser App installieren",
                            color = Muted, fontSize = 11.sp
                        )
                    }
                }
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = {
                        if (updateReady != null) installUpdate()
                        else checkForUpdates(true)
                    },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (updateReady != null) Positive else BlueMuted,
                        contentColor = if (updateReady != null) Ink else Blue
                    ),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Icon(Icons.Outlined.Refresh, null, modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(7.dp))
                    Text(
                        if (updateReady != null) "Update ${updateReady!!.name} installieren"
                        else "Auf Updates prüfen",
                        fontSize = 13.sp, fontWeight = FontWeight.SemiBold
                    )
                }
                if (updateNotice.isNotBlank()) {
                    Spacer(Modifier.height(9.dp))
                    Text(updateNotice, color = Muted, fontSize = 12.sp, lineHeight = 17.sp)
                }
            }
        }
    }

    private fun checkForUpdates(showMessage: Boolean) {
        val cookie = CookieManager.getInstance().getCookie(ADMIN_BASE) ?: ""
        if (cookie.isBlank()) {
            if (showMessage) updateNotice = "Bitte zuerst im Dashboard anmelden."
            return
        }
        if (showMessage) updateNotice = "Update wird geprüft …"
        AdminUpdater.check(cookie, BuildConfig.VERSION_CODE.toLong()) { candidate, message ->
            updateReady = candidate
            if (showMessage || candidate != null) updateNotice = message
        }
    }

    private fun installUpdate() {
        val release = updateReady ?: return
        val cookie = CookieManager.getInstance().getCookie(ADMIN_BASE) ?: ""
        updateNotice = "Das signierte Update wird heruntergeladen und überprüft …"
        AdminUpdater.downloadAndInstall(this, cookie, release) { message ->
            updateNotice = message
        }
    }

    @Composable
    private fun PushPanel() {
        Surface(
            shape = RoundedCornerShape(18.dp),
            color = InkRaised,
            border = BorderStroke(1.dp, Border)
        ) {
            Column(Modifier.padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.NotificationsActive, null, tint = Blue,
                        modifier = Modifier.size(22.dp))
                    Spacer(Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Push-Benachrichtigungen", color = White,
                            fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        Text(
                            if (pushRegistered) "Dieses Gerät ist registriert."
                            else "Noch nicht für dieses Gerät aktiviert.",
                            color = Muted, fontSize = 11.sp
                        )
                    }
                }
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = { enablePush() },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = BlueMuted, contentColor = Blue),
                        shape = RoundedCornerShape(12.dp),
                        contentPadding = PaddingValues(horizontal = 8.dp)
                    ) {
                        Text(if (pushRegistered) "Erneut verbinden" else "Push aktivieren",
                            fontSize = 12.sp, maxLines = 1)
                    }
                    OutlinedButton(
                        onClick = { unregisterPush() },
                        modifier = Modifier.weight(1f),
                        border = BorderStroke(1.dp, Border),
                        shape = RoundedCornerShape(12.dp),
                        contentPadding = PaddingValues(horizontal = 8.dp)
                    ) {
                        Icon(Icons.Outlined.Logout, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Abmelden", fontSize = 12.sp, maxLines = 1)
                    }
                }
                if (notice.isNotBlank()) {
                    Spacer(Modifier.height(10.dp))
                    Text(notice, color = Warning, fontSize = 12.sp, lineHeight = 17.sp)
                }
            }
        }
    }

    private fun loadEpiscene() {
        if (!unlocked) return
        if (analysisBusy) return
        analysisBusy = true
        analysisError = ""
        val cookie = CookieManager.getInstance().getCookie(ADMIN_BASE) ?: ""
        AdminNativeStatus.load(cookie) { value, error ->
            analysisBusy = false
            analysisSnapshot = value
            analysisError = error
        }
    }

    @Composable
    private fun NativeEpiscene(modifier: Modifier = Modifier) {
        Column(
            modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(horizontal = 18.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(15.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text("EpiScene", color = White, fontSize = 27.sp,
                        fontWeight = FontWeight.ExtraBold)
                    Text("Zwei unabhängige Analysequellen · Live-Status",
                        color = Muted, fontSize = 12.sp)
                }
                OutlinedButton(
                    onClick = { loadEpiscene() },
                    enabled = !analysisBusy,
                    border = BorderStroke(1.dp, Border),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Icon(Icons.Outlined.Refresh, null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(5.dp))
                    Text("Aktuell")
                }
            }
            if (analysisBusy) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            val status = analysisSnapshot
            if (analysisError.isNotBlank()) {
                Surface(color = InkElevated, shape = RoundedCornerShape(13.dp),
                    border = BorderStroke(1.dp, Warning.copy(alpha = .4f))) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Status nicht bestätigt", color = Warning,
                            fontWeight = FontWeight.Bold)
                        Spacer(Modifier.height(5.dp))
                        Text(analysisError, color = Muted, fontSize = 13.sp)
                        TextButton(onClick = { selectDestination(DASHBOARD) }) {
                            Text("Im Dashboard anmelden", color = Blue)
                        }
                    }
                }
            }
            if (status != null) {
                Text(
                    "Letzte Abfrage: " + java.text.DateFormat.getDateTimeInstance(
                        java.text.DateFormat.SHORT, java.text.DateFormat.SHORT
                    ).format(java.util.Date(status.sampledAtEpoch * 1000)),
                    color = Muted, fontSize = 12.sp
                )
                for (lane in status.lanes) {
                    Surface(
                        shape = RoundedCornerShape(18.dp), color = InkRaised,
                        border = BorderStroke(1.dp, Border)
                    ) {
                        Column(Modifier.fillMaxWidth().padding(17.dp),
                            verticalArrangement = Arrangement.spacedBy(11.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(Modifier.size(9.dp).clip(CircleShape)
                                    .background(if (lane.enabled) Positive else Warning))
                                Spacer(Modifier.width(9.dp))
                                Text(lane.label, color = White, fontWeight = FontWeight.Bold,
                                    fontSize = 17.sp, modifier = Modifier.weight(1f))
                                Text(if (lane.enabled) "Quelle aktiv" else "Quelle deaktiviert",
                                    color = if (lane.enabled) Positive else Warning,
                                    fontSize = 11.sp)
                            }
                            HorizontalDivider(color = Border)
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text("WARTEND", color = Muted, fontSize = 10.sp)
                                    Text(lane.queued.toString(), color = White,
                                        fontSize = 24.sp, fontWeight = FontWeight.Bold)
                                }
                                Column(modifier = Modifier.weight(1f)) {
                                    Text("IN ARBEIT", color = Muted, fontSize = 10.sp)
                                    Text(lane.running.toString(), color = Blue,
                                        fontSize = 24.sp, fontWeight = FontWeight.Bold)
                                }
                                Column(modifier = Modifier.weight(1f)) {
                                    Text("ABGESCHLOSSEN", color = Muted, fontSize = 10.sp)
                                    Text(lane.completed.toString(), color = Positive,
                                        fontSize = 24.sp, fontWeight = FontWeight.Bold)
                                }
                            }
                            Text(
                                "Fehlgeschlagen: " + lane.failed + " · Letzter Abschluss: " +
                                    (lane.lastCompletionEpoch?.let {
                                        java.text.DateFormat.getDateTimeInstance(
                                            java.text.DateFormat.SHORT,
                                            java.text.DateFormat.SHORT
                                        ).format(java.util.Date(it * 1000))
                                    } ?: "nicht belegt"),
                                color = Muted, fontSize = 12.sp, lineHeight = 19.sp
                            )
                        }
                    }
                }
                Text("Quellenstatus und Zähler sind keine Garantie für neue erfolgreiche " +
                    "Erkennung. Keine Kunden-Playlists werden ausgewertet.",
                    color = Muted, fontSize = 12.sp, lineHeight = 19.sp)
            } else if (!analysisBusy && analysisError.isBlank()) {
                Text("Noch keine aktuellen Messwerte verfügbar.",
                    color = Muted, fontSize = 13.sp)
            }
            Button(
                onClick = {
                    analysisDetailWeb = true
                    browser.loadUrl(ADMIN_BASE + "/admin/skip")
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Blue, contentColor = Ink),
                shape = RoundedCornerShape(13.dp)
            ) {
                Text("Analyseverwaltung öffnen", fontWeight = FontWeight.Bold)
                Spacer(Modifier.width(8.dp))
                Icon(Icons.Outlined.ChevronRight, null)
            }
            Spacer(Modifier.height(8.dp))
        }
    }

    @Composable
    private fun WebContent(modifier: Modifier = Modifier) {
        Column(
            modifier = modifier.fillMaxWidth().padding(horizontal = 15.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp, horizontal = 5.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(destinations[selection].title, color = White,
                        fontSize = 23.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(3.dp))
                    Text(destinations[selection].hint, color = Muted, fontSize = 12.sp)
                }
                Surface(
                    modifier = Modifier.size(44.dp),
                    onClick = { browser.reload() },
                    color = InkElevated,
                    shape = RoundedCornerShape(13.dp),
                    border = BorderStroke(1.dp, Border)
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Outlined.Refresh, contentDescription = "Seite aktualisieren",
                            tint = Blue, modifier = Modifier.size(20.dp))
                    }
                }
            }
            Surface(
                modifier = Modifier.fillMaxWidth().weight(1f),
                shape = RoundedCornerShape(topStart = 17.dp, topEnd = 17.dp),
                color = InkRaised,
                border = BorderStroke(1.dp, Border)
            ) {
                Column {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(
                            start = 13.dp, end = 13.dp, top = 10.dp, bottom = 10.dp
                        ),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Outlined.Lock, null, tint = Positive,
                            modifier = Modifier.size(13.dp))
                        Spacer(Modifier.width(7.dp))
                        Text("admin.epimediahub.com", color = Muted,
                            fontSize = 11.sp, modifier = Modifier.weight(1f))
                        if (loading) CircularProgressIndicator(
                            modifier = Modifier.size(16.dp), strokeWidth = 2.dp, color = Blue
                        )
                    }
                    AndroidView(
                        factory = {
                            (browser.parent as? ViewGroup)?.removeView(browser)
                            browser
                        },
                        modifier = Modifier.fillMaxWidth().weight(1f)
                    )
                }
            }
            if (notice.isNotBlank()) {
                Text(
                    notice, color = Warning, fontSize = 12.sp,
                    modifier = Modifier.fillMaxWidth().padding(9.dp)
                )
            }
        }
    }

    @Composable
    private fun NavigationFooter() {
        val icons = listOf(Icons.Outlined.Home, Icons.Outlined.Dashboard,
            Icons.Outlined.AutoAwesome, Icons.Outlined.Notifications)
        NavigationBar(
            containerColor = InkRaised,
            tonalElevation = 0.dp,
            modifier = Modifier.fillMaxWidth()
        ) {
            destinations.forEachIndexed { index, destination ->
                NavigationBarItem(
                    selected = selection == index,
                    onClick = { if (selection != index) selectDestination(index) },
                    icon = {
                        Icon(icons[index], contentDescription = null,
                            modifier = Modifier.size(22.dp))
                    },
                    label = {
                        Text(destination.title, fontSize = 10.sp,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                    },
                    alwaysShowLabel = true,
                    colors = NavigationBarItemDefaults.colors(
                        selectedIconColor = Ink,
                        selectedTextColor = Blue,
                        indicatorColor = Blue,
                        unselectedIconColor = Muted,
                        unselectedTextColor = Muted
                    )
                )
            }
        }
    }

    private fun unregisterPush() {
        val cookie = CookieManager.getInstance().getCookie(ADMIN_BASE) ?: ""
        if (cookie.isBlank()) {
            notice = "Bitte zuerst im Dashboard anmelden."
            return
        }
        AdminPushRegistration.unregister(this, cookie) {
            notice = it
            pushRegistered = getSharedPreferences("admin-push", MODE_PRIVATE)
                .getBoolean("registered", false)
        }
    }

    private fun enablePush() {
        if (!unlocked) return
        if (FirebaseApp.getApps(this).isEmpty()) {
            notice = "Firebase ist in diesem Build noch nicht eingerichtet."
            return
        }
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            android.content.pm.PackageManager.PERMISSION_GRANTED) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            return
        }
        registerPush()
    }

    private fun registerPush() {
        notice = "Push-Verbindung wird geprüft …"
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { token ->
                val cookie = CookieManager.getInstance().getCookie(ADMIN_BASE) ?: ""
                if (cookie.isBlank()) {
                    notice = "Bitte zuerst im Dashboard anmelden."
                    return@addOnSuccessListener
                }
                AdminPushRegistration.register(this, token, cookie) {
                    notice = it
                    pushRegistered = getSharedPreferences("admin-push", MODE_PRIVATE)
                        .getBoolean("registered", false)
                }
            }
            .addOnFailureListener { notice = "Firebase-Push ist noch nicht erreichbar." }
    }
}
