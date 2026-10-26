#!/usr/bin/env bash
# Lightweight end-to-end packaging smoke test using synthetic ext4 payloads.
# It executes the REAL S10 packager but never requires Samsung firmware,
# block devices, root, or a working device.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-beyond2lte}"
case "$TARGET" in
  beyond0lte) MODELS="SM-G970F:SM-G970N" ;;
  beyond1lte) MODELS="SM-G973F:SM-G973N" ;;
  beyond2lte) MODELS="SM-G975F:SM-G975N" ;;
  beyondx) MODELS="SM-G977B:SM-G977N" ;;
  *) echo "Invalid smoke test target: $TARGET" >&2; exit 2 ;;
esac
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
export SRC_DIR="$ROOT/mocksrc" OUT_DIR="$ROOT/out" WORK_DIR="$ROOT/work"
export TARGET_CODENAME="$TARGET" TARGET_ASSERT_MODEL="$MODELS"
export TARGET_PLATFORM="exynos9820" TARGET_USE_DYNAMIC_PARTITIONS=false
export TARGET_OS_FILE_SYSTEM_TYPE="ext4" TARGET_OS_BUILD_SYSTEM_EXT_PARTITION=false
export UNICA_S10_PIT_VERIFIED=1 UNICA_S10_BOOT_VERIFIED=1 ROM_VERSION="smoke"
export TARGET_SYSTEM_PARTITION_SIZE=2097152 TARGET_VENDOR_PARTITION_SIZE=2097152
export TARGET_PRODUCT_PARTITION_SIZE=2097152 TARGET_ODM_PARTITION_SIZE=2097152
mkdir -p "$ROOT/bin" "$SRC_DIR/scripts/utils" "$SRC_DIR/scripts" \
  "$SRC_DIR/prebuilts/bootable/deprecated-ota" "$SRC_DIR/security" \
  "$OUT_DIR" "$WORK_DIR/configs"
printf '#!/bin/sh\n' > "$SRC_DIR/prebuilts/bootable/deprecated-ota/updater"
touch "$SRC_DIR/security/aosp_testkey.x509.pem" "$SRC_DIR/security/aosp_testkey.pk8"
cat > "$SRC_DIR/scripts/utils/build_utils.sh" <<'EOF'
LOG() { :; }
LOGE() { echo "$*" >&2; }
GET_IMAGE_SIZE() { stat -c %s "$1"; }
EOF
cat > "$SRC_DIR/scripts/utils/install_utils.sh" <<'EOF'
GET_DEVICE_FROM_MOUNTPOINT() {
  case "$1" in /system|/vendor|/product|/odm|/boot)
    printf '"/dev/block/by-name/%s"' "${1#/}";;
  *) return 1 ;;
  esac
}
EOF
cat > "$SRC_DIR/scripts/build_fs_image.sh" <<'EOF'
#!/usr/bin/env bash
set -e
out=""
while (( $# )); do
  if [[ "$1" == "-o" ]]; then shift; out="$1"; fi
  shift
done
[[ -n "$out" ]]
truncate -s 4096 "$out"
EOF
cat > "$ROOT/bin/img2sdat" <<'EOF'
#!/usr/bin/env bash
set -e
out=""
last=""
while (( $# )); do
  case "$1" in -o) shift; out="$1" ;; -B) shift ;; *) last="$1" ;; esac
  shift
done
[[ -n "$out" && -n "$last" ]]
part="${last##*/}"
part="${part%.img}"
printf '4\n1\n0\n0\nnew 2,0,1\n' > "$out/$part.transfer.list"
truncate -s 4096 "$out/$part.new.dat"
if [[ "${S10_MOCK_NO_PATCH:-0}" != "1" ]]; then
  : > "$out/$part.patch.dat"
fi
EOF
cat > "$ROOT/bin/brotli" <<'EOF'
#!/usr/bin/env bash
set -e
out=""
input=""
for a in "$@"; do
  case "$a" in --output=*) out="${a#--output=}" ;; --quality=*) ;; *) input="$a" ;; esac
done
cp "$input" "$out"
EOF
cat > "$ROOT/bin/7z" <<'EOF'
#!/usr/bin/env bash
set -e
[[ "$1" == "a" && "$2" == "-tzip" && "$3" == "-mx=5" ]]
archive="$5"
shift 5
zip -q -0 -r "$archive" "$@"
EOF
cat > "$ROOT/bin/signapk" <<'EOF'
#!/usr/bin/env bash
set -e
cp "${@: -2:1}" "${@: -1}"
EOF
chmod +x "$SRC_DIR/scripts/build_fs_image.sh" "$ROOT/bin/"*
export PATH="$ROOT/bin:$PATH"
mkdir -p "$WORK_DIR/kernel"
# Synthetic image for packaging contract testing only, not a bootable kernel.
printf 'ANDROID!' > "$WORK_DIR/kernel/boot.img"
truncate -s 4096 "$WORK_DIR/kernel/boot.img"
export TARGET_BOOT_PARTITION_SIZE=2097152
export TARGET_BOOT_IMAGE_SHA256="$(sha256sum "$WORK_DIR/kernel/boot.img" | cut -d ' ' -f1)"
for p in system vendor product odm; do
  mkdir -p "$WORK_DIR/$p"
  printf '%s\n' "$p" > "$WORK_DIR/$p/file.txt"
  printf 'test\n' > "$WORK_DIR/configs/file_context-$p"
  printf 'test\n' > "$WORK_DIR/configs/fs_config-$p"
done

PACKAGER="$REPO/scripts/internal/build_legacy_flashable_zip.sh"
bash "$PACKAGER"
ARCHIVE="$OUT_DIR/RebirthROM_EXPERIMENTAL_smoke_$TARGET.zip"
test -s "$ARCHIVE"
unzip -tqq "$ARCHIVE"
unzip -Z1 "$ARCHIVE" | grep -qx "boot.img"
SCRIPT="$(unzip -p "$ARCHIVE" META-INF/com/google/android/updater-script)"
[[ "$SCRIPT" == *'ro.boot.em.model'* ]]
[[ "$SCRIPT" == *"${MODELS%%:*}"* ]]
[[ "$SCRIPT" != *"update_dynamic_partitions"* ]]
[[ "$SCRIPT" != *"map_partition("* ]]
[[ "$SCRIPT" == *'package_extract_file("boot.img"'* ]]
for p in system vendor product odm; do
  unzip -Z1 "$ARCHIVE" | grep -qx "$p.transfer.list"
  unzip -Z1 "$ARCHIVE" | grep -qx "$p.new.dat.br"
  unzip -Z1 "$ARCHIVE" | grep -qx "$p.patch.dat"
  [[ "$SCRIPT" == *"/dev/block/by-name/$p"* ]]
done
unzip -p "$ARCHIVE" check-partitions.sh > "$ROOT/check-partitions.sh"
sh -n "$ROOT/check-partitions.sh"
python3 "$REPO/tests/test_recovery_capacity.py" "$ROOT/check-partitions.sh"
[[ "$SCRIPT" == *'NOT SAFE TO FLASH'* ]]
CHECK_LINE="$(grep -n 'run_program' <<< "$SCRIPT" | cut -d: -f1)"
WRITE_LINE="$(grep -n 'block_image_update' <<< "$SCRIPT" | head -1 | cut -d: -f1)"
(( CHECK_LINE < WRITE_LINE ))
test -s "$ARCHIVE.sha256"
sha256sum --check --status "$ARCHIVE.sha256"
# Regression: missing patch payload must fail before producing a valid ZIP.
rm -f "$ARCHIVE"
export S10_MOCK_NO_PATCH=1
if bash "$PACKAGER" > "$ROOT/negative.log" 2>&1; then
  echo "ERROR: incomplete transfer payload was accepted" >&2
  exit 1
fi
test ! -f "$ARCHIVE"
unset S10_MOCK_NO_PATCH
# Regression: wrong boot hash must never make a signed ROM ZIP.
rm -f "$ARCHIVE"
export TARGET_BOOT_IMAGE_SHA256="$(printf 0%.0s {1..64})"
if bash "$PACKAGER" > "$ROOT/badhash.log" 2>&1; then
  echo "ERROR: unreviewed boot image was accepted" >&2
  exit 1
fi
test ! -f "$ARCHIVE"
export TARGET_BOOT_IMAGE_SHA256="$(sha256sum "$WORK_DIR/kernel/boot.img" | cut -d ' ' -f1)"

# Regression: explicit build opt-in is required.
unset UNICA_S10_PIT_VERIFIED
if bash "$PACKAGER" > "$ROOT/pit.log" 2>&1; then
  echo "ERROR: missing PIT validation marker was accepted" >&2
  exit 1
fi
echo "S10 legacy packaging smoke test passed for $TARGET"
