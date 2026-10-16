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
        val releaseCode = System.getenv("EPI_ADMIN_RELEASE_VERSION_CODE")?.toIntOrNull() ?: 3
        require(releaseCode in 1..2147483646) { "Invalid release version code" }
        versionCode = releaseCode
        val releaseName = System.getenv("EPI_ADMIN_RELEASE_VERSION_NAME") ?: "0.3.0-private-qa"
        require(releaseName.matches(Regex("[A-Za-z0-9._-]{1,48}"))) {
            "Invalid release version name"
        }
        versionName = releaseName
        val appId = firebaseVariable("EPI_ADMIN_FIREBASE_APP_ID")
        val apiKey = firebaseVariable("EPI_ADMIN_FIREBASE_API_KEY")
        val projectId = firebaseVariable("EPI_ADMIN_FIREBASE_PROJECT_ID")
        val senderId = firebaseVariable("EPI_ADMIN_FIREBASE_SENDER_ID")
        buildConfigField("String", "FIREBASE_APP_ID", "\"$appId\"")
        buildConfigField("String", "FIREBASE_API_KEY", "\"$apiKey\"")
        buildConfigField("String", "FIREBASE_PROJECT_ID", "\"$projectId\"")
        buildConfigField("String", "FIREBASE_SENDER_ID", "\"$senderId\"")
    }
    val releaseKeystore = System.getenv("EPI_ADMIN_RELEASE_KEYSTORE_FILE") ?: ""
    signingConfigs {
        create("adminRelease") {
            if (releaseKeystore.isNotBlank()) {
                storeFile = file(releaseKeystore)
                storePassword = System.getenv("EPI_ADMIN_RELEASE_STORE_PASSWORD")
                keyAlias = System.getenv("EPI_ADMIN_RELEASE_KEY_ALIAS")
                keyPassword = System.getenv("EPI_ADMIN_RELEASE_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            if (releaseKeystore.isNotBlank()) {
                signingConfig = signingConfigs.getByName("adminRelease")
            }
        }
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
