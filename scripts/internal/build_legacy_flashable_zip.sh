#!/usr/bin/env bash
# Copyright (c) 2026 WatchFact
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Dedicated recovery ZIP generator for stock-layout Exynos 9820 devices.
# No super.img, repartitioning, userdata format, or automatic boot flash.
set -eo pipefail
source "$SRC_DIR/scripts/utils/build_utils.sh" || exit 1
source "$SRC_DIR/scripts/utils/install_utils.sh" || exit 1

case "$TARGET_CODENAME" in
    beyond0lte|beyond1lte|beyond2lte|beyondx) ;;
    *) LOGE "Unsupported legacy device: $TARGET_CODENAME"; exit 1 ;;
esac
if [[ "$TARGET_PLATFORM" != "exynos9820" ]] ||
        [[ "$TARGET_USE_DYNAMIC_PARTITIONS" != "false" ]] ||
        [[ "$TARGET_OS_FILE_SYSTEM_TYPE" != "ext4" ]] ||
        [[ "$TARGET_OS_BUILD_SYSTEM_EXT_PARTITION" != "false" ]]; then
    LOGE "Refusing to build a non-static Exynos9820 recovery ZIP"
    exit 1
fi

# Must be explicitly enabled only after reviewing the target's stock PIT
# and validating its running boot chain. This is a BUILD safety gate, not
# a user-facing preflight or a request to repartition the phone.
if [[ "${UNICA_S10_PIT_VERIFIED:-0}" != "1" ]] ||
        [[ "${UNICA_S10_BOOT_VERIFIED:-0}" != "1" ]]; then
    LOGE "S10 recovery ZIP disabled until PIT and kernel/boot chain are verified."
    LOGE "Set UNICA_S10_PIT_VERIFIED=1 and UNICA_S10_BOOT_VERIFIED=1 only after verification."
    exit 1
fi

# The stock Android 12 boot image cannot be assumed to boot Android 16.
# A device-reviewed boot image and stock PIT boot capacity must be pinned.
BOOT_IMAGE="$WORK_DIR/kernel/boot.img"
BOOT_LIMIT="${TARGET_BOOT_PARTITION_SIZE:-none}"
BOOT_SHA256="${TARGET_BOOT_IMAGE_SHA256:-}"
if [[ ! -f "$BOOT_IMAGE" ]] ||
        [[ ! "$BOOT_LIMIT" =~ ^[0-9]+$ ]] || (( BOOT_LIMIT < 1048576 )) ||
        (( BOOT_LIMIT % 4096 != 0 )) ||
        [[ ! "$BOOT_SHA256" =~ ^[[:xdigit:]]{64}$ ]]; then
    LOGE "Missing validated S10 boot.img, boot partition size, or pinned SHA-256."
    exit 1
fi
BOOT_BYTES="$(stat -c %s "$BOOT_IMAGE")"
if (( BOOT_BYTES == 0 || BOOT_BYTES > BOOT_LIMIT )); then
    LOGE "boot.img is empty or larger than the physical boot partition"
    exit 1
fi
if ! printf '%s  %s\n' "$BOOT_SHA256" "$BOOT_IMAGE" | sha256sum --check --status; then
    LOGE "boot.img differs from the reviewed boot image SHA-256"
    exit 1
fi

PARTITIONS=(system vendor product odm)
for part in "${PARTITIONS[@]}"; do
    size_var="TARGET_${part^^}_PARTITION_SIZE"
    size="${!size_var:-none}"
    if [[ ! "$size" =~ ^[0-9]+$ ]] || (( size < 1048576 )) || (( size % 4096 != 0 )); then
        LOGE "No validated 4K-aligned capacity for $part ($size_var=$size)"
        exit 1
    fi
    if [[ ! -d "$WORK_DIR/$part" ]] ||
            [[ ! -f "$WORK_DIR/configs/file_context-$part" ]] ||
            [[ ! -f "$WORK_DIR/configs/fs_config-$part" ]]; then
        LOGE "Missing extracted data or SELinux metadata for $part"
        exit 1
    fi
    # Also fail if the requested destination is absent from recovery.fstab.
    GET_DEVICE_FROM_MOUNTPOINT "/$part" > /dev/null
done

STAGE="$OUT_DIR/target/$TARGET_CODENAME/legacy_zip"
mkdir -p "$(dirname "$STAGE")"
rm -rf "$STAGE"
mkdir -p "$STAGE/META-INF/com/google/android" "$STAGE/META-INF/com/android"
cp -a "$SRC_DIR/prebuilts/bootable/deprecated-ota/updater" \
    "$STAGE/META-INF/com/google/android/update-binary"
SCRIPT_FILE="$STAGE/META-INF/com/google/android/updater-script"

printf 'ui_print("RebirthROM experimental S10 recovery package");\n' > "$SCRIPT_FILE"
printf 'ui_print("Target: %s");\n' "$TARGET_CODENAME" >> "$SCRIPT_FILE"
# A mismatched device aborts before *any* partition is written.
# For Samsung bootloaders, use the hardware model first. If this recovery
# does not expose that property, fall back to the device codename.
# Never let a model reported by the bootloader disagree with this package.
MODEL_CHECK=""
IFS=':' read -r -a S10_ALLOWED_MODELS <<< "${TARGET_ASSERT_MODEL:-}"
for model in "${S10_ALLOWED_MODELS[@]}"; do
    if [[ ! "$model" =~ ^SM-G[0-9A-Z]+$ ]]; then
        LOGE "Unexpected target model in configuration: $model"
        exit 1
    fi
    [[ -n "$MODEL_CHECK" ]] && MODEL_CHECK+=" || "
    MODEL_CHECK+="getprop(\"ro.boot.em.model\") == \"$model\""
done
if [[ -z "$MODEL_CHECK" ]]; then
    LOGE "Cannot package S10 without explicit approved model numbers"
    exit 1
fi
printf 'assert((getprop("ro.boot.em.model") != "" && (%s)) || (getprop("ro.boot.em.model") == "" && (getprop("ro.product.device") == "%s" || getprop("ro.build.product") == "%s")) || abort("Wrong S10 model/device"));\n' \
    "$MODEL_CHECK" "$TARGET_CODENAME" "$TARGET_CODENAME" >> "$SCRIPT_FILE"
printf 'unmount("/system");\nunmount("/vendor");\nunmount("/product");\nunmount("/odm");\n' >> "$SCRIPT_FILE"

BROTLI_QUALITY="${UNICA_BROTLI_QUALITY:-6}"
if ! [[ "$BROTLI_QUALITY" =~ ^([0-9]|1[01])$ ]]; then
    LOGE "Brotli quality must be 0..11"
    exit 1
fi

for part in "${PARTITIONS[@]}"; do
    size_var="TARGET_${part^^}_PARTITION_SIZE"
    limit="${!size_var}"
    LOG "Creating verified-size ext4 image for $part ($limit bytes maximum)"
    "$SRC_DIR/scripts/build_fs_image.sh" ext4 --no-avb -m -S \
        -s "$limit" -o "$STAGE/$part.img" \
        "$WORK_DIR/$part" "$WORK_DIR/configs/file_context-$part" \
        "$WORK_DIR/configs/fs_config-$part" || exit 1
    image_bytes="$(GET_IMAGE_SIZE "$STAGE/$part.img")"
    if (( image_bytes > limit )); then
        LOGE "$part image exceeds recorded partition capacity"
        exit 1
    fi
    img2sdat -o "$STAGE" -B "$STAGE/$part.map" "$STAGE/$part.img"
    if [[ ! -s "$STAGE/$part.transfer.list" ]] ||
            [[ ! -s "$STAGE/$part.new.dat" ]] ||
            [[ ! -f "$STAGE/$part.patch.dat" ]]; then
        LOGE "Incomplete $part block-image payload (transfer/new/patch)"
        exit 1
    fi
    brotli --quality="$BROTLI_QUALITY" --output="$STAGE/$part.new.dat.br" "$STAGE/$part.new.dat"
    rm -f "$STAGE/$part.img" "$STAGE/$part.map" "$STAGE/$part.new.dat"
    block="$(GET_DEVICE_FROM_MOUNTPOINT "/$part")"
    printf 'ui_print("Writing %s...");\n' "$part" >> "$SCRIPT_FILE"
    printf 'assert(block_image_update(%s, package_extract_file("%s.transfer.list"), "%s.new.dat.br", "%s.patch.dat"));\n' \
        "$block" "$part" "$part" "$part" >> "$SCRIPT_FILE"
done
printf 'set_progress(1.0);\nui_print("System partitions installed.");\n' >> "$SCRIPT_FILE"
# Only the exact reviewed image is permitted to replace the boot partition.
cp -a "$BOOT_IMAGE" "$STAGE/boot.img"
BOOT_BLOCK="$(GET_DEVICE_FROM_MOUNTPOINT "/boot")"
printf 'ui_print("Writing verified boot.img...");\n' >> "$SCRIPT_FILE"
printf 'assert(package_extract_file("boot.img", %s) || abort("Boot image installation failed"));\n' \
    "$BOOT_BLOCK" >> "$SCRIPT_FILE"


# DTBO/recovery/AVB remain untouched. The explicitly pinned boot image above
# still does not establish boot compatibility or verified AVB state.
printf 'ota-type=BLOCK\npre-device=%s\n' "$TARGET_CODENAME" > "$STAGE/META-INF/com/android/metadata"
mkdir -p "$OUT_DIR"
archive="$OUT_DIR/RebirthROM_EXPERIMENTAL_${ROM_VERSION}_${TARGET_CODENAME}.zip"
unsigned="$STAGE/rom-unsigned.zip"
(
    cd "$STAGE"
    7z a -tzip -mx=0 -mmt=on "$unsigned" META-INF \
        *.new.dat.br *.transfer.list *.patch.dat boot.img
)
signapk -w "$SRC_DIR/security/aosp_testkey.x509.pem" \
    "$SRC_DIR/security/aosp_testkey.pk8" "$unsigned" "$archive"
test -s "$archive" || { LOGE "Missing generated ZIP"; exit 1; }
LOG "Experimental recovery artifact: $archive"
