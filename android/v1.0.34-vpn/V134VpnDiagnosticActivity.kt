package de.epimediahub.app.vpn

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.VpnService
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import de.epimediahub.app.MainActivity
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/** Isolated tester activity. No VPN credentials bundled, persisted or logged. */
class V134VpnDiagnosticActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var status: TextView
    private lateinit var openPlayer: Button
    private lateinit var vpnButton: Button
    private lateinit var directButton: Button
    private var route = "blocked"
    private var busy = false

    companion object {
        private const val REQUEST_FILE = 5133
        private const val REQUEST_CONSENT = 5134
        private const val FINLAND_IP = "37.27.42.215"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 24, 36, 24)
            setBackgroundColor(Color.rgb(7, 17, 29))
        }
        fun label(content: String, font: Float) {
            layout.addView(TextView(this).apply {
                text = content
                textSize = font
                setTextColor(Color.WHITE)
                setPadding(0, 10, 0, 14)
            })
        }
        fun action(content: String, click: () -> Unit): Button {
            return Button(this).apply {
                text = content
                textSize = 16f
                isAllCaps = false
                minHeight = 64
                setOnClickListener { click() }
                layout.addView(this)
            }
        }
        label("EPIMEDIAHUB · FINLAND VPN BETA", 23f)
        label("Separate Testinstallation. WireGuard-Profil wird nach dem ersten Import verschlüsselt und gerätegebunden gespeichert.", 15f)
        status = TextView(this).apply {
            textSize = 17f
            setTextColor(Color.WHITE)
            setPadding(0, 18, 0, 24)
        }
        layout.addView(status)
        action("VPN-Profil vom Fire TV laden (ADB)") { importLocalProfile() }
        action("Gespeichertes VPN-Profil löschen") {
            android.app.AlertDialog.Builder(this)
                .setTitle("Gespeichertes VPN-Profil löschen?")
                .setMessage("Der verschlüsselte WireGuard-Schlüssel wird auf diesem Fire TV entfernt. Für eine erneute Finnland-Verbindung ist ein neuer Import nötig.")
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Profil löschen") { _, _ ->
                    work({
                        V134VpnSession.eraseProfile(applicationContext)
                        "Profil gelöscht"
                    }, {
                        route = "blocked"
                        setStatus("VPN-Profil gelöscht. Für Finnland erneut importieren.")
                    })
                }.show()
        }
        action("Anderes VPN-Profil auswählen") {
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
            }
            val handlerAvailable = intent.resolveActivity(packageManager) != null
            if (!handlerAvailable) {
                setStatus("Fire TV bietet keine Dateiauswahl. Bitte die ADB-Importtaste darüber verwenden.")
            } else {
                runCatching { startActivityForResult(intent, REQUEST_FILE) }
                    .onFailure { setStatus("Dateiauswahl nicht verfügbar. Bitte über ADB importieren.") }
            }
        }
        vpnButton = action("VPN Finnland verbinden und prüfen") { startVpn() }
        directButton = action("Direktverbindung herstellen und prüfen") { startDirect() }
        openPlayer = action("Testplayer öffnen") {
            if (route != "blocked" && !busy) startActivity(Intent(this, MainActivity::class.java))
            else setStatus("Route nicht bestätigt. Player bleibt gesperrt.")
        }
        label("Keine Freigabe für Kunden. Der Android-VPN-Dialog erfordert deine Zustimmung. Verwende niemals den privaten VPN-Schlüssel in GitHub oder Screenshots.", 13f)
        // Android 11+ may deny adb shell access to Android/data even for this app.
        // Android/media is intended only as a short-lived ADB handoff; delete on import.
        runCatching { getExternalFilesDir(null) }
        runCatching { getExternalMediaDirs().firstOrNull()?.mkdirs() }
        setContentView(ScrollView(this).apply { addView(layout) })
        setStatus(if (V134VpnSession.hasProfile(applicationContext))
            "Verschlüsseltes Finnland-Profil vorhanden. Bitte VPN verbinden und prüfen."
        else "Noch kein VPN-Profil gespeichert. Bitte einmal per ADB importieren.")
    }

    private fun setStatus(text: String) {
        status.text = text
        openPlayer.isEnabled = route != "blocked" && !busy
        vpnButton.isEnabled = !busy
        directButton.isEnabled = !busy
    }

    private fun work(task: () -> String, success: (String) -> Unit) {
        if (busy) return
        busy = true
        route = "blocked"
        setStatus("Route wird überprüft …")
        thread(name = "vpn-beta-test") {
            val result = runCatching { task() }
            handler.post {
                busy = false
                result.onSuccess(success).onFailure {
                    route = "blocked"
                    setStatus("Vorgang fehlgeschlagen: " + (it.message ?: it.javaClass.simpleName).take(135))
                }
            }
        }
    }

    private fun importLocalProfile() {
        val privateDirectory = getExternalFilesDir(null)
        val adbMediaDirectory = runCatching { getExternalMediaDirs().firstOrNull() }.getOrNull()
        val files = listOfNotNull(privateDirectory, adbMediaDirectory)
            .map { File(it, "epi-test-01.conf") }
        val file = files.firstOrNull { it.isFile }
        if (file == null) {
            setStatus(
                "VPN-Datei fehlt. ADB-Ziel: /sdcard/Android/media/" +
                    packageName + "/epi-test-01.conf"
            )
            return
        }
        work({
            require(file.length() in 150L..12_000L) { "Ungültige Profildateigröße" }
            file.inputStream().buffered().use { input ->
                val buffer = input.readBytes()
                betaProfile(buffer.toString(Charsets.UTF_8)).also { config ->
                    V134VpnSession.storeProfile(applicationContext, config)
                }
            }
        }, {
            val erased = file.delete()
            route = "blocked"
            setStatus(if (erased)
                "Finnland-Testprofil verschlüsselt gespeichert und temporäre Datei gelöscht. VPN jetzt verbinden."
            else "Finnland-Testprofil verschlüsselt gespeichert. Bitte temporäre Importdatei per ADB löschen.")
        })
    }

    private fun startVpn() {
        if (!V134VpnSession.hasProfile(applicationContext)) {
            setStatus("Bitte zuerst ein eigenes Finnland-Testprofil importieren.")
            return
        }
        route = "blocked"
        val consent = VpnService.prepare(this)
        if (consent != null) {
            setStatus("Android-VPN-Einwilligung bestätigen.")
            startActivityForResult(consent, REQUEST_CONSENT)
        } else connectAndCheck()
    }

    private fun connectAndCheck() {
        work({ V134VpnSession.connectAndVerify(applicationContext) }, { ip ->
            route = "finland"
            setStatus("FINNLAND VPN bestätigt · Ausgang: " + ip + ". Testplayer bereit.")
        })
    }

    private fun startDirect() {
        work({ V134VpnSession.disconnectAndVerify(applicationContext) }, { ip ->
            route = "direct"
            setStatus("DIREKT bestätigt · Ausgang: " + ip + ". Testplayer bereit.")
        })
    }

    @Deprecated("Compatibility with Fire OS Activity result API")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_FILE && resultCode == RESULT_OK) {
            val uri = data?.data ?: return
            work({
                val bytes = contentResolver.openInputStream(uri)?.use { stream ->
                    stream.readBytes().also { require(it.size in 150..12000) }
                } ?: error("Datei nicht lesbar")
                betaProfile(bytes.toString(Charsets.UTF_8)).also { config ->
                    V134VpnSession.storeProfile(applicationContext, config)
                }
            }, {
                route = "blocked"
                setStatus("Finnland-Profil verschlüsselt gespeichert. Bitte VPN verbinden.")
            })
        } else if (requestCode == REQUEST_CONSENT) {
            if (resultCode == RESULT_OK) connectAndCheck()
            else { route = "blocked"; setStatus("VPN-Einwilligung verweigert.") }
        }
    }

    private fun betaProfile(raw: String): String {
        val text = raw.replace("\r\n", "\n")
        require(text.contains(Regex("(?m)^\\[Interface\\]$")))
        require(text.contains(Regex("(?m)^\\[Peer\\]$")))
        require(text.contains(Regex("(?mi)^Endpoint\\s*=\\s*37\\.27\\.42\\.215:51820\\s*$")))
        require(text.contains(Regex("(?mi)^AllowedIPs\\s*=.*0\\.0\\.0\\.0/0.*::/0")))
        require(!text.contains(Regex("(?mi)^\\s*(IncludedApplications|ExcludedApplications)\\s*=")))
        require(text.length in 150..11800)
        return text.replaceFirst("[Interface]", "[Interface]\nIncludedApplications = " + packageName)
    }

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized && !busy) {
            V134VpnSession.block()
            route = "blocked"
            setStatus(if (V134VpnSession.hasProfile(applicationContext))
                "Finnland-Profil verschlüsselt gespeichert. VPN bitte verbinden und prüfen."
            else "Kein gespeichertes Finnland-Profil. Bitte einmalig importieren.")
        }
    }
}
