import java.net.URI

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.kapt")
}

val configuredServerUrl = providers.gradleProperty("monitorServerUrl")
    .orElse(providers.environmentVariable("MONITOR_SERVER_URL"))
    .orElse("https://monitor.example.com")
    .get()
val parsedServerUrl = URI(configuredServerUrl)
require(
    parsedServerUrl.scheme == "https" &&
        !parsedServerUrl.host.isNullOrBlank() &&
        parsedServerUrl.rawUserInfo == null &&
        parsedServerUrl.rawPath.orEmpty() in listOf("", "/") &&
        parsedServerUrl.rawQuery == null &&
        parsedServerUrl.rawFragment == null,
) {
    "monitorServerUrl debe ser un origen HTTPS sin credenciales, ruta, query ni fragmento."
}
val escapedServerUrl = configuredServerUrl
    .replace("\\", "\\\\")
    .replace("\"", "\\\"")

android {
    namespace = "mx.protocolo.monitor"
    compileSdk = 35
    buildFeatures {
        buildConfig = true
    }

    defaultConfig {
        applicationId = "mx.protocolo.monitor"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
        buildConfigField("String", "DEFAULT_SERVER_URL", "\"$escapedServerUrl\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
    }
}

dependencies {
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    kapt("androidx.room:room-compiler:2.6.1")
    implementation("androidx.work:work-runtime-ktx:2.10.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")

    testImplementation("junit:junit:4.13.2")
}
