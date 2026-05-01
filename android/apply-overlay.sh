#!/usr/bin/env bash
# Clones MLC Chat at a pinned commit and applies the Hermes overlay so the
# build produces an installable APK.
#
# Usage:
#   cd android
#   ./apply-overlay.sh                  # clone + apply
#   ./apply-overlay.sh --rebuild        # also run `gradle assembleDebug`
#
# Output:
#   ./mlc-chat/                         <- the working source tree
#   ./mlc-chat/android/MLCChat/app/build/outputs/apk/debug/app-debug.apk
#
# The script is idempotent: re-running over an existing tree re-syncs
# the overlay files but won't re-clone.

set -euo pipefail

# Pin so manifest/gradle anchors stay stable. Bump deliberately.
# To advance the pin: git ls-remote "${MLC_REPO}" HEAD | cut -f1
MLC_REPO="https://github.com/mlc-ai/mlc-llm.git"
MLC_PIN="6e6e5d27a84b09b088e6c55eeab7a7c4b7f8dc0f"  # Apr 2025 HEAD; last verified against overlay
TREE="$(cd "$(dirname "$0")" && pwd)"
DEST="${TREE}/mlc-chat"
OVERLAY="${TREE}/overlay"

echo "==> tree:    ${TREE}"
echo "==> overlay: ${OVERLAY}"
echo "==> dest:    ${DEST}"

if [[ ! -d "${DEST}" ]]; then
    echo "==> cloning MLC Chat (${MLC_PIN})"
    # --branch does not accept raw SHAs; use fetch+checkout for SHA support.
    git init "${DEST}"
    git -C "${DEST}" remote add origin "${MLC_REPO}"
    git -C "${DEST}" fetch --depth 1 origin "${MLC_PIN}"
    git -C "${DEST}" -c advice.detachedHead=false checkout FETCH_HEAD
else
    echo "==> ${DEST} exists; skipping clone"
fi

APP="${DEST}/android/MLCChat/app"
SRC="${APP}/src/main"

[[ -d "${APP}" ]] || {
    echo "!!  ${APP} not found — MLC Chat layout may have changed."
    echo "    Update MLC_PIN in this script or apply the overlay manually."
    exit 1
}

echo "==> copying overlay sources"
mkdir -p "${SRC}/kotlin" "${SRC}/res/values"
cp -R "${OVERLAY}/app/src/main/kotlin/." "${SRC}/kotlin/"
cp -R "${OVERLAY}/app/src/main/res/values/." "${SRC}/res/values/"

# ---------- AndroidManifest.xml -----------------------------------------------
MANIFEST="${SRC}/AndroidManifest.xml"
if [[ ! -f "${MANIFEST}" ]]; then
    echo "!!  no manifest at ${MANIFEST}"
    exit 1
fi

if grep -q "ai.mlc.mlcchat.hermes.HermesActivity" "${MANIFEST}"; then
    echo "==> manifest already patched"
else
    echo "==> patching AndroidManifest.xml"
    python3 - "${MANIFEST}" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path).read()

PERMS = """
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
    <uses-permission android:name="moe.shizuku.manager.permission.API_V23" />

    <queries>
        <package android:name="moe.shizuku.privileged.api" />
        <package android:name="com.tailscale.ipn" />
    </queries>
"""

APP_ENTRIES = """
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
"""

# Strip MAIN/LAUNCHER intent-filter from the existing MLC Chat activity so
# Hermes is the launcher.
src = re.sub(
    r'(<activity[^>]*android:name="[^"]*MainActivity"[^>]*>)([\s\S]*?)(</activity>)',
    lambda m: m.group(1) + re.sub(
        r'<intent-filter>\s*<action[^>]*MAIN[^>]*/>\s*<category[^>]*LAUNCHER[^>]*/>\s*</intent-filter>',
        '', m.group(2)) + m.group(3),
    src, count=1,
)

# Insert permissions after the opening <manifest ...> tag.
src = re.sub(r'(<manifest[^>]*>)', r'\1\n' + PERMS, src, count=1)

# Insert app entries before </application>.
src = re.sub(r'(\s*</application>)', APP_ENTRIES + r'\1', src, count=1)

open(path, 'w').write(src)
print('manifest patched')
PY
fi

# ---------- build.gradle.kts --------------------------------------------------
GRADLE="${APP}/build.gradle.kts"
if [[ ! -f "${GRADLE}" ]]; then
    echo "!!  no app build.gradle.kts at ${GRADLE}"
    exit 1
fi

if grep -q "dev.rikka.shizuku:api" "${GRADLE}"; then
    echo "==> build.gradle.kts already patched"
else
    echo "==> patching build.gradle.kts"
    python3 - "${GRADLE}" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path).read()

DEPS = """
    // Hermes overlay — added by apply-overlay.sh
    implementation("dev.rikka.shizuku:api:13.1.5")
    implementation("dev.rikka.shizuku:provider:13.1.5")
    implementation("io.ktor:ktor-server-core:2.3.12")
    implementation("io.ktor:ktor-server-cio:2.3.12")
    implementation("io.ktor:ktor-server-content-negotiation:2.3.12")
    implementation("io.ktor:ktor-client-core:2.3.12")
    implementation("io.ktor:ktor-client-cio:2.3.12")
    implementation("io.ktor:ktor-client-content-negotiation:2.3.12")
    implementation("io.ktor:ktor-serialization-kotlinx-json:2.3.12")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.compose.material3:material3:1.3.0")
"""

src = re.sub(
    r'(dependencies\s*\{)',
    r'\1' + DEPS,
    src, count=1,
)

# Patch minSdk to 30+ — Shizuku wireless ADB pairing requires Android 11+.
# Three cases: existing minSdk line below 30, no minSdk at all, no
# defaultConfig block (warns but does not abort the build).
def _patch_min_sdk(s):
    def _raise_value(m):
        return m.group(0).replace(m.group(1), '30') if int(m.group(1)) < 30 else m.group(0)

    patched, n = re.subn(r'minSdk\s*=\s*(\d+)', _raise_value, s, count=1)
    if n:
        return patched
    patched, n = re.subn(
        r'(defaultConfig\s*\{)',
        r'\1\n        minSdk = 30  // Hermes: Shizuku requires Android 11+',
        s, count=1,
    )
    if n:
        return patched
    print('WARNING: could not patch minSdk — defaultConfig block not found', file=sys.stderr)
    return s

src = _patch_min_sdk(src)

open(path, 'w').write(src)
print('gradle patched')
PY
fi

echo "==> overlay applied"
echo
echo "    Build:   cd ${DEST}/android/MLCChat && ./gradlew assembleDebug"
echo "    Install: adb install -r app/build/outputs/apk/debug/app-debug.apk"

if [[ "${1:-}" == "--rebuild" ]]; then
    echo "==> running gradle"
    (cd "${DEST}/android/MLCChat" && ./gradlew assembleDebug)
fi
