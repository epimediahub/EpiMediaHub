#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


# ---------------------------------------------------------------------------
# Version metadata.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
require_once(s, 'versionCode = 49', 'v0.4.9 versionCode')
require_once(s, 'versionName = "0.4.9"', 'v0.4.9 versionName')
s = s.replace('versionCode = 49', 'versionCode = 50', 1)
s = s.replace('versionName = "0.4.9"', 'versionName = "0.4.10"', 1)
gradle.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.4.9", "0.4.10"))


# ---------------------------------------------------------------------------
# Replace the Raspberry HTTP/OAuth bootstrap with Tailscale's own interactive
# login flow. The embedded runtime is the official Tailscale Android runtime.
# Tailscale itself supplies BrowseToURL/LoginFinished; no raw WireGuard config,
# no auth key in the APK, and no Raspberry LAN provisioner are involved.
# ---------------------------------------------------------------------------
remote = java / "RemoteTailscaleManager.kt"
remote.write_text(r'''package de.epimediahub.app

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.VpnService
import com.tailscale.ipn.App
import com.tailscale.ipn.ui.localapi.Client
import com.tailscale.ipn.ui.model.Ipn
import com.tailscale.ipn.ui.model.IpnState
import com.tailscale.ipn.ui.notifier.Notifier
import java.lang.ref.WeakReference
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

/**
 * Embedded Tailscale controller for EpiMediaHub remote maintenance.
 *
 * v0.4.10 uses Tailscale's native interactive login, matching the Enigma flow:
 * the Tailscale backend produces its own login URL, the TV shows it as a QR
 * code, and after account approval the official Tailscale Android VpnService
 * carries the connection. There is deliberately no manual WireGuard setup and
 * no Raspberry HTTP/OAuth bootstrap in this path.
 */
object RemoteTailscaleManager {
    enum class Phase {
        IDLE,
        CHECKING,
        AUTH_REQUIRED,
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
        val authUrl: String = "",
        val raspberryReachable: Boolean = false,
        val raspberryName: String = "",
        val raspberryIp: String = "",
        val lastError: String = "",
        val backendState: String = ""
    )

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
            val activity = activityRef.get() ?: return
            if (VpnService.prepare(activity) == null && pendingStartAfterPermission) {
                onVpnPermissionResult(true)
            }
        }
    }

    fun isProvisioned(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_PROVISIONED, false)

    fun ensureConnected() {
        val activity = activityRef.get() ?: return
        if (activeJob?.isActive == true) return
        activeJob = scope.launch {
            _state.value = _state.value.copy(
                phase = Phase.CHECKING,
                message = "Tailscale-Status wird geprüft …",
                lastError = ""
            )
            val current = runCatching { status() }.getOrNull()
            connectedIp(current)?.let { ip ->
                markProvisioned(activity)
                _state.value = connectedState(current, ip)
                return@launch
            }

            if (current?.BackendState == "NeedsLogin" || !isProvisioned(activity)) {
                _state.value = State(
                    phase = Phase.PIN_REQUIRED,
                    message = "Tailscale muss einmalig direkt angemeldet werden. Fernwartungs-PIN eingeben.",
                    lastError = if (current?.BackendState == "NeedsLogin") "needs_login" else "tailscale_login_required",
                    backendState = current?.BackendState.orEmpty()
                )
                return@launch
            }

            _state.value = _state.value.copy(
                phase = Phase.CONNECTING,
                message = "Gespeicherte Tailscale-Identität wird verbunden …",
                authUrl = "",
                backendState = current?.BackendState.orEmpty()
            )
            requestVpnAndStart()
        }
    }

    /**
     * The PIN was already verified by MainViewModel. It remains a local
     * EpiMediaHub gate only; Tailscale authentication itself is performed by
     * Tailscale's native interactive login/QR flow.
     */
    @Suppress("UNUSED_PARAMETER")
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
                _state.value = connectedState(current, ip)
                return@launch
            }

            // A known, still-valid Tailscale identity only needs the VPN tunnel.
            if (isProvisioned(activity) && current?.BackendState != "NeedsLogin") {
                _state.value = State(
                    phase = Phase.CONNECTING,
                    message = "Gespeicherte Tailscale-Identität wird verbunden …",
                    backendState = current?.BackendState.orEmpty()
                )
                requestVpnAndStart()
                return@launch
            }

            startInteractiveTailscaleLogin(activity)
        }
    }

    fun retry() {
        val activity = activityRef.get() ?: return
        if (isProvisioned(activity)) ensureConnected()
        else _state.value = State(
            Phase.PIN_REQUIRED,
            "Tailscale-Anmeldung erforderlich. Fernwartungs-PIN eingeben.",
            lastError = "tailscale_login_required"
        )
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

    private suspend fun startInteractiveTailscaleLogin(activity: Activity) {
        _state.value = State(
            phase = Phase.CHECKING,
            message = "Tailscale erstellt den sicheren Anmeldelink …",
            backendState = "NeedsLogin"
        )

        val app = App.get()
        val client = Client(app.applicationScope)
        val loginFinishedBefore = Notifier.loginFinished.value

        runCatching {
            app.startForegroundForLogin()
            val prefs: Ipn.Prefs = awaitResult { callback ->
                client.editPrefs(Ipn.MaskedPrefs(), callback)
            }
            prefs.WantRunning = true
            awaitResult<Unit> { callback ->
                client.start(Ipn.Options(UpdatePrefs = prefs), callback)
            }
            // Tailscale Android requires this call for interactive login and
            // also uses it for auth-key login internally.
            awaitResult<Unit> { callback -> client.startLoginInteractive(callback) }
        }.onFailure { error ->
            _state.value = State(
                Phase.ERROR,
                "Tailscale-Anmeldung konnte nicht gestartet werden.",
                lastError = error.message.orEmpty()
            )
            return
        }

        var lastUrl = ""
        repeat(600) { // five minutes for QR/browser approval
            delay(500L)
            val current = runCatching { status() }.getOrNull()
            val url = loginUrl(current)
            if (url.isNotBlank() && url != lastUrl) {
                lastUrl = url
                _state.value = State(
                    phase = Phase.AUTH_REQUIRED,
                    message = "QR-Code mit einem Gerät öffnen, das bei deinem Tailscale-Konto angemeldet ist, und dieses Gerät freigeben.",
                    authUrl = url,
                    backendState = current?.BackendState.orEmpty()
                )
            }

            val finished = Notifier.loginFinished.value
            val loginCompleted =
                (!finished.isNullOrBlank() && finished != loginFinishedBefore) ||
                current?.Self != null ||
                current?.TailscaleIPs?.any { it.startsWith("100.") } == true

            if (loginCompleted && current?.BackendState != "NeedsLogin") {
                markProvisioned(activity)
                _state.value = _state.value.copy(
                    phase = Phase.CONNECTING,
                    message = "Tailscale-Anmeldung bestätigt · VPN-Verbindung wird gestartet …",
                    authUrl = "",
                    backendState = current?.BackendState.orEmpty()
                )
                requestVpnAndStart()
                return
            }
        }

        _state.value = State(
            Phase.ERROR,
            if (lastUrl.isBlank()) "Tailscale hat keinen Anmeldelink geliefert." else "Tailscale-Freigabe wurde nicht innerhalb von 5 Minuten abgeschlossen.",
            authUrl = lastUrl,
            lastError = if (lastUrl.isBlank()) "no_tailscale_login_url" else "tailscale_login_timeout"
        )
    }

    private fun loginUrl(status: IpnState.Status?): String {
        val notified = Notifier.browseToURL.value.orEmpty().trim()
        if (notified.startsWith("https://login.tailscale.com/")) return notified
        val fromStatus = status?.AuthURL.orEmpty().trim()
        if (fromStatus.startsWith("https://login.tailscale.com/")) return fromStatus
        return ""
    }

    private suspend fun requestVpnAndStart() {
        val activity = activityRef.get() ?: throw IllegalStateException("no_activity")
        val prepareIntent = VpnService.prepare(activity)
        if (prepareIntent != null) {
            pendingStartAfterPermission = true
            _state.value = _state.value.copy(
                phase = Phase.VPN_PERMISSION,
                message = "Einmalige Android-VPN-Freigabe für Tailscale bestätigen.",
                authUrl = ""
            )
            permissionLauncher?.invoke(prepareIntent)
            return
        }
        startVpnAndWait()
    }

    private suspend fun startVpnAndWait() {
        _state.value = _state.value.copy(
            phase = Phase.CONNECTING,
            message = "Tailscale verbindet …",
            authUrl = ""
        )
        App.get().startVPN()
        repeat(45) {
            delay(1000L)
            val current = runCatching { status() }.getOrNull()
            if (current?.BackendState == "NeedsLogin") {
                _state.value = State(
                    phase = Phase.PIN_REQUIRED,
                    message = "Tailscale-Anmeldung ist abgelaufen. Fernwartungs-PIN eingeben und erneut per Tailscale freigeben.",
                    lastError = "needs_login",
                    backendState = current.BackendState.orEmpty()
                )
                return
            }
            val ip = connectedIp(current)
            if (ip != null) {
                activityRef.get()?.let { markProvisioned(it) }
                _state.value = connectedState(current, ip)
                return
            }
        }
        val finalStatus = runCatching { status() }.getOrNull()
        _state.value = State(
            Phase.ERROR,
            "Tailscale hat innerhalb von 45 Sekunden keine Verbindung hergestellt.",
            lastError = "tailscale_connect_timeout",
            backendState = finalStatus?.BackendState.orEmpty()
        )
    }

    private fun connectedState(status: IpnState.Status?, ip: String): State {
        val raspberry = findRaspberryPeer(status)
        val raspberryIp = raspberry?.TailscaleIPs?.firstOrNull { it.startsWith("100.") }.orEmpty()
        val raspberryName = raspberry?.HostName?.ifBlank {
            raspberry.DNSName.substringBefore('.').ifBlank { "Raspberry" }
        }.orEmpty()
        val online = raspberry?.Online == true
        return State(
            phase = Phase.CONNECTED,
            message = when {
                online -> "Tailscale verbunden · Raspberry $raspberryName erreichbar"
                raspberry != null -> "Tailscale verbunden · Raspberry $raspberryName ist im Tailnet, aber offline"
                else -> "Tailscale verbunden · Raspberry im Tailnet noch nicht gefunden"
            },
            tailscaleIp = ip,
            raspberryReachable = online,
            raspberryName = raspberryName,
            raspberryIp = raspberryIp,
            backendState = status?.BackendState.orEmpty()
        )
    }

    private fun findRaspberryPeer(status: IpnState.Status?): IpnState.PeerStatus? {
        val peers = status?.Peer?.values.orEmpty()
        fun firstLabel(peer: IpnState.PeerStatus): String =
            peer.DNSName.trim('.').substringBefore('.').lowercase()
        return peers.firstOrNull { peer ->
            peer.HostName.equals("epimedia", ignoreCase = true) || firstLabel(peer) == "epimedia"
        } ?: peers.firstOrNull { peer ->
            peer.HostName.lowercase().startsWith("raspberry") || firstLabel(peer).startsWith("raspberry")
        }
    }

    private suspend fun status(): IpnState.Status =
        awaitResult { callback -> Client(App.get().applicationScope).status(callback) }

    private fun connectedIp(status: IpnState.Status?): String? {
        if (status == null || status.BackendState != "Running") return null
        return status.TailscaleIPs?.firstOrNull { ip -> ip.startsWith("100.") }
    }

    private suspend fun <T> awaitResult(call: (((Result<T>) -> Unit)) -> Unit): T {
        val deferred = CompletableDeferred<Result<T>>()
        call { result -> if (!deferred.isCompleted) deferred.complete(result) }
        return deferred.await().getOrThrow()
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
        installationId(context)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putBoolean(KEY_PROVISIONED, true).apply()
    }
}
''')


# ---------------------------------------------------------------------------
# Remote-maintenance screen: show Tailscale's own login URL as a QR code and
# make the wording explicit that the Raspberry provisioner is no longer used.
# ---------------------------------------------------------------------------
web = java / "ui/V047WebAdmin.kt"
s = web.read_text()

replacements = {
    "Die separate Fernwartungs-PIN startet die automatische Tailscale-Einrichtung über deinen Raspberry. Kein Router-Port wird geöffnet.":
        "Die separate Fernwartungs-PIN startet die direkte Tailscale-Anmeldung. Kein WireGuard-Profil und kein Router-Port wird manuell eingerichtet.",
    "Fernwartung automatisch einrichten": "Tailscale-Fernwartung einrichten",
    "TAILSCALE · RASPBERRY": "TAILSCALE · DIREKTVERBINDUNG",
    "Bitte den einmaligen Android-VPN-Dialog bestätigen. Danach sind keine weiteren Tailscale-Anmeldungen nötig.":
        "Bitte den Android-VPN-Dialog für Tailscale bestätigen. Die Anmeldung selbst erfolgt direkt über dein Tailscale-Konto.",
    "Fernwartungs-PIN eingeben. EpiMediaHub sucht danach automatisch deinen Raspberry, holt einen einmaligen Tailscale-Zugang und verbindet dieses Gerät.":
        "Fernwartungs-PIN eingeben. Danach zeigt EpiMediaHub den offiziellen Tailscale-QR-Code zur einmaligen Freigabe dieses Geräts.",
}
for old, new in replacements.items():
    require_once(s, old, f"remote wording: {old[:32]}")
    s = s.replace(old, new, 1)

old_status = '''                                Text(ts.message, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)\n\n                                if (effectiveRemoteUrl.isNotBlank()) {'''
require_once(s, old_status, "Tailscale status block")
new_status = '''                                Text(ts.message, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)\n\n                                if (ts.phase == RemoteTailscaleManager.Phase.AUTH_REQUIRED && ts.authUrl.isNotBlank()) {\n                                    Spacer(Modifier.height(6.dp))\n                                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {\n                                        ParityQrCode(ts.authUrl)\n                                        Column(Modifier.weight(1f)) {\n                                            Text("TAILSCALE ANMELDUNG", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black)\n                                            SelectionContainer { Text(ts.authUrl, color = Color.White, fontSize = 11.sp, lineHeight = 14.sp) }\n                                            Text("QR-Code scannen und das Gerät im gleichen Tailscale-Tailnet wie den Raspberry freigeben.", color = Color.White.copy(.74f), fontSize = 10.sp, lineHeight = 13.sp)\n                                        }\n                                    }\n                                } else if (effectiveRemoteUrl.isNotBlank()) {'''
s = s.replace(old_status, new_status, 1)

old_remote_hint = '''                                    Text("Automatisch verbunden · nur im Tailnet erreichbar", color = Color.White.copy(.74f), fontSize = 11.sp)'''
require_once(s, old_remote_hint, "remote URL hint")
new_remote_hint = '''                                    Text("Direkt über Tailscale verbunden · nur im Tailnet erreichbar", color = Color.White.copy(.74f), fontSize = 11.sp)\n                                    if (ts.raspberryName.isNotBlank()) {\n                                        Text(\n                                            "Raspberry: ${ts.raspberryName}" + if (ts.raspberryIp.isNotBlank()) " · ${ts.raspberryIp}" else "",\n                                            color = if (ts.raspberryReachable) accent else Color.White.copy(.66f),\n                                            fontSize = 10.sp,\n                                            fontWeight = FontWeight.Bold\n                                        )\n                                    }'''
s = s.replace(old_remote_hint, new_remote_hint, 1)
web.write_text(s)

print("Android v0.4.10 direct native Tailscale login patch applied")
