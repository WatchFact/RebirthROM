#!/usr/bin/env bash
# Guard Samsung's diagnostic-only RefreshRateConfig.dump bytecode on Android 16.
# Do not suppress runtime getMainInstance, Settings, or SystemUI HFR patches.
PATCH_REFRESH_RATE_DUMP()
{
    local OLD_VALUE="$1"
    local NEW_VALUE="$2"
    local REL="smali_classes6/com/samsung/android/hardware/display/RefreshRateConfig.smali"
    local DECODED="$APKTOOL_DIR/system/framework/framework.jar/$REL"

    if [[ "$TARGET_PLATFORM" == "exynos9820" && "${SOURCE_PLATFORM_SDK_VERSION:-0}" -ge 36 ]]; then
        if [[ ! -f "$DECODED" ]]; then
            ABORT "Missing decoded RefreshRateConfig smali: $DECODED"
            return 1
        fi
        if ! grep -Eq '^\.class[[:space:]].*Lcom/samsung/android/hardware/display/RefreshRateConfig;$' "$DECODED"; then
            ABORT "Unexpected RefreshRateConfig smali class declaration: $DECODED"
            return 1
        fi
        # Android 16 donor omits the legacy dump(PrintWriter,String,boolean)
        # method. This is a diagnostic-only text replacement, not HFR logic.
        if ! grep -Eq '^[[:space:]]*\.method[[:space:]]+.*[[:space:]]dump\(Ljava/io/PrintWriter;Ljava/lang/String;Z\)V[[:space:]]*$' "$DECODED"; then
            LOG "Android 16 RefreshRateConfig has no legacy dump method; omitting diagnostic string: $OLD_VALUE"
            return 0
        fi
    fi

    SMALI_PATCH "system" "system/framework/framework.jar" \
        "$REL" "replace" \
        "dump(Ljava/io/PrintWriter;Ljava/lang/String;Z)V" \
        "$OLD_VALUE" "$NEW_VALUE"
}
