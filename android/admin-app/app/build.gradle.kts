plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

fun firebaseVariable(name: String): String {
    val value = System.getenv(name) ?: ""
    require(value.matches(Regex("[A-Za-z0-9:._-]{0,180}"))) {
        "Firebase build metadata contains invalid characters: $name"
    }
    return value
}

android {
    namespace = "de.epimediahub.admin"
    compileSdk = 35

    defaultConfig {
        applicationId = "de.epimediahub.admin"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0-private-qa"
        val appId = firebaseVariable("EPI_ADMIN_FIREBASE_APP_ID")
        val apiKey = firebaseVariable("EPI_ADMIN_FIREBASE_API_KEY")
        val projectId = firebaseVariable("EPI_ADMIN_FIREBASE_PROJECT_ID")
        val senderId = firebaseVariable("EPI_ADMIN_FIREBASE_SENDER_ID")
        buildConfigField("String", "FIREBASE_APP_ID", "\"$appId\"")
        buildConfigField("String", "FIREBASE_API_KEY", "\"$apiKey\"")
        buildConfigField("String", "FIREBASE_PROJECT_ID", "\"$projectId\"")
        buildConfigField("String", "FIREBASE_SENDER_ID", "\"$senderId\"")
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.15"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.10.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("androidx.fragment:fragment-ktx:1.8.5")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("com.google.firebase:firebase-messaging:24.1.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
