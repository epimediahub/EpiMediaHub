plugins { id("com.android.library") }

android {
    namespace = "androidx.media3.decoder.ffmpeg"
    compileSdk = 35
    ndkVersion = "26.1.10909125"
    defaultConfig {
        minSdk = 25
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk { abiFilters += listOf("armeabi-v7a", "arm64-v8a", "x86", "x86_64") }
        consumerProguardFiles("consumer-rules.pro")
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    externalNativeBuild {
        cmake { path = file("src/main/jni/CMakeLists.txt"); version = "3.22.1" }
    }
    testOptions { animationsDisabled = true }
}

dependencies {
    api("androidx.media3:media3-decoder:1.9.4")
    implementation("androidx.media3:media3-exoplayer:1.9.4")
    implementation("androidx.annotation:annotation:1.9.1")
    compileOnly("org.checkerframework:checker-qual:3.49.0")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:rules:1.6.1")
}
