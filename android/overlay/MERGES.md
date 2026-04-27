# Manifest + Gradle merges to apply on top of MLC Chat

## `app/src/main/AndroidManifest.xml`

Add inside `<manifest>`:

```xml
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
<uses-permission android:name="moe.shizuku.manager.permission.API_V23" />

<queries>
    <package android:name="moe.shizuku.privileged.api" />
    <package android:name="com.tailscale.ipn" />
</queries>
```

Add inside `<application>`:

```xml
<service
    android:name="ai.mlc.mlcchat.hermes.service.HermesForegroundService"
    android:exported="false"
    android:foregroundServiceType="dataSync" />

<receiver
    android:name="ai.mlc.mlcchat.hermes.service.BootReceiver"
    android:enabled="true"
    android:exported="false">
    <intent-filter>
        <action android:name="android.intent.action.BOOT_COMPLETED" />
    </intent-filter>
</receiver>

<provider
    android:name="rikka.shizuku.ShizukuProvider"
    android:authorities="${applicationId}.shizuku"
    android:multiprocess="false"
    android:enabled="true"
    android:exported="true"
    android:permission="android.permission.INTERACT_ACROSS_USERS_FULL" />
```

## `app/build.gradle.kts`

Add to `dependencies`:

```kotlin
implementation("dev.rikka.shizuku:api:13.1.5")
implementation("dev.rikka.shizuku:provider:13.1.5")
implementation("io.ktor:ktor-server-core:2.3.12")
implementation("io.ktor:ktor-server-netty:2.3.12")
implementation("io.ktor:ktor-server-content-negotiation:2.3.12")
implementation("io.ktor:ktor-serialization-kotlinx-json:2.3.12")
implementation("androidx.work:work-runtime-ktx:2.9.1")
```

Add to `android.defaultConfig`:

```kotlin
minSdk = 30   // Shizuku wireless ADB pairing requires Android 11+
```
