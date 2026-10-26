# Exynos9820 static S10 integration — current safety boundary

Targets: beyond0lte, beyond1lte, beyond2lte, beyondx. Only their Exynos9820
vendor/ODM/kernel interfaces may be used. Do not import Exynos990 partitions.

The build script now has a separate static recovery packaging path. It never
calls lpmake, update_dynamic_partitions, or formats userdata. It also leaves
boot/dtbo/recovery, EFS, prism and optics untouched.

## Important outstanding prerequisites

1. Verify real system/vendor/product/odm capacities from each target model's
   PIT or block device. Record capacities as TARGET_*_PARTITION_SIZE in the
   device configuration. Do not guess sizes from another S10 model.
2. Audit and pin kernel and DTB/DTBO sources. The legacy ExtremeKRNL module is
   disabled because it builds a moving 'main' branch without verification.
3. Validate the Android 16 donor userspace against the target stock VINTF
   manifest, API 31 vendor interfaces, camera/graphics/radio/audio/NFC HALs,
   kernel modules, init services, and SELinux with real boot logs.
4. Verify the device's AVB/boot chain and recovery implementation.
5. Only after items above, opt into producing an experimental ZIP with
   UNICA_S10_PIT_VERIFIED=1 and UNICA_S10_BOOT_VERIFIED=1.

The opt-in flags are build-time safety gates, not an installer preflight. The
generated package is never automatically published as a working ROM.

The current .github/workflows/build.yml runs source/contract validation only.
No verified kernel image or end-to-end S10 boot test has been produced.
