#!/usr/bin/env python3
from pathlib import Path
import os
import xml.etree.ElementTree as ET

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"
gradle = root / "app/build.gradle.kts"

s = gradle.read_text()
if 'versionCode = 55' not in s or 'versionName = "0.4.15"' not in s:
    raise SystemExit("v0.4.15 version anchors missing")
gradle.write_text(
    s.replace('versionCode = 55', 'versionCode = 56', 1)
     .replace('versionName = "0.4.15"', 'versionName = "0.4.16"', 1)
)
for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.4.15", "0.4.16"))

# Turn provisioning into a real first-launch flow without depending on the
# Compose navigation structure. We move the launch intent-filter from the
# existing launcher activity to a tiny native gate activity. Once a valid
# provisioning session exists, the gate immediately opens the original app.
manifest = root / "app/src/main/AndroidManifest.xml"
ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
ANDROID = "{http://schemas.android.com/apk/res/android}"
tree = ET.parse(manifest)
root_el = tree.getroot()
app = root_el.find("application")
if app is None:
    raise SystemExit("AndroidManifest application element missing")

launcher_activity = None
launcher_filter = None
for activity in app.findall("activity"):
    for intent_filter in activity.findall("intent-filter"):
        actions = {x.get(ANDROID + "name", "") for x in intent_filter.findall("action")}
        categories = {x.get(ANDROID + "name", "") for x in intent_filter.findall("category")}
        if "android.intent.action.MAIN" in actions and (
            "android.intent.category.LAUNCHER" in categories or
            "android.intent.category.LEANBACK_LAUNCHER" in categories
        ):
            launcher_activity = activity
            launcher_filter = intent_filter
            break
    if launcher_activity is not None:
        break

if launcher_activity is None or launcher_filter is None:
    raise SystemExit("existing launcher activity/intent-filter missing")

original_name = launcher_activity.get(ANDROID + "name", "")
if not original_name:
    raise SystemExit("launcher activity name missing")

# Remove the launcher filter from the real activity, but preserve all of its
# categories/data by attaching the exact same filter to the gate.
launcher_activity.remove(launcher_filter)

gate = ET.Element("activity")
gate.set(ANDROID + "name", "de.epimediahub.app.ProvisioningGateActivity")
gate.set(ANDROID + "exported", "true")
if launcher_activity.get(ANDROID + "theme"):
    gate.set(ANDROID + "theme", launcher_activity.get(ANDROID + "theme"))
gate.append(launcher_filter)
app.append(gate)
app.set(ANDROID + "usesCleartextTraffic", "true")
tree.write(manifest, encoding="utf-8", xml_declaration=True)

# Native Android setup screen, intentionally dependency-light for Fire TV.
(java / "ProvisioningGateActivity.kt").write_text(r'''package de.epimediahub.app

import android.app.Activity
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import de.epimediahub.app.data.SetupCodeProvisioning
import de.epimediahub.app.data.SetupCodeResult

class ProvisioningGateActivity : Activity() {
    companion object {
        private const val DEFAULT_SERVER = "http://100.96.157.82:8787"
        private const val ORIGINAL_ACTIVITY = "__ORIGINAL_ACTIVITY__"
    }

    private lateinit var codeInput: EditText
    private lateinit var serverInput: EditText
    private lateinit var statusText: TextView
    private lateinit var connectButton: Button
    private lateinit var progress: ProgressBar

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!SetupCodeProvisioning.sessionToken(this).isNullOrBlank()) {
            openMain()
            return
        }
        showGate()
    }

    private fun showGate() {
        val pad = (24 * resources.displayMetrics.density).toInt()
        val gap = (12 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(pad, pad, pad, pad)
        }

        root.addView(TextView(this).apply {
            text = "EpiMediaHub verbinden"
            textSize = 26f
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = gap })

        root.addView(TextView(this).apply {
            text = "Gib den Einrichtungscode aus dem EpiMediaHub Admin-Dashboard ein. Danach wird dieser Fire TV automatisch als Gerät registriert."
            textSize = 17f
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = gap * 2 })

        serverInput = EditText(this).apply {
            hint = "Provisionierungsserver"
            setText(SetupCodeProvisioning.provisioningBaseUrl(this@ProvisioningGateActivity) ?: DEFAULT_SERVER)
            isSingleLine = true
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        root.addView(serverInput, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = gap })

        codeInput = EditText(this).apply {
            hint = "z. B. EPI7-K4M9-2ABC"
            isSingleLine = true
            textSize = 22f
            gravity = Gravity.CENTER
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
        }
        root.addView(codeInput, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = gap })

        progress = ProgressBar(this).apply { visibility = View.GONE }
        root.addView(progress, LinearLayout.LayoutParams(-2, -2).apply { gravity = Gravity.CENTER_HORIZONTAL; bottomMargin = gap })

        statusText = TextView(this).apply {
            text = "Noch nicht mit dem Admin-Dashboard verbunden."
            textSize = 15f
            gravity = Gravity.CENTER
        }
        root.addView(statusText, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = gap })

        connectButton = Button(this).apply {
            text = "Mit Einrichtungscode verbinden"
            setOnClickListener { connect() }
        }
        root.addView(connectButton, LinearLayout.LayoutParams(-1, -2))

        setContentView(root)
    }

    private fun connect() {
        val baseUrl = serverInput.text.toString().trim()
        val code = codeInput.text.toString().trim()
        if (!SetupCodeProvisioning.isValid(code)) {
            statusText.text = "Einrichtungscode ist ungültig."
            return
        }
        setBusy(true, "Gerät wird registriert …")
        Thread {
            val result = SetupCodeProvisioning.redeem(this, baseUrl, code)
            runOnUiThread {
                when (result) {
                    is SetupCodeResult.Success -> {
                        statusText.text = "Gerät registriert. Konfiguration wird synchronisiert …"
                        Thread {
                            runCatching { SetupCodeProvisioning.sync(this) }
                            runOnUiThread { openMain() }
                        }.start()
                    }
                    is SetupCodeResult.Error -> setBusy(false, result.message)
                }
            }
        }.start()
    }

    private fun setBusy(busy: Boolean, message: String) {
        codeInput.isEnabled = !busy
        serverInput.isEnabled = !busy
        connectButton.isEnabled = !busy
        progress.visibility = if (busy) View.VISIBLE else View.GONE
        statusText.text = message
    }

    private fun openMain() {
        val target = if (ORIGINAL_ACTIVITY.startsWith(".")) packageName + ORIGINAL_ACTIVITY else ORIGINAL_ACTIVITY
        startActivity(Intent().setClassName(this, target).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP))
        finish()
    }
}
'''.replace("__ORIGINAL_ACTIVITY__", original_name))

print(f"Android v0.4.16 provisioning gate installed; original launcher={original_name}")
