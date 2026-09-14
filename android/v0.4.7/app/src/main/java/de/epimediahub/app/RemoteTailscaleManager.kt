package de.epimediahub.app

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build
import com.tailscale.ipn.App
import com.tailscale.ipn.ui.localapi.Client
import com.tailscale.ipn.ui.model.Ipn
import com.tailscale.ipn.ui.model.IpnState
import java.lang.ref.WeakReference
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Embedded Tailscale controller for EpiMediaHub remote maintenance.
 *
 * The Android APK never contains an OAuth client secret or reusable auth key.
 * First enrollment asks the trusted Raspberry provisioner for a short-lived,
 * one-use auth key. The resulting Tailscale node identity is persisted by
 * libtailscale and reused for automatic reconnects.
 */
object RemoteTailscaleManager {
    enum class Phase {
        IDLE,
        CHECKING,
        FINDING_RASPBERRY,
        REQUESTING_ACCESS,
        ENROLLING,
        VPN_PERMISSION,
        CONNECTING,
        CONNECTED,
        PIN_REQUIRED,
        ERROR
    }

    data class State(
        val phase: Phase = Phase.IDLE,
        val message: String = "Bereit",
        val tailscaleIp: String = "",
        val raspberryReachable: Boolean = false,
        val lastError: String = ""
    )

    private const val PROVISIONER_URL = "http://192.168.0.207:8787/v1/enroll"
    private const val PROVISIONER_HEALTH = "http://192.168.0.207:8787/health"
    private const val PREFS = "epimediahub_tailscale"
    private const val KEY_PROVISIONED = "provisioned"
    private const val KEY_INSTALL_ID = "install_id"

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state

    private var activityRef = WeakReference<Activity>(null)
    private var permissionLauncher: ((Intent) -> Unit)? = null
    private var pendingStartAfterPermission = false
    private var activeJob: Job? = null

    fun attach(activity: Activity, launchPermission: (Intent) -> Unit) {
        activityRef = WeakReference(activity)
        permissionLauncher = launchPermission
    }

    fun detach(activity: Activity) {
        if (activityRef.get() === activity) activityRef.clear()
    }

    fun onHostResumed() {
        if (_state.value.phase == Phase.VPN_PERMISSION) {
            // Android may have granted permission while Activity was paused.
            val activity = activityRef.get() ?: return
            if (VpnService.prepare(activity) == null && pendingStartAfterPermission) {
                onVpnPermissionResult(true)
            }
        }
    }

    fun isProvisioned(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY_PROVISIONED, false)

    fun ensureConnected() {
        val activity = activityRef.get() ?: return
        if (activeJob?.isActive == true) return
        activeJob = scope.launch {
            _state.value = State(Phase.CHECKING, "Tailscale-Status wird geprüft …")
            val status = runCatching { status() }.getOrNull()
            connectedIp(status)?.let { ip ->
                _state.value = State(Phase.CONNECTED, "Verbunden · Fernwartung bereit", ip, true)
                return@launch
            }
            if (!isProvisioned(activity)) {
                _state.value = State(
                    Phase.PIN_REQUIRED,
                    "Ersteinrichtung benötigt einmalig die Fernwartungs-PIN."
                )
                return@launch
            }
            _state.value = State(Phase.CONNECTING, "Gespeicherte Tailscale-Identität wird verbunden …")
            requestVpnAndStart()
        }
    }

    fun provisionAndConnect(remotePin: String) {
        val activity = activityRef.get() ?: run {
            _state.value = State(Phase.ERROR, "App-Oberfläche ist noch nicht bereit.", lastError = "no_activity")
            return
        }
        if (activeJob?.isActive == true) activeJob?.cancel()
        activeJob = scope.launch {
            _state.value = State(Phase.CHECKING, "Tailscale-Status wird geprüft …")
            val current = runCatching { status() }.getOrNull()
            connectedIp(current)?.let { ip ->
                markProvisioned(activity)
                _state.value = State(Phase.CONNECTED, "Verbunden · Fernwartung bereit", ip, true)
                return@launch
            }

            if (isProvisioned(activity) && current?.BackendState != "NeedsLogin") {
                _state.value = State(Phase.CONNECTING, "Gespeicherte Tailscale-Identität wird verbunden …")
                requestVpnAndStart()
                return@launch
            }

            _state.value = State(Phase.FINDING_RASPBERRY, "Raspberry epimedia wird im Heimnetz gesucht …")
            val healthOk = withContext(Dispatchers.IO) { checkProvisioner() }
            if (!healthOk) {
                _state.value = State(
                    Phase.ERROR,
                    "Raspberry-Provisioner nicht erreichbar. Ersteinrichtung muss einmal im Heimnetz erfolgen.",
                    lastError = "raspberry_unreachable"
                )
                return@launch
            }

            _state.value = State(Phase.REQUESTING_ACCESS, "Einmaligen Tailscale-Zugang vom Raspberry anfordern …", raspberryReachable = true)
            val enrollment = runCatching {
                withContext(Dispatchers.IO) { requestEnrollment(activity, remotePin) }
            }.getOrElse { e ->
                _state.value = State(
                    Phase.ERROR,
                    when (e.message) {
                        "bad_remote_pin" -> "Fernwartungs-PIN wurde vom Raspberry abgelehnt."
                        else -> "Tailscale-Zugang konnte nicht erstellt werden."
                    },
                    raspberryReachable = true,
                    lastError = e.message.orEmpty()
                )
                return@launch
            }

            _state.value = State(Phase.ENROLLING, "Gerät wird automatisch im Tailnet registriert …", raspberryReachable = true)
            runCatching { loginWithAuthKey(enrollment.authKey, enrollment.controlUrl) }
                .onFailure { e ->
                    _state.value = State(
                        Phase.ERROR,
                        "Tailscale-Anmeldung fehlgeschlagen.",
                        raspberryReachable = true,
                        lastError = e.message.orEmpty()
                    )
                    return@launch
                }

            markProvisioned(activity)
            _state.value = State(Phase.CONNECTING, "Tailscale ist eingerichtet · Verbindung wird gestartet …", raspberryReachable = true)
            requestVpnAndStart()
        }
    }

    fun retry() {
        ensureConnected()
    }

    fun disconnect() {
        activeJob?.cancel()
        runCatching { App.get().stopVPN() }
        pendingStartAfterPermission = false
        _state.value = State(Phase.IDLE, "Fernwartung ist gesperrt.")
    }

    fun onVpnPermissionResult(granted: Boolean) {
        if (!pendingStartAfterPermission) return
        if (!granted) {
            pendingStartAfterPermission = false
            _state.value = State(
                Phase.ERROR,
                "Android-VPN-Freigabe wurde nicht erteilt.",
                lastError = "vpn_permission_denied"
            )
            return
        }
        pendingStartAfterPermission = false
        scope.launch { startVpnAndWait() }
    }

    private suspend fun requestVpnAndStart() {
        val activity = activityRef.get() ?: throw IllegalStateException("no_activity")
        val prepareIntent = VpnService.prepare(activity)
        if (prepareIntent != null) {
            pendingStartAfterPermission = true
            _state.value = State(
                Phase.VPN_PERMISSION,
                "Einmalige Android-VPN-Freigabe bestätigen. Danach verbindet EpiMediaHub automatisch."
            )
            permissionLauncher?.invoke(prepareIntent)
            return
        }
        startVpnAndWait()
    }

    private suspend fun startVpnAndWait() {
        _state.value = _state.value.copy(phase = Phase.CONNECTING, message = "Tailscale verbindet …")
        App.get().startVPN()
        repeat(30) {
            delay(1000L)
            val current = runCatching { status() }.getOrNull()
            val ip = connectedIp(current)
            if (ip != null) {
                val raspberryOnline = current?.Peer?.values?.any { peer ->
                    peer.TailscaleIPs?.any { it == "100.96.157.82" } == true && peer.Online
                } == true
                _state.value = State(
                    Phase.CONNECTED,
                    if (raspberryOnline) "Verbunden · Raspberry erreichbar" else "Verbunden · Tailnet aktiv",
                    tailscaleIp = ip,
                    raspberryReachable = raspberryOnline
                )
                return
            }
        }
        _state.value = State(
            Phase.ERROR,
            "Tailscale hat innerhalb von 30 Sekunden keine Verbindung hergestellt.",
            lastError = "connect_timeout"
        )
    }

    private suspend fun status(): IpnState.Status =
        awaitResult { callback -> Client(App.get().applicationScope).status(callback) }

    private fun connectedIp(status: IpnState.Status?): String? {
        if (status == null || status.BackendState != "Running") return null
        return status.TailscaleIPs?.firstOrNull { ip -> ip.startsWith("100.") }
    }

    private suspend fun loginWithAuthKey(authKey: String, controlUrl: String) {
        val app = App.get()
        app.startForegroundForLogin()
        val client = Client(app.applicationScope)
        val maskedPrefs = Ipn.MaskedPrefs().apply {
            ControlURL = controlUrl
            LoggedOut = false
        }
        val prefs: Ipn.Prefs = awaitResult { callback -> client.editPrefs(maskedPrefs, callback) }
        prefs.WantRunning = true
        val options = Ipn.Options(UpdatePrefs = prefs, AuthKey = authKey)
        awaitResult<Unit> { callback -> client.start(options, callback) }
        awaitResult<Unit> { callback -> client.startLoginInteractive(callback) }
    }

    private suspend fun <T> awaitResult(call: (((Result<T>) -> Unit)) -> Unit): T {
        val deferred = CompletableDeferred<Result<T>>()
        call { result -> if (!deferred.isCompleted) deferred.complete(result) }
        return deferred.await().getOrThrow()
    }

    private fun checkProvisioner(): Boolean = try {
        val conn = (URL(PROVISIONER_HEALTH).openConnection() as HttpURLConnection).apply {
            connectTimeout = 2500
            readTimeout = 2500
            requestMethod = "GET"
            useCaches = false
        }
        try { conn.responseCode == 200 } finally { conn.disconnect() }
    } catch (_: Exception) {
        false
    }

    private data class Enrollment(val authKey: String, val controlUrl: String)

    private fun requestEnrollment(context: Context, pin: String): Enrollment {
        val installId = installationId(context)
        val model = Build.MODEL.orEmpty().replace(Regex("[^A-Za-z0-9_-]+"), "-").take(32)
        val body = JSONObject()
            .put("pin", pin)
            .put("deviceName", "epimediahub-$model-${installId.takeLast(6)}")
            .put("installId", installId)
            .toString()
            .toByteArray()
        val conn = (URL(PROVISIONER_URL).openConnection() as HttpURLConnection).apply {
            connectTimeout = 5000
            readTimeout = 15000
            requestMethod = "POST"
            doOutput = true
            useCaches = false
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "EpiMediaHub-Android/0.4.7")
        }
        try {
            conn.outputStream.use { it.write(body) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val payload = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            val json = JSONObject(payload.ifBlank { "{}" })
            if (code !in 200..299) throw IllegalStateException(json.optString("error", "http_$code"))
            val key = json.optString("authKey")
            if (!key.startsWith("tskey-")) throw IllegalStateException("missing_auth_key")
            return Enrollment(key, json.optString("controlUrl", "https://controlplane.tailscale.com"))
        } finally {
            conn.disconnect()
        }
    }

    private fun installationId(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val current = prefs.getString(KEY_INSTALL_ID, null)
        if (!current.isNullOrBlank()) return current
        val generated = UUID.randomUUID().toString()
        prefs.edit().putString(KEY_INSTALL_ID, generated).apply()
        return generated
    }

    private fun markProvisioned(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putBoolean(KEY_PROVISIONED, true).apply()
    }
}
