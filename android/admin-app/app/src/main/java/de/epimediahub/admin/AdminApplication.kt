package de.epimediahub.admin

import android.app.Application
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions

/** Initialize the default Firebase app for both foreground UI and background FCM. */
class AdminApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        val values=listOf(BuildConfig.FIREBASE_APP_ID, BuildConfig.FIREBASE_API_KEY,
            BuildConfig.FIREBASE_PROJECT_ID, BuildConfig.FIREBASE_SENDER_ID)
        if (values.any { it.isBlank() }) return
        if (FirebaseApp.getApps(this).isNotEmpty()) return
        val options=FirebaseOptions.Builder()
            .setApplicationId(BuildConfig.FIREBASE_APP_ID)
            .setApiKey(BuildConfig.FIREBASE_API_KEY)
            .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
            .setGcmSenderId(BuildConfig.FIREBASE_SENDER_ID)
            .build()
        FirebaseApp.initializeApp(this,options)
    }
}
