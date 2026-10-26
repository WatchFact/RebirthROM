if [[ "$SOURCE_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME" == "$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME" ]] && \
    [[ "$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" == "$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" ]]; then
    LOG "\033[0;33m! Nothing to do\033[0m"
    return 0
fi

_LOG() { if $DEBUG; then LOGW "$1"; else ABORT "$1"; fi }

# Samsung renames the obfuscated SDHMS classes between platform releases.
# Keep the known One UI 8.0 paths as the default and select their 8.5
# counterparts when building from the S23 FE source.
DVFS_FEATURE_SMALI="smali/r1/c.smali"
DVFS_PROPERTIES_SMALI="smali/z1/e.smali"
SSRM_FEATURE_SMALI="smali/U1/w.smali"
if [ "$SOURCE_PLATFORM_SDK_VERSION" -ge 36 ]; then
    DVFS_FEATURE_SMALI="smali/c4/c.smali"
    DVFS_PROPERTIES_SMALI="smali/k4/e.smali"
    SSRM_FEATURE_SMALI="smali/o5/w.smali"
fi

# SEC_PRODUCT_FEATURE_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME
if [[ "$SOURCE_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME" != "$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME" ]]; then
    SMALI_PATCH "system" "system/framework/ssrm.jar" \
        "smali/com/android/server/ssrm/Feature.smali" "replace" \
        "<clinit>()V" \
        "$SOURCE_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME" \
        "$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME"

    DECODE_APK "system" "system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk"

    if [ -f "$SRC_DIR/target/$TARGET_CODENAME/dvfs/$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME.xml" ]; then
        LOG "- Adding /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/res/raw/$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME.xml"
        EVAL "cp -a \"$SRC_DIR/target/$TARGET_CODENAME/dvfs/$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME.xml\" \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/res/raw/$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME.xml\""
    elif [ ! -f "$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/res/raw/$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME.xml" ]; then
        _LOG "\"$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME\" does not exist in SDHMS app"
    fi

    # com/sec/android/sdhms/performance/PerformanceFeature
    SMALI_PATCH "system" "system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk" \
        "$DVFS_FEATURE_SMALI" "replace" \
        "<clinit>()V" \
        "$SOURCE_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME" \
        "$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME"
    # com/sec/android/sdhms/performance/settings/PerformanceProperties
    SMALI_PATCH "system" "system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk" \
        "$DVFS_PROPERTIES_SMALI" "replace" \
        "<init>(Landroid/content/Context;)V" \
        "$SOURCE_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME" \
        "$TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME"
fi

# SEC_PRODUCT_FEATURE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME
if [[ "$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" != "$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" ]]; then
    SET_FLOATING_FEATURE_CONFIG "SEC_FLOATING_FEATURE_SYSTEM_CONFIG_SIOP_POLICY_FILENAME" "$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME"

    SMALI_PATCH "system" "system/framework/ssrm.jar" \
        "smali/com/android/server/ssrm/Feature.smali" "replace" \
        "<clinit>()V" \
        "$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" \
        "$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME"

    DECODE_APK "system" "system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk"

    if [[ "$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" != "ssrm_default" ]] && \
            [[ "$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" == "ssrm_default" ]]; then
        LOG "- Deleting /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_default"
        EVAL "rm \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_default\""
        LOG "- Deleting /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_model"
        EVAL "rm \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_model\""
        LOG "- Deleting /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/ssrm_default"
        EVAL "rm \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/ssrm_default\""
        LOG "- Adding /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_default.xml"
        EVAL "cp -a \"$MODPATH/assets/siop_default.xml\" \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_default.xml\""
        LOG "- Adding /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/ssrm_default.xml"
        EVAL "cp -a \"$MODPATH/assets/ssrm_default.xml\" \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/ssrm_default.xml\""
    fi

    # com/sec/android/sdhms/util/Feature
    SMALI_PATCH "system" "system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk" \
        "$SSRM_FEATURE_SMALI" "replace" \
        "<clinit>()V" \
        "$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" \
        "$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME"
fi

if [ -f "$SRC_DIR/target/$TARGET_CODENAME/dvfs/siop_model.xml" ]; then
    DECODE_APK "system" "system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk"

    LOG "- Deleting /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_default"
    EVAL "rm \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_default\""
    LOG "- Deleting /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_model"
    EVAL "rm \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_model\""
    LOG "- Deleting /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/ssrm_default"
    EVAL "rm \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/ssrm_default\""

    LOG "- Adding /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_default.xml"
    EVAL "cp -a \"$MODPATH/assets/siop_default.xml\" \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/siop_default.xml\""
    LOG "- Adding /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME.xml"
    EVAL "cp -a \"$SRC_DIR/target/$TARGET_CODENAME/dvfs/siop_model.xml\" \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME.xml\""
    LOG "- Adding /system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/ssrm_default.xml"
    EVAL "cp -a \"$MODPATH/assets/ssrm_default.xml\" \"$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/ssrm_default.xml\""
else
    if [[ "$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" != "$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" ]] && \
            [[ "$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" != "ssrm_default" ]]; then
        # Legacy S10 trees do not ship siop_model.xml. Try to obtain the
        # matching, device-authored policy from the extracted target stock APK.
        S10_SDHMS_FW_PATH="$(cut -d "/" -f 1 -s <<< "$TARGET_FIRMWARE")_$(cut -d "/" -f 2 -s <<< "$TARGET_FIRMWARE")"
        S10_SDHMS_APK="$FW_DIR/$S10_SDHMS_FW_PATH/system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk"
        S10_SDHMS_ASSET="$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk/assets/$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME.xml"
        mkdir -p "$(dirname "$S10_SDHMS_ASSET")"
        # Samsung's Android 12 SDHMS APK may store the device-authored
        # SIOP XML in res/raw instead of assets. Only import the exact
        # configured S10+ policy, never a similarly named donor policy.
        S10_SDHMS_ENTRY=""
        if [ -f "$S10_SDHMS_APK" ]; then
            for S10_SDHMS_CANDIDATE in \
                    "assets/$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME.xml" \
                    "res/raw/$TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME.xml"; do
                if unzip -Z1 "$S10_SDHMS_APK" 2>/dev/null |
                        grep -Fx "$S10_SDHMS_CANDIDATE" >/dev/null; then
                    S10_SDHMS_ENTRY="$S10_SDHMS_CANDIDATE"
                    break
                fi
            done
        fi

        S10_SDHMS_VALID=false
        if [ -n "$S10_SDHMS_ENTRY" ] &&
                unzip -p "$S10_SDHMS_APK" "$S10_SDHMS_ENTRY" > "$S10_SDHMS_ASSET" &&
                [ -s "$S10_SDHMS_ASSET" ]; then
            # Reject non-XML/compiled Android resources and incompatible
            # document roots rather than silently installing thermal data
            # the Android 16 donor's SSRM parser may not understand.
            # Look up the exact donor policy in both decoded resource
            # locations. Some Samsung APKs omit the .xml suffix in assets.
            # Do not substitute a different model's thermal policy.
            S10_DONOR_SIOP=""
            S10_DONOR_BASE="$APKTOOL_DIR/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk"
            # The Android 16 SDHMS has an encrypted asset mode, selected by
            # assets/ssrm_default, and a separate plaintext XML mode. Its
            # plaintext parser loads siop_default.xml and <policy>.xml.
            # Only switch modes if the actual decoded parser exposes that
            # path and the genuine stock policy has the expected structure.
            S10_DONOR_PARSER="$S10_DONOR_BASE/smali/com/sec/android/sdhms/settings/k.smali"
            if [ -s "$S10_DONOR_PARSER" ] &&
                    grep -Fq 'const-string p0, "ssrm_default"' "$S10_DONOR_PARSER" &&
                    grep -Fq 'const-string v0, "siop_default.xml"' "$S10_DONOR_PARSER" &&
                    grep -Fq 'const-string p1, "siop_model"' "$S10_DONOR_PARSER" &&
                    grep -Fq 'const-string v0, ".xml"' "$S10_DONOR_PARSER" &&
                    grep -Fq 'AssetManager;->open' "$S10_DONOR_PARSER" &&
                    python3 - "$S10_SDHMS_ASSET" "$MODPATH/assets/siop_default.xml" "$MODPATH/assets/ssrm_default.xml" <<'PY'
import sys
import xml.etree.ElementTree as ET
try:
    target, default, ssrm = [ET.parse(p).getroot() for p in sys.argv[1:]]
except (ET.ParseError, OSError) as exc:
    print(f"S10 plaintext policy validation failed: {exc}", file=sys.stderr)
    sys.exit(1)
if any(root.tag != "siop_document" for root in (target, default, ssrm)):
    sys.exit("S10 and bundled default policies have incompatible roots")
if not all(root.find("modelsettings") is not None and
           root.find("components") is not None and
           root.find("scenarios") is not None for root in (target, default, ssrm)):
    sys.exit("S10 or bundled policy is missing required sections")
if not target.findall("./components/component") or not target.findall("./scenarios/scenario"):
    sys.exit("S10 policy lacks component or scenario entries")
PY
            then
                # Absence of this exact filename selects plaintext parsing
                # in the inspected SDHMS parser. Never alter thermal values.
                rm -f "$S10_DONOR_BASE/assets/ssrm_default" \
                    "$S10_DONOR_BASE/assets/siop_default" \
                    "$S10_DONOR_BASE/assets/siop_model"
                cp -a "$MODPATH/assets/siop_default.xml" "$S10_DONOR_BASE/assets/siop_default.xml"
                cp -a "$MODPATH/assets/ssrm_default.xml" "$S10_DONOR_BASE/assets/ssrm_default.xml"
                S10_SDHMS_VALID=true
                LOG "- Selected donor's inspected plaintext SIOP parser for exact stock S10 XML (runtime still unverified)"
            fi
            for S10_DONOR_CANDIDATE in \
                    "$S10_DONOR_BASE/assets/$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME.xml" \
                    "$S10_DONOR_BASE/res/raw/$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME.xml" \
                    "$S10_DONOR_BASE/assets/$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME" \
                    "$S10_DONOR_BASE/res/raw/$SOURCE_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME"; do
                if [ -s "$S10_DONOR_CANDIDATE" ]; then
                    S10_DONOR_SIOP="$S10_DONOR_CANDIDATE"
                    break
                fi
            done
            if [ -n "$S10_DONOR_SIOP" ] &&
                    python3 - "$S10_SDHMS_ASSET" "$S10_DONOR_SIOP" <<'PY'
import sys
import xml.etree.ElementTree as ET

try:
    target = ET.parse(sys.argv[1]).getroot()
    donor = ET.parse(sys.argv[2]).getroot()
except (ET.ParseError, OSError) as exc:
    print(f"Cannot validate stock/donor SIOP XML: {exc}", file=sys.stderr)
    sys.exit(1)
if target.tag != "siop_document" or donor.tag != target.tag:
    print(f"Incompatible SIOP XML roots: stock={target.tag}, donor={donor.tag}", file=sys.stderr)
    sys.exit(1)
PY
            then
                S10_SDHMS_VALID=true
                LOG "- Imported verified stock $TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME.xml from $S10_SDHMS_ENTRY"
            fi
        fi

        if ! $S10_SDHMS_VALID; then
            # Preserve the reason for rejecting the exact stock policy.
            # Previously a missing donor path produced no diagnostic at all.
            if [ -z "$S10_SDHMS_ENTRY" ]; then
                LOGW "Exact target policy entry not found in stock SDHMS APK"
            elif [ ! -s "$S10_SDHMS_ASSET" ]; then
                LOGW "Stock SDHMS policy entry was found but extraction was empty"
            else
                LOGW "Stock policy extracted from $S10_SDHMS_ENTRY but validation failed"
                python3 - "$S10_SDHMS_ASSET" <<'PY' || true
import sys
import xml.etree.ElementTree as ET
try:
    print("Stock policy XML root:", ET.parse(sys.argv[1]).getroot().tag)
except (ET.ParseError, OSError) as exc:
    print("Stock policy XML parse error:", exc, file=sys.stderr)
PY
            fi
            if [ -z "${S10_DONOR_SIOP:-}" ]; then
                LOGW "No exact donor SIOP policy found in decoded SDHMS assets or res/raw"
            fi
            LOGW "Decoded donor SIOP/DVFS candidate files:"
            find "$S10_DONOR_BASE/assets" "$S10_DONOR_BASE/res/raw" \
                -maxdepth 1 -type f 2>/dev/null |
                grep -Ei '/(siop|ssrm|dvfs)[^/]*$' |
                head -60 || true
            rm -f "$S10_SDHMS_ASSET"
            if [ -f "$S10_SDHMS_APK" ]; then
                LOGW "Target stock SDHMS APK: $S10_SDHMS_APK"
                LOGW "Matching S10 and default stock SIOP/DVFS assets:"
                unzip -Z1 "$S10_SDHMS_APK" 2>/dev/null |
                    grep -Ei '(^|/)(siop|ssrm|dvfs|thermal)[^/]*$' |
                    grep -Ei '(beyond|exynos9820|default|^assets/)' |
                    head -100 || true
            else
                LOGW "Target stock SDHMS APK not found: $S10_SDHMS_APK"
            fi
            LOGW "Matching loose target-stock policy files:"
            find "$FW_DIR/$S10_SDHMS_FW_PATH" -type f -print 2>/dev/null |
                grep -Ei '/[^/]*(siop|ssrm|dvfs)[^/]*$' |
                head -60 || true
            _LOG "Missing or incompatible verified S10 SSRM policy: $TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME.xml (do not substitute donor thermal data)"
        fi
        unset S10_SDHMS_ENTRY S10_SDHMS_CANDIDATE S10_SDHMS_VALID S10_DONOR_SIOP S10_DONOR_BASE S10_DONOR_CANDIDATE
        unset S10_SDHMS_FW_PATH S10_SDHMS_APK S10_SDHMS_ASSET
    fi
fi

unset -f _LOG
unset DVFS_FEATURE_SMALI DVFS_PROPERTIES_SMALI SSRM_FEATURE_SMALI
