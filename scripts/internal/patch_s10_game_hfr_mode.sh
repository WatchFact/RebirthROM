#!/usr/bin/env bash
# On the Android 16 Samsung donor the VRR method moved from GameManagerService
# to VrrManager. Patch the actual method, never silently omit the runtime HFR fix.
PATCH_S10_GAME_HFR_MODE()
{
    local OLD_VALUE="$1"
    local NEW_VALUE="$2"
    local REL="smali/com/samsung/android/game/GameManagerService.smali"
    local VRR_REL="smali/com/samsung/android/game/VrrManager.smali"
    local JAR="system/framework/gamemanager.jar"
    local METHOD='isVariableRefreshRateSupported()Ljava/lang/String;'
    local CLASS_FILE="$APKTOOL_DIR/system/framework/gamemanager.jar/$REL"
    local VRR_FILE="$APKTOOL_DIR/system/framework/gamemanager.jar/$VRR_REL"

    if [[ "$TARGET_PLATFORM" == "exynos9820" && "${SOURCE_PLATFORM_SDK_VERSION:-0}" -ge 36 ]]; then
        # SMALI_PATCH decodes the JAR itself, but these preflight class checks
        # run before SMALI_PATCH. Decode first to avoid a false missing-class
        # abort on a fresh compilation work directory.
        DECODE_APK "system" "$JAR" || return 1
        if [[ ! -f "$CLASS_FILE" ]] || \
                ! grep -Eq '^[[:space:]]*\.class[[:space:]].*Lcom/samsung/android/game/GameManagerService;$' "$CLASS_FILE"; then
            ABORT "Missing or incompatible GameManagerService donor class: $CLASS_FILE"
            return 1
        fi
        if ! grep -Eq '^[[:space:]]*\.method[[:space:]]+.*[[:space:]]isVariableRefreshRateSupported\(\)Ljava/lang/String;[[:space:]]*$' "$CLASS_FILE"; then
            if [[ ! -f "$VRR_FILE" ]] || \
                    ! grep -Eq '^[[:space:]]*\.class[[:space:]].*Lcom/samsung/android/game/VrrManager;$' "$VRR_FILE"; then
                ABORT "Android 16 GameManagerService VRR method moved, but VrrManager donor class is missing or incompatible: $VRR_FILE"
                return 1
            fi
            if ! grep -Eq '^[[:space:]]*\.method[[:space:]]+.*[[:space:]]isVariableRefreshRateSupported\(\)Ljava/lang/String;[[:space:]]*$' "$VRR_FILE"; then
                ABORT "Android 16 donor lacks exact VRR method in both GameManagerService and VrrManager"
                return 1
            fi
            REL="$VRR_REL"
            LOG "Android 16 GameManagerService VRR method relocated to VrrManager; patching runtime method"
        fi
    fi

    SMALI_PATCH "system" "$JAR" "$REL" "replace" "$METHOD" "$OLD_VALUE" "$NEW_VALUE"
}
