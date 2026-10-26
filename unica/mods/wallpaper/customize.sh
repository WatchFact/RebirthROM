#!/usr/bin/env bash
# Copyright (c) 2026 At30c
# SPDX-License-Identifier: GPL-3.0-or-later

# shellcheck disable=SC2034
SKIPUNZIP=1

# Only use a wallpaper-res donor that matches the device being built.
# The legacy S10 trees currently have no beyond*xxx prebuilt; skip safely.
# Never pull S20/Note20 wallpapers or reuse another device's panel assets.

WALLPAPER_DONOR="${TARGET_CODENAME}xxx"

if [ ! -d "$SRC_DIR/prebuilts/samsung/$WALLPAPER_DONOR" ]; then
    LOG "- No wallpaper-res donor for \"$TARGET_CODENAME\"; skipping"
    return 0
fi

LOG_STEP_IN "- Adding stock wallpapers from $WALLPAPER_DONOR"
ADD_TO_WORK_DIR "$WALLPAPER_DONOR" "system" \
    "system/priv-app/wallpaper-res/wallpaper-res.apk" \
    0 0 644 "u:object_r:system_file:s0" || return 1
LOG_STEP_OUT

unset WALLPAPER_DONOR

return 0
