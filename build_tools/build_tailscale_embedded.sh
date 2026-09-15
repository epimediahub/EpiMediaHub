#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"
: "${ANDROID_HOME:?ANDROID_HOME is required}"

TAILSCALE_ANDROID_SHA="${TAILSCALE_ANDROID_SHA:-c412dfe3b28ed7c5dd4de233149fa1bd55065dfd}"
TS="${RUNNER_TEMP:-/tmp}/tailscale-android-embedded"
rm -rf "$TS"
git clone --no-checkout https://github.com/tailscale/tailscale-android.git "$TS"
git -C "$TS" checkout "$TAILSCALE_ANDROID_SHA"

export NDK_ROOT="$ANDROID_HOME/ndk/23.1.7779620"
cd "$TS"
make libtailscale
test -s android/libs/libtailscale.aar

cat > android/build.gradle.kts <<'EOF'
plugins {
    id("org.jetbrains.kotlin.android") version "1.9.22"
    id("com.android.library") version "8.13.0"
    id("org.jetbrains.kotlin.plugin.serialization") version "1.9.22"
}
repositories { google(); mavenCentral() }
val composeVersion = "1.5.10"
android {
    namespace = "com.tailscale.ipn"
    compileSdk = 36
    ndkVersion = "23.1.7779620"
    defaultConfig {
        minSdk = 26
        buildConfigField("boolean", "USE_GOOGLE_DNS_FALLBACK", "true")
        buildConfigField("String", "VERSION_NAME", "\"embedded-c412dfe3\"")
        buildConfigField("String", "APPLICATION_ID", "\"com.tailscale.ipn\"")
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true; compose = true }
    composeOptions { kotlinCompilerExtensionVersion = composeVersion }
    buildTypes { release { isMinifyEnabled = false } }
}
dependencies {
    implementation(libs.androidx.core)
    implementation(libs.androidx.coreKtx)
    implementation(libs.androidx.browser)
    implementation(libs.androidx.security.crypto)
    implementation(libs.androidx.work.runtime)
    implementation(libs.androidx.work.runtimeKtx)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.androidx.room.ktx)
    runtimeOnly(libs.kotlinx.coroutines.android)
    implementation(libs.kotlin.stdlib)
    implementation(libs.kotlin.reflect)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.toolingPreview)
    implementation(libs.androidx.lifecycle.viewmodel.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.accompanist.permissions)
    implementation(libs.accompanist.systemuicontroller)
    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.compose.animation)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.navigation.ui)
    implementation(libs.coil.compose)
    implementation(libs.zxing.core)
    implementation(libs.vico.compose)
    implementation(libs.vico.composeM3)

    // libtailscale is a generated local AAR. The wrapper module only needs it
    // on the compile classpath; the final EpiMediaHub APK packages the same AAR
    // separately. Using implementation(...) here makes AGP try to nest an AAR
    // inside another AAR and fails bundleReleaseAar by design.
    compileOnly(files("libs/libtailscale.aar"))
}
EOF

cat > android/src/main/AndroidManifest.xml <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.CHANGE_NETWORK_STATE" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SYSTEM_EXEMPTED" />
    <application>
        <service
            android:name=".IPNService"
            android:exported="false"
            android:foregroundServiceType="systemExempted"
            android:permission="android.permission.BIND_VPN_SERVICE">
            <intent-filter>
                <action android:name="android.net.VpnService" />
            </intent-filter>
        </service>
    </application>
</manifest>
EOF

cd android
./gradlew assembleRelease --no-daemon --stacktrace
test -s build/outputs/aar/android-release.aar

mkdir -p "$GITHUB_WORKSPACE/$PROJECT_ROOT/app/libs"
cp build/outputs/aar/android-release.aar "$GITHUB_WORKSPACE/$PROJECT_ROOT/app/libs/tailscale-embedded.aar"
cp libs/libtailscale.aar "$GITHUB_WORKSPACE/$PROJECT_ROOT/app/libs/libtailscale.aar"
test -s "$GITHUB_WORKSPACE/$PROJECT_ROOT/app/libs/tailscale-embedded.aar"
test -s "$GITHUB_WORKSPACE/$PROJECT_ROOT/app/libs/libtailscale.aar"

echo "Embedded Tailscale runtime built from $TAILSCALE_ANDROID_SHA"
