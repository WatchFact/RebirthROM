# Supply explicit ownership and SELinux context for checked-in camera libraries.
# Otherwise ADD_TO_WORK_DIR falls back to generic system_file labels.
for S10_CAMERA_LIB in "$MODPATH"/system/lib64/*.so; do
    [[ -f "$S10_CAMERA_LIB" ]] || continue
    SET_METADATA "system" "system/lib64/${S10_CAMERA_LIB##*/}" 0 0 644 "u:object_r:system_lib_file:s0" || return 1
done
unset S10_CAMERA_LIB

LOG_STEP_IN "- Replacing camera blobs"
BLOBS_LIST="
system/lib64/libenn_wrapper_system.so
system/lib64/libpic_best.arcsoft.so
system/lib64/libarcsoft_dualcam_portraitlighting.so
system/lib64/libdualcam_refocus_gallery_54.so
system/lib64/libdualcam_refocus_gallery_48.so
system/lib64/libhybrid_high_dynamic_range.arcsoft.so
system/lib64/libae_bracket_hdr.arcsoft.so
system/lib64/libface_recognition.arcsoft.so
system/lib64/libDualCamBokehCapture.camera.samsung.so
"
for blob in $BLOBS_LIST
do
    DELETE_FROM_WORK_DIR "system" "$blob" || return 1
done


BLOBS_LIST="
system/lib64/libPortraitDistortionCorrectionCali.arcsoft.so
system/lib64/libMultiFrameProcessing10.camera.samsung.so
system/lib64/libMultiFrameProcessing20.camera.samsung.so
system/lib64/libMultiFrameProcessing20Day.camera.samsung.so
system/lib64/libMultiFrameProcessing30.camera.samsung.so
system/lib64/libMultiFrameProcessing30Tuning.camera.samsung.so
system/lib64/vendor.samsung_slsi.hardware.iva@1.0.so
system/lib64/vendor.samsung_slsi.hardware.MultiFrameProcessing20@1.0.so
"
for blob in $BLOBS_LIST
do
    ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "$blob" 0 0 644 "u:object_r:system_lib_file:s0" || return 1
done


LOG_STEP_OUT

# These libstagefright instruction sequences came from an older One UI donor.
# Android 16 firmware can contain different machine code at these offsets.
# Never replace bytes using an unverified signature or silently claim a fix.
S10_PATCH_KNOWN_STAGEFRIGHT_SIGNATURE()
{
    local description="$1" file="$2" original="$3" replacement="$4"
    local match_status=0
    python3 - "$file" "$original" "$replacement" <<'PY' || match_status=$?
import pathlib
import sys

try:
    data = pathlib.Path(sys.argv[1]).read_bytes()
    before = bytes.fromhex(sys.argv[2])
    after = bytes.fromhex(sys.argv[3])
    if len(before) != len(after):
        sys.exit(1)
    if before in data:
        sys.exit(0)
    if after in data:
        sys.exit(2)
    sys.exit(3)
except (OSError, ValueError):
    sys.exit(1)
PY
    case "$match_status" in
        0)
            HEX_PATCH "$file" "$original" "$replacement" || return 1
            ;;
        2)
            LOG "- $description: known replacement already present"
            ;;
        3)
            LOGW "UNVERIFIED CAMERA COMPATIBILITY: $description has no known signature in ${file//$WORK_DIR/}; leaving binary unchanged"
            printf '%s\n' "$description: no known libstagefright signature" >> "$WORK_DIR/.unverified-camera-patches"
            ;;
        *)
            LOGE "Could not inspect libstagefright for $description"
            return 1
            ;;
    esac
}

LOG_STEP_IN
LOG "- Checking version-specific Video SVC patch"
# Old donor: b LAB_001dd448 -> b LAB_001ddc24.
# An unknown donor MUST NOT be patched at guessed offsets.
S10_PATCH_KNOWN_STAGEFRIGHT_SIGNATURE "Video SVC" \
    "$WORK_DIR/system/system/lib64/libstagefright.so" \
    "da4a0594e0031a2a22feff17" "da4a0594e0031a2a19000014" || return 1

LOG "- Checking version-specific HDR10+ patch"
# Old donor: cbz this,LAB_001dde38 -> nop.
S10_PATCH_KNOWN_STAGEFRIGHT_SIGNATURE "HDR10+" \
    "$WORK_DIR/system/system/lib64/libstagefright.so" \
    "010140f90a4d0594604d0034" "010140f90a4d05941f2003d5" || return 1
LOG_STEP_OUT

BLOBS_LIST="
system/lib64/libeden_wrapper_system.so
system/lib64/libsnap_aidl.snap.samsung.so
"
for blob in $BLOBS_LIST
do
    ADD_TO_WORK_DIR "p3sxxx" "system" "$blob" 0 0 644 "u:object_r:system_lib_file:s0"
done
LOG_STEP_OUT

LOG_STEP_IN "- Adding S21 (p3sxxx) SWISP models"
DELETE_FROM_WORK_DIR "vendor" "saiv/swisp_1.0"
ADD_TO_WORK_DIR "p3sxxx" "vendor" "saiv/swisp_1.0"

BLOBS_LIST="
system/lib64/libSwIsp_core.camera.samsung.so
system/lib64/libSwIsp_wrapper_v1.camera.samsung.so
"
for blob in $BLOBS_LIST
do
    ADD_TO_WORK_DIR "p3sxxx" "system" "$blob" 0 0 644 "u:object_r:system_lib_file:s0" || return 1
done
LOG_STEP_OUT

# Use the checked-in A73 Polarr libraries. The old a26xxx donor directory
# is absent, so its optional branch could never install these dependencies.
LOG_STEP_IN "- Adding A73 (a73xqxx) Polarr SDK blobs"
ADD_TO_WORK_DIR "a73xqxx" "system" "system/etc/public.libraries-polarr.txt" 0 0 644 "u:object_r:system_file:s0" || return 1
ADD_TO_WORK_DIR "a73xqxx" "system" "system/lib64/libBestComposition.polarr.so" 0 0 644 "u:object_r:system_lib_file:s0" || return 1
ADD_TO_WORK_DIR "a73xqxx" "system" "system/lib64/libFeature.polarr.so" 0 0 644 "u:object_r:system_lib_file:s0" || return 1
ADD_TO_WORK_DIR "a73xqxx" "system" "system/lib64/libTracking.polarr.so" 0 0 644 "u:object_r:system_lib_file:s0" || return 1
LOG_STEP_OUT

LOG_STEP_IN "- Cleaning SamsungCamera OAT"
DELETE_FROM_WORK_DIR "system" "system/priv-app/SamsungCamera/oat"
DELETE_FROM_WORK_DIR "system" "system/priv-app/SamsungCamera/SamsungCamera.apk.prof"
DELETE_FROM_WORK_DIR "system" "system/app/FilterProvider/oat"
LOG_STEP_OUT

LOG_STEP_IN "- Fixing AI Photo Editor"
cp -a --preserve=all \
    "$WORK_DIR/system/system/cameradata/portrait_data/single_bokeh_feature.json" \
    "$WORK_DIR/system/system/cameradata/portrait_data/nexus_bokeh_feature.json"
SET_METADATA "system" "system/cameradata/portrait_data/nexus_bokeh_feature.json" 0 0 644 "u:object_r:system_file:s0"
sed -i "s/MODEL_TYPE_INSTANCE_CAPTURE/MODEL_TYPE_OBJ_INSTANCE_CAPTURE/g" \
    "$WORK_DIR/system/system/cameradata/portrait_data/single_bokeh_feature.json"
sed -i \
    's/system\/cameradata\/portrait_data\/single_bokeh_feature.json/system\/cameradata\/portrait_data\/nexus_bokeh_feature.json\x00/g' \
    "$WORK_DIR/system/system/lib64/libPortraitSolution.camera.samsung.so"
LOG_STEP_OUT

LOG_STEP_IN "- Adding S21 (p3sxxx) SingleTake models"
DELETE_FROM_WORK_DIR "vendor" "etc/singletake"
ADD_TO_WORK_DIR "p3sxxx" "vendor" "etc/singletake"

BLOBS_LIST="
system/priv-app/SingleTakeService/SingleTakeService.apk
system/cameradata/singletake/service-feature.xml
"
for blob in $BLOBS_LIST
do
    ADD_TO_WORK_DIR "p3sxxx" "system" "$blob" 0 0 644 "u:object_r:system_file:s0" || return 1
done


LOG "- Decompiling SamsungCamera" # To fool build system into recompiling + signing it at the end
DECODE_APK "system" "system/priv-app/SamsungCamera/SamsungCamera.apk"

if [[ "$TARGET_CODENAME" == "beyond2lte" ]]; then
   LOG "- Adding stock cutout assets"
   cp -a "$MODPATH/assets/lottie_camera_punchcut_timer_b2.json" "$APKTOOL_DIR/system/priv-app/SamsungCamera/SamsungCamera.apk/res/raw/lottie_camera_punchcut_timer_b0.json"
   cp -a "$MODPATH/assets/face_unlocking_cutout_ic_b2.json" "$APKTOOL_DIR/system/priv-app/SamsungCamera/SamsungCamera.apk/res/raw/face_unlocking_cutout_ic_b0.json"
fi

if [[ "$TARGET_CODENAME" == "beyondx" ]]; then
   LOG "- Adding stock cutout assets"
   cp -a "$MODPATH/assets/lottie_camera_punchcut_timer_bx.json" "$APKTOOL_DIR/system/priv-app/SamsungCamera/SamsungCamera.apk/res/raw/lottie_camera_punchcut_timer_b0.json"
   cp -a "$MODPATH/assets/face_unlocking_cutout_ic_bx.json" "$APKTOOL_DIR/system/priv-app/SamsungCamera/SamsungCamera.apk/res/raw/face_unlocking_cutout_ic_b0.json"
fi

LOG_STEP_OUT
