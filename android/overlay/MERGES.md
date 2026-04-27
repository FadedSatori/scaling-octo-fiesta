# Manifest + Gradle merges to apply on top of MLC Chat

`apply-overlay.sh` performs these merges automatically against the pinned
MLC Chat commit. The notes below are for manual application or for
verifying the patch when MLC Chat changes shape.

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

Inside `<application>`, **remove** the `<intent-filter>` containing
`android.intent.action.MAIN` from MLC Chat's existing `MainActivity` so
Hermes becomes the launcher, then add:

```xml
<activity
    android:name="ai.mlc.mlcchat.hermes.HermesActivity"
    android:exported="true"
    android:label="@string/hermes_app_name"
    android:launchMode="singleTask">
    <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
    </intent-filter>
</activity>

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
// Hermes inference bridge depends on the mlc4j module from the upstream
// MLC LLM repo. The MLC Chat sample app already includes it as a project
// dependency; we just rely on that. If you've moved mlc4j elsewhere, swap
// this for the appropriate `implementation(project(":..."))` reference.
implementation(project(":mlc4j"))

// Shizuku for ADB-level privileges without root.
implementation("dev.rikka.shizuku:api:13.1.5")
implementation("dev.rikka.shizuku:provider:13.1.5")

// Ktor server (HermesForegroundService) + client (RemoteChatBackend, HermesClient).
// CIO engine is used on Android — Netty pulls in JVM-only deps.
implementation("io.ktor:ktor-server-core:2.3.12")
implementation("io.ktor:ktor-server-cio:2.3.12")
implementation("io.ktor:ktor-server-content-negotiation:2.3.12")
implementation("io.ktor:ktor-client-core:2.3.12")
implementation("io.ktor:ktor-client-cio:2.3.12")
implementation("io.ktor:ktor-client-content-negotiation:2.3.12")
implementation("io.ktor:ktor-serialization-kotlinx-json:2.3.12")

// Compose UI for HermesActivity.
implementation("androidx.activity:activity-compose:1.9.2")
implementation("androidx.compose.material3:material3:1.3.0")

implementation("androidx.work:work-runtime-ktx:2.9.1")
```

Add to `android.defaultConfig`:

```kotlin
minSdk = 30   // Shizuku wireless ADB pairing requires Android 11+
```
