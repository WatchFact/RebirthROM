#!/usr/bin/env python3
"""Guarded Android-16 SamsungCamera scene/text callback bridge for Exynos9820.

Every expected donor class and bytecode anchor is validated before any writes.
This is not evidence of camera operation or device boot compatibility.
"""
import argparse
from pathlib import Path
import re

PREFIX = "com/samsung/android/camera/core2/"
FORWARDER = "callback/forwarder/TextDetectionInfoCallbackForwarder.smali"
MANAGER = "maker/MakerCallbackManager.smali"
CALLBACKS = (
    "AutoBeautyPhotoMaker$6", "AutoPhotoMaker$4", "BeautyPhotoMaker$7",
    "DualBokehPhotoMaker$2", "SuperNightPhotoMaker$2",
)
FIELD = "Lcom/samsung/android/camera/core2/callback/forwarder/TextDetectionInfoCallbackForwarder;->sceneDetectionEvent:I"
SCENE_NODE = "Lcom/samsung/android/camera/core2/node/sceneDetection/SceneDetectionNodeBase$NodeCallback;"
SEND_SIGNATURE = ".method public sendTextDetectionInfoCallback(Lcom/samsung/android/camera/core2/CamDevice;Ljava/lang/Long;Landroid/hardware/camera2/CaptureResult;)V"


def unique_class(decoded: Path, suffix: str) -> Path:
    paths = sorted(p for p in decoded.glob("smali*/" + PREFIX + suffix) if p.is_file())
    if len(paths) != 1:
        raise ValueError(f"Expected one decoded class {suffix}; found {len(paths)}")
    return paths[0]


def one_replace(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{label}: expected exactly one donor anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def patch_forwarder(s: str) -> str:
    if "sceneDetectionEvent" in s or ".method static constructor <clinit>()V" in s:
        raise ValueError("forwarder changed: scene field or static constructor already exists")
    if ".implements Lcom/samsung/android/camera/core2/callback/TextDetectionInfoCallback;" not in s:
        raise ValueError("unexpected forwarder interface")
    field = "# static fields\n.field public static volatile sceneDetectionEvent:I\n\n\n"
    s = one_replace(s, "# direct methods\n", field + "# direct methods\n", "forwarder fields")
    init = (".method static constructor <clinit>()V\n"
            "    .locals 1\n\n"
            "    const/4 v0, -0x1\n\n"
            f"    sput v0, {FIELD}\n\n"
            "    return-void\n.end method\n\n")
    return one_replace(s, "# direct methods\n", "# direct methods\n" + init, "forwarder init")


def patch_callback(s: str, name: str) -> str:
    if f".implements {SCENE_NODE}" not in s:
        raise ValueError(f"{name}: missing expected scene node interface")
    if FIELD in s:
        raise ValueError(f"{name}: scene bridge already present")
    # Capture the scene index before Optional.ifPresent drops an unregistered callback.
    match = re.search(r"(?m)^\.method public a\(I\[J\)V\n    \.locals ([0-9]+)\n", s)
    if not match or int(match.group(1)) < 2 or len(re.findall(r"(?m)^\.method public a\(I\[J\)V$", s)) != 1:
        raise ValueError(f"{name}: incompatible node callback signature/register count")
    body_end = s.find(".end method", match.end())
    if body_end == -1 or "->getSceneDetectionEventCallback()" not in s[match.end():body_end]:
        raise ValueError(f"{name}: node callback dispatch differs from inspected donor")
    return s[:match.end()] + f"\n    sput p1, {FIELD}\n" + s[match.end():]


def patch_manager(s: str) -> str:
    if FIELD in s or ":rebirth_scene_" in s:
        raise ValueError("manager bridge already present")
    if s.count(SEND_SIGNATURE) != 1:
        raise ValueError("donor text callback method signature differs")
    start = s.index(SEND_SIGNATURE)
    end = s.find(".end method", start)
    if end < 0:
        raise ValueError("donor text callback method is incomplete")
    method = s[start:end]
    if "    .locals 2" not in method.splitlines()[:3]:
        raise ValueError("donor text callback register allocation differs")
    if "SemCaptureResult;->y1:Landroid/hardware/camera2/CaptureResult$Key;" not in method:
        raise ValueError("donor text callback capture-result key differs")
    if "->onTextDetectionInfo(Ljava/lang/Long;Ljava/lang/Integer;Lcom/samsung/android/camera/core2/CamDevice;)V" not in method:
        raise ValueError("donor text callback dispatch differs")
    anchor = "    check-cast p3, Ljava/lang/Integer;\n"
    # Preserve the Android-16 HAL text flag. Only when it is absent use the
    # legacy scene event, mapping scene IDs 2 and 39 to text detected.
    bridge = (f"\n    if-nez p3, :rebirth_scene_done\n\n"
              f"    sget v1, {FIELD}\n\n"
              "    const/4 p3, 0x0\n\n"
              "    const/4 v2, 0x2\n\n"
              "    if-eq v1, v2, :rebirth_scene_true\n\n"
              "    const/16 v2, 0x27\n\n"
              "    if-ne v1, v2, :rebirth_scene_false\n\n"
              "    :rebirth_scene_true\n"
              "    const/4 p3, 0x1\n\n"
              "    :rebirth_scene_false\n"
              "    invoke-static {p3}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;\n\n"
              "    move-result-object p3\n\n"
              "    :rebirth_scene_done\n")
    # v0 contains the live TextDetectionInfoCallback object; never clobber it.
    method = one_replace(method, "    .locals 2\n", "    .locals 3\n", "manager register expansion")
    method = one_replace(method, anchor, anchor + bridge, "manager fallback")
    return s[:start] + method + s[end:]


def adapt(decoded: Path) -> list[Path]:
    if not decoded.is_dir():
        raise ValueError(f"decoded APK directory missing: {decoded}")
    edits = {}
    p = unique_class(decoded, FORWARDER)
    edits[p] = patch_forwarder(p.read_text(encoding="utf-8"))
    p = unique_class(decoded, MANAGER)
    edits[p] = patch_manager(p.read_text(encoding="utf-8"))
    for name in CALLBACKS:
        p = unique_class(decoded, f"maker/{name}.smali")
        edits[p] = patch_callback(p.read_text(encoding="utf-8"), name)
    # No modifications occur if any donor compatibility check fails.
    for p, result in edits.items():
        if not result.endswith("\n") or result.count(".method ") != result.count(".end method"):
            raise ValueError(f"{p.name}: invalid method boundaries after transformation")
    for p, result in edits.items():
        p.write_text(result, encoding="utf-8")
    return list(edits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decoded_apk", type=Path)
    args = parser.parse_args()
    try:
        files = adapt(args.decoded_apk)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"S10 camera bridge incompatible with donor: {exc}\n")
    print(f"Applied guarded S10 scene/text callback bridge to {len(files)} decoded classes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
