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
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import android.net.Uri
import android.webkit.WebSettings

private const val ADMIN_HOST = "admin.epimediahub.com"
private const val ADMIN_BASE = "https://admin.epimediahub.com"
private const val INCIDENTS = "https://admin.epimediahub.com/admin/mobile/alerts"

class MainActivity : FragmentActivity() {
    private var unlocked by mutableStateOf(false)
    private var notice by mutableStateOf("")
    private var selection by mutableStateOf(0)
    private lateinit var browser: WebView
    private var firstUnlock = true

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) registerPush() else notice = "Push benötigt die Benachrichtigungserlaubnis."
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        val openAlerts = intent.getBooleanExtra("open_alerts", false)
        selection = if (openAlerts) 2 else 0
        browser = WebView(this).apply {
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
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val uri = request.url
                    val isAdmin = uri.scheme == "https" && uri.host == ADMIN_HOST
                    if (isAdmin) return false
                    if (request.isForMainFrame && uri.scheme == "https") {
                        try { startActivity(Intent(Intent.ACTION_VIEW, uri)) } catch (_: Exception) {}
                    }
                    return true
                }
            }
            loadUrl(if (openAlerts) INCIDENTS else "$ADMIN_BASE/admin")
        }
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(modifier = Modifier.fillMaxSize()) {
                    if (!unlocked) {
                        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.Center) {
                            Text("EpiMediaHub Admin", style = MaterialTheme.typography.headlineMedium)
                            Spacer(Modifier.height(12.dp))
                            Text("Geschützter Administratorzugriff")
                            if (notice.isNotEmpty()) Text(notice, color = MaterialTheme.colorScheme.error)
                            Spacer(Modifier.height(18.dp))
                            Button(onClick = { requireUnlock() }) { Text("Gerät entsperren") }
                        }
                    } else {
                        AdminScreen()
                    }
                }
            }
        }
    }

    override fun onStart() {
        super.onStart()
        if (firstUnlock) {
            firstUnlock = false
        }
        requireUnlock()
    }

    override fun onStop() {
        unlocked = false
        super.onStop()
    }

    override fun onDestroy() {
        browser.destroy()
        super.onDestroy()
    }

    private fun requireUnlock() {
        if (unlocked || isFinishing) return
        val flags = BiometricManager.Authenticators.BIOMETRIC_STRONG or
                    BiometricManager.Authenticators.DEVICE_CREDENTIAL
        if (BiometricManager.from(this).canAuthenticate(flags) != BiometricManager.BIOMETRIC_SUCCESS) {
            notice = "Richte zuerst eine sichere Displaysperre oder Biometrie ein."
            return
        }
        val prompt = BiometricPrompt(
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
        )
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("EpiMediaHub Admin entsperren")
            .setSubtitle("Administrator-Dashboard")
            .setAllowedAuthenticators(flags)
            .build()
        prompt.authenticate(info)
    }

    @Composable
    private fun AdminScreen() {
        Column {
            Text("EpiMediaHub Admin", Modifier.padding(14.dp), style = MaterialTheme.typography.titleLarge)
            Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                listOf("Übersicht", "EpiScene", "Meldungen").forEachIndexed { index, title ->
                    val path = listOf("$ADMIN_BASE/admin", "$ADMIN_BASE/admin/skip", INCIDENTS)[index]
                    Button(
                        onClick = { selection = index; browser.loadUrl(path) },
                        modifier = Modifier.weight(1f),
                        contentPadding = PaddingValues(horizontal = 4.dp, vertical = 8.dp),
                        colors = if (selection == index) ButtonDefaults.buttonColors()
                                 else ButtonDefaults.outlinedButtonColors()
                    ) { Text(title) }
                }
            }
            Row(Modifier.padding(horizontal = 10.dp, vertical = 3.dp)) {
                OutlinedButton(onClick = { browser.reload() }) { Text("Aktualisieren") }
                Spacer(Modifier.width(8.dp))
                OutlinedButton(onClick = { enablePush() }) { Text("Push aktivieren") }
            }
            if (notice.isNotEmpty()) Text(notice, modifier = Modifier.padding(10.dp),
                style = MaterialTheme.typography.bodySmall)
            AndroidView(
                factory = {
                    (browser.parent as? ViewGroup)?.removeView(browser)
                    browser
                },
                modifier = Modifier.fillMaxWidth().weight(1f)
            )
        }
    }

    private fun enablePush() {
        if (!unlocked) return
        if (FirebaseApp.getApps(this).isEmpty()) {
            notice = "Push ist in diesem privaten Build noch nicht konfiguriert."
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
        notice = "Push-Registrierung wird geprüft …"
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { token ->
                val cookie = CookieManager.getInstance().getCookie(ADMIN_BASE) ?: ""
                if (cookie.isBlank()) {
                    notice = "Bitte erst im Dashboard anmelden."
                    return@addOnSuccessListener
                }
                AdminPushRegistration.register(this, token, cookie) { result ->
                    notice = result
                }
            }
            .addOnFailureListener { notice = "Firebase-Push ist noch nicht verfügbar." }
    }
}
