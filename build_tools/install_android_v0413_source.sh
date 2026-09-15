#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v0412_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.13/patch_v0413.py

grep -q 'versionName = "0.4.13"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 53' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq '/v1/setup/redeem' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
grep -Fq 'Einrichtungscode wurde bereits verwendet' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
grep -Fq 'Einrichtungscode ist abgelaufen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
grep -Fq 'Provisionierungsserver nicht erreichbar' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
grep -Fq 'Oder mit Einrichtungscode anmelden' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/SetupCodeLogin.kt"

echo "Android v0.4.13 setup-code source reconstructed successfully"
