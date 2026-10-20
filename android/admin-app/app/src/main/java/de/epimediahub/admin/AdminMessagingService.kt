package de.epimediahub.admin

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class AdminMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        super.onNewToken(token)
        // Registration is revalidated on the next explicit admin action.
        // Never log the credential-like FCM token or guess a web login.
        getSharedPreferences("admin-push", MODE_PRIVATE)
            .edit().putBoolean("registered", false).apply()
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        val kind = message.data["kind"] ?: return
        val allowed = setOf(
            "analysis_stalled", "playlist_access", "worker_preflight",
            "service_down", "build_failed", "playback_errors", "daily_report",
            "expiry_monthly", "expiry_weekly"
        )
        if (kind !in allowed) return
        val channelId = "epi-admin-alerts"
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(channelId, "EpiMediaHub Admin Alarme", NotificationManager.IMPORTANCE_HIGH)
        )
        val descriptions = mapOf(
            "analysis_stalled" to "EpiScene benötigt Aufmerksamkeit",
            "playlist_access" to "Ein Analysezugang benötigt Aufmerksamkeit",
            "worker_preflight" to "Ein Analyse-Worker benötigt Aufmerksamkeit",
            "service_down" to "Server-/API-Status prüfen",
            "build_failed" to "App-Build oder Update prüfen",
            "playback_errors" to "Kundenwiedergabe prüfen",
            "daily_report" to "EpiScene-Tagesbericht ist verfügbar",
            "expiry_monthly" to "Die Monatsübersicht ist zum Drucken bereit",
            "expiry_weekly" to "Die Wochenübersicht ist bereit"
        )
        val intent = Intent(this, MainActivity::class.java)
            .putExtra("open_reports", kind.startsWith("expiry_"))
            .putExtra("open_alerts", !kind.startsWith("expiry_"))
            .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val action = PendingIntent.getActivity(
            this, if (kind.startsWith("expiry_")) 1 else 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle("EpiMediaHub Admin")
            .setContentText(descriptions[kind])
            .setContentIntent(action)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        try {
            NotificationManagerCompat.from(this).notify((kind.hashCode() and Int.MAX_VALUE), notification)
        } catch (_: SecurityException) {
            // Android 13+ permission denied; never bypass user notification choice.
        }
    }
}
