#!/usr/bin/env bash
# Copyright (c) 2025 Salvo Giangreco
# SPDX-License-Identifier: GPL-3.0-or-later

# Run from an immutable snapshot. A build can take hours, and changing this
# file while Bash is still reading it can otherwise corrupt the command being
# parsed at the current file offset.
if [ -z "${UNICA_MAKE_ROM_SNAPSHOT:-}" ]; then
    UNICA_MAKE_ROM_SNAPSHOT_PATH="$(mktemp "${TMPDIR:-/tmp}/unica-make-rom.XXXXXX")" || exit 1
    cp -a "${BASH_SOURCE[0]}" "$UNICA_MAKE_ROM_SNAPSHOT_PATH" || {
        rm -f -- "$UNICA_MAKE_ROM_SNAPSHOT_PATH"
        exit 1
    }
    export UNICA_MAKE_ROM_SNAPSHOT=1
    export UNICA_MAKE_ROM_SNAPSHOT_PATH
    trap 'rm -f -- "$UNICA_MAKE_ROM_SNAPSHOT_PATH"' EXIT
    exec bash "$UNICA_MAKE_ROM_SNAPSHOT_PATH" "$@"
fi

# [
source "$SRC_DIR/scripts/utils/build_utils.sh" || exit 1

FORCE=false
USE_APK_CACHE=false
BUILD_ROM=false
BUILD_ZIP=true
SKIP_DEBUG_INSTALL=false
DEBUG=false
BETA=false

START_TIME="$(date +%s)"

SOURCE_FIRMWARE_PATH="$(cut -d "/" -f 1 -s <<< "$SOURCE_FIRMWARE")_$(cut -d "/" -f 2 -s <<< "$SOURCE_FIRMWARE")"
TARGET_FIRMWARE_PATH="$(cut -d "/" -f 1 -s <<< "$TARGET_FIRMWARE")_$(cut -d "/" -f 2 -s <<< "$TARGET_FIRMWARE")"
APK_CACHE_DIR="$OUT_DIR/target/$TARGET_CODENAME/apk_cache"
APK_DECODE_CACHE_DIR="$OUT_DIR/target/$TARGET_CODENAME/apk_decode_cache"

GET_PATCHED_APK_TREE_HASH()
{
    [ -d "$APKTOOL_DIR" ] || return 1

    find "$APKTOOL_DIR" -type f -print0 | sort -z | \
        xargs -0 sha256sum | sha256sum | cut -d " " -f 1
}

GET_BUILT_APK_PATH()
{
    local RELATIVE_PATH="$1"
    local PARTITION
    local FILE

    PARTITION="$(cut -d "/" -f 1 -s <<< "$RELATIVE_PATH")"
    FILE="$(cut -d "/" -f 2- -s <<< "$RELATIVE_PATH")"

    case "$PARTITION" in
        "system")
            echo "$WORK_DIR/system/system/$FILE"
            ;;
        "system_ext")
            if $TARGET_OS_BUILD_SYSTEM_EXT_PARTITION; then
                echo "$WORK_DIR/system_ext/$FILE"
            else
                echo "$WORK_DIR/system/system/system_ext/$FILE"
            fi
            ;;
        *)
            echo "$WORK_DIR/$PARTITION/$FILE"
            ;;
    esac
}

RESTORE_APK_CACHE()
{
    local TREE_HASH
    local RELATIVE_PATH
    local OUTPUT_FILE

    TREE_HASH="$(GET_PATCHED_APK_TREE_HASH)" || return 1
    [ -f "$APK_CACHE_DIR/.tree_hash" ] || return 1
    [ "$(cat "$APK_CACHE_DIR/.tree_hash")" = "$TREE_HASH" ] || return 1

    while IFS= read -r -d '' f; do
        RELATIVE_PATH="${f/$APKTOOL_DIR\//}"
        OUTPUT_FILE="$(GET_BUILT_APK_PATH "$RELATIVE_PATH")"
        [ -f "$APK_CACHE_DIR/files/$RELATIVE_PATH" ] || return 1
        mkdir -p "$(dirname "$OUTPUT_FILE")"
        cp -a "$APK_CACHE_DIR/files/$RELATIVE_PATH" "$OUTPUT_FILE"
    done < <(find "$APKTOOL_DIR" -type d \( -name "*.apk" -o -name "*.jar" \) -print0)

    LOG "- Reused APK/JAR cache ($TREE_HASH)"
    return 0
}

UPDATE_APK_CACHE()
{
    local TREE_HASH
    local RELATIVE_PATH
    local OUTPUT_FILE

    [ -d "$APKTOOL_DIR" ] || return 0
    TREE_HASH="$(GET_PATCHED_APK_TREE_HASH)" || return 1

    rm -rf "$APK_CACHE_DIR"
    mkdir -p "$APK_CACHE_DIR/files"

    while IFS= read -r -d '' f; do
        RELATIVE_PATH="${f/$APKTOOL_DIR\//}"
        OUTPUT_FILE="$(GET_BUILT_APK_PATH "$RELATIVE_PATH")"
        [ -f "$OUTPUT_FILE" ] || return 1
        mkdir -p "$APK_CACHE_DIR/files/$(dirname "$RELATIVE_PATH")"
        cp -a "$OUTPUT_FILE" "$APK_CACHE_DIR/files/$RELATIVE_PATH"
    done < <(find "$APKTOOL_DIR" -type d \( -name "*.apk" -o -name "*.jar" \) -print0)

    printf '%s' "$TREE_HASH" > "$APK_CACHE_DIR/.tree_hash"
    LOG "- Updated APK/JAR cache ($TREE_HASH)"
}

BUILD_APKS()
{
    local MAX_JOBS
    MAX_JOBS="$(nproc)"
    [ "$MAX_JOBS" -gt "8" ] && MAX_JOBS="8"

    if [ -d "$APKTOOL_DIR" ]; then
        LOG_STEP_IN true "Building APKs/JARs"

        # shellcheck disable=SC2016
        find "$APKTOOL_DIR" -type d \( -name "*.apk" -o -name "*.jar" \) -print0 | xargs -0 -I "{}" -P "$MAX_JOBS" \
            bash -c '
                FILE="${1/$APKTOOL_DIR\//}"
                PARTITION="$(cut -d "/" -f 1 -s <<< "$FILE")"
                [[ "$PARTITION" != "system" ]] && FILE="$(cut -d "/" -f 2- -s <<< "$FILE")"
                "$SRC_DIR/scripts/apktool.sh" b -j "$2" "$PARTITION" "$FILE"
            ' "bash" "{}" "$MAX_JOBS" || exit 1

        LOG_STEP_OUT
    fi
}

GET_WORK_DIR_HASH()
{
    # A reusable work directory depends on more than shell modules. Samsung
    # prebuilts, AVB/signing assets, and build configuration can change without
    # touching scripts/unica/platform/target. Hash their actual bytes and paths.
    local INPUTS=(
        "$SRC_DIR/scripts"
        "$SRC_DIR/unica"
        "$SRC_DIR/target/$TARGET_CODENAME"
        "$SRC_DIR/prebuilts"
        "$SRC_DIR/security"
        "$SRC_DIR/buildenv.sh"
        "$SRC_DIR/.gitmodules"
    )
    local ITEM
    local INPUT_HASH

    if [[ "$TARGET_PLATFORM" != "none" ]]; then
        INPUTS+=("$SRC_DIR/platform/$TARGET_PLATFORM")
    fi
    for ITEM in "${INPUTS[@]}"; do
        if [ ! -e "$ITEM" ]; then
            LOGE "Cannot reuse work directory: missing source input $ITEM"
            return 1
        fi
    done

    INPUT_HASH="$(
        set -o pipefail
        find -H "${INPUTS[@]}" -type f -print0 |
            LC_ALL=C sort -z |
            xargs -0 -r sha256sum |
            sha256sum | cut -d " " -f 1
    )" || return 1

    # Distinguish firmware/model selections even if all tracked files match.
    printf '%s\n' "$INPUT_HASH" "${SOURCE_FIRMWARE:-}" "${TARGET_FIRMWARE:-}" \
        "$TARGET_CODENAME" "$TARGET_PLATFORM" |
        sha256sum | cut -d " " -f 1
}

PREPARE_SCRIPT()
{
    while [[ "$#" != 0 ]]; do
        if [[ "$1" == "--force" ]] || [[ "$1" == "-f" ]]; then
            FORCE=true
        elif [[ "$1" == "--use-apk-cache" ]] || [[ "$1" == "-c" ]]; then
            USE_APK_CACHE=true
        elif [[ "$1" == "--no-rom-zip" ]] || [[ "$1" == "-z" ]]; then
            BUILD_ZIP=false
	elif [[ "$1" == "--debug" ]] || [[ "$1" == "-d" ]]; then
            DEBUG=true
        elif [[ "$1" == "--beta" ]] || [[ "$1" == "-b" ]]; then
            BETA=true
        else
            if [[ "$1" == "-"* ]]; then
                LOGE "Unknown option: $1"
            fi
            PRINT_USAGE
            exit 1
        fi

        shift
    done
}

# shellcheck disable=SC2317,SC2329
PRINT_BUILD_OUTCOME()
{
    local EXIT_CODE="$?"
    local END_TIME
    local ESTIMATED

    [ -n "${UNICA_MAKE_ROM_SNAPSHOT_PATH:-}" ] && \
        rm -f -- "$UNICA_MAKE_ROM_SNAPSHOT_PATH"

    END_TIME="$(date +%s)"
    ESTIMATED="$((END_TIME - START_TIME))"

    if [[ "$EXIT_CODE" != "0" ]]; then
        echo -n -e '\n\033[1;31m'"Build failed "
    else
        echo -n -e '\n\033[1;32m'"Build completed "
    fi
    echo -e "in $((ESTIMATED / 3600))hrs $(((ESTIMATED / 60) % 60))min $((ESTIMATED % 60))sec."'\033[0m\n'
}

PRINT_USAGE()
{
    echo "Usage: make_rom [options]" >&2
    echo " -f, --force : Force ROM build" >&2
    echo " -c, --use-apk-cache : Reuse decoded and compiled APKs/JARs when sources match" >&2
    echo " --no-rom-zip : Do not build ROM zip" >&2
    echo " -d, --debug : Create a debug build" >&2
    echo " -b, --beta : Create a beta build" >&2
}
# ]

PREPARE_SCRIPT "$@"

# apktool.sh is also invoked indirectly by patch modules. Exporting the cache
# policy here lets every decode participate without changing module scripts.
export APK_DECODE_CACHE_DIR
if $USE_APK_CACHE; then
    export APK_DECODE_CACHE_MODE="reuse"
else
    export APK_DECODE_CACHE_MODE="refresh"
    rm -rf "$APK_DECODE_CACHE_DIR"
fi

# A completed work tree can be reused only when the caller explicitly opts
# into caching, its source hash still matches, both firmware extractions exist,
# and the expected compiled output files are present. A stale or incomplete
# tree must be removed before create_work_dir.sh rebuilds it.
BUILD_ROM=true
if ! $FORCE && $USE_APK_CACHE && \
        [ -f "$WORK_DIR/.completed" ] && \
        [ -f "$FW_DIR/$SOURCE_FIRMWARE_PATH/.extracted" ] && \
        [ -f "$FW_DIR/$TARGET_FIRMWARE_PATH/.extracted" ] && \
        [ -s "$WORK_DIR/system/system/build.prop" ] && \
        [ -s "$WORK_DIR/vendor/build.prop" ]; then
    CURRENT_WORK_DIR_HASH="$(GET_WORK_DIR_HASH)" || exit 1
    if [[ "$(cat "$WORK_DIR/.completed")" == "$CURRENT_WORK_DIR_HASH" ]]; then
        LOGW "No changes have been detected in the build environment"
        BUILD_ROM=false
    else
        LOGW "Changes detected in the build environment"
    fi
fi

if $BUILD_ROM && [ -d "$WORK_DIR" ]; then
    LOG "- Cleaning previous work dir"
    rm -rf "${WORK_DIR:?}" || exit 1
fi

trap 'PRINT_BUILD_OUTCOME' EXIT
trap 'echo' INT

if $BUILD_ROM; then
    [ -d "$APKTOOL_DIR" ] && rm -rf "$APKTOOL_DIR"

    if [ ! -f "$FW_DIR/$SOURCE_FIRMWARE_PATH/.extracted" ] || [ ! -f "$FW_DIR/$TARGET_FIRMWARE_PATH/.extracted" ]; then
        if [ ! -f "$ODIN_DIR/$SOURCE_FIRMWARE_PATH/.downloaded" ] || [ ! -f "$ODIN_DIR/$TARGET_FIRMWARE_PATH/.downloaded" ]; then
            LOG_STEP_IN true "Downloading required firmwares"
            "$SRC_DIR/scripts/download_fw.sh" || exit 1
            LOG_STEP_OUT
        fi
        LOG_STEP_IN true "Extracting required firmwares"
        "$SRC_DIR/scripts/extract_fw.sh" || exit 1
        LOG_STEP_OUT
    fi

    LOG_STEP_IN true "Creating work dir"
    "$SRC_DIR/scripts/internal/create_work_dir.sh" || exit 1
    LOG_STEP_OUT

    if [ -d "$SRC_DIR/platform/$TARGET_PLATFORM/patches" ]; then
        LOG_STEP_IN true "Applying platform patches"
        "$SRC_DIR/scripts/internal/apply_modules.sh" "$SRC_DIR/platform/$TARGET_PLATFORM/patches" || exit 1
        LOG_STEP_OUT
    fi
    if [ -d "$SRC_DIR/target/$TARGET_CODENAME/patches" ]; then
        LOG_STEP_IN true "Applying device patches"
        "$SRC_DIR/scripts/internal/apply_modules.sh" "$SRC_DIR/target/$TARGET_CODENAME/patches" || exit 1
        LOG_STEP_OUT
    fi
    if [ -d "$SRC_DIR/unica/patches" ]; then
        LOG_STEP_IN true "Applying ROM patches"
        "$SRC_DIR/scripts/internal/apply_modules.sh" "$SRC_DIR/unica/patches" || exit 1
        LOG_STEP_OUT
    fi

    if [ -d "$SRC_DIR/unica/mods" ]; then
        LOG_STEP_IN true "Applying ROM mods"
        "$SRC_DIR/scripts/internal/apply_modules.sh" "$SRC_DIR/unica/mods" || exit 1
        LOG_STEP_OUT
    fi

    if $USE_APK_CACHE && RESTORE_APK_CACHE; then
        LOG "Skipping APK/JAR compilation"
    else
        if $USE_APK_CACHE; then
            LOGW "APK/JAR cache is missing or stale. Rebuilding it."
        fi
        BUILD_APKS
        UPDATE_APK_CACHE || exit 1
    fi

    # A completed work tree must have a verified input hash. A failed or
    # malformed digest must not produce a success marker.
    WORK_DIR_HASH="$(GET_WORK_DIR_HASH)" || {
        LOGE "Cannot mark completed work directory: input hashing failed"
        exit 1
    }
    if [[ ! "$WORK_DIR_HASH" =~ ^[[:xdigit:]]{64}$ ]]; then
        LOGE "Cannot mark completed work directory: invalid input hash"
        exit 1
    fi
    printf '%s' "$WORK_DIR_HASH" > "$WORK_DIR/.completed" || exit 1
fi

if $BUILD_ZIP; then
    LOG_STEP_IN true "Creating zip"
    "$SRC_DIR/scripts/internal/build_flashable_zip.sh" || exit 1
    LOG_STEP_OUT
fi

exit 0
