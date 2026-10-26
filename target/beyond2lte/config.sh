#
# Copyright (C) 2024 BlackMesa123
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

# Device configuration file for Galaxy S10+ (Exynos) (beyond2lte)
TARGET_NAME="Galaxy S10+ (Exynos)"
TARGET_CODENAME="beyond2lte"
TARGET_ASSERT_MODEL=("SM-G975F" "SM-G975N")
TARGET_PLATFORM="exynos9820"
TARGET_FIRMWARE="SM-G975F/AUT/356262101234561"
TARGET_EXTRA_FIRMWARES=()

# SEC Product Feature
TARGET_LCD_CONFIG_CONTROL_AUTO_BRIGHTNESS="4"
TARGET_FINGERPRINT_CONFIG_SENSOR="google_touch_display_ultrasonic"
TARGET_COMMON_CONFIG_MDNIE_MODE="65303"
TARGET_LCD_CONFIG_COLOR_WEAKNESS_SOLUTION="3"
TARGET_AUDIO_SUPPORT_ACH_RINGTONE=false

# Shared Exynos9820 modern build variables: platform/exynos9820/config.sh
# Per-device additional overrides
TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME="siop_beyond2_exynos9820"
TARGET_CAMERA_SUPPORT_MASS_APP_FLAVOR=false
TARGET_LCD_CONFIG_HFR_MODE="0"
TARGET_LCD_CONFIG_HFR_SUPPORTED_REFRESH_RATE="60"
