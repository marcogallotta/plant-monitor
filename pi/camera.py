from typing import Protocol, runtime_checkable


@runtime_checkable
class Camera(Protocol):
    def capture(self) -> bytes: ...


class FakeCamera:
    def capture(self) -> bytes:
        return b"FAKEJPEG"


class PiCamera:
    # Fixed manual focus for the down-pointing mount. The camera points down at
    # the plants (~2.5 m); the Module 3 lens sags under gravity, so autofocus
    # bails to infinity and never lands on the plants. Two-part fix:
    #   1. tuning file rpi.af "map" adjusted for gravity (445->380, 925->880 in
    #      /usr/share/libcamera/ipa/rpi/vc4/imx708.json), and
    #   2. lock manual focus at the measured sharpness peak below.
    # Override with the LENS_POSITION env var if the mount/distance changes.
    LENS_POSITION = 1.0

    def capture(self) -> bytes:
        import io
        import os
        import sys
        import time
        from picamera2 import Picamera2  # only available on real Pi hardware
        from PIL import Image
        lens_position = float(os.getenv("LENS_POSITION", self.LENS_POSITION))
        cam = Picamera2()
        cam.configure(cam.create_still_configuration())  # full sensor resolution
        cam.start()
        try:
            try:
                from libcamera import controls
                # Clamp to the lens's supported range so a bad env override
                # can't push LensPosition out of bounds.
                lp_ctrl = cam.camera_controls.get("LensPosition")
                if lp_ctrl:
                    lp_min, lp_max, _ = lp_ctrl
                    lens_position = max(lp_min, min(lp_max, lens_position))
                cam.set_controls(
                    {"AfMode": controls.AfModeEnum.Manual, "LensPosition": lens_position}
                )
                time.sleep(0.6)  # let the lens settle before capture
                md = cam.capture_metadata()
                print(
                    f"manual focus LensPosition={md.get('LensPosition')} "
                    f"FocusFoM={md.get('FocusFoM')}",
                    file=sys.stderr,
                )
            except Exception as e:  # focus control not supported on this module
                print(f"focus control unavailable: {e}", file=sys.stderr)
            buf = cam.capture_array()
        finally:
            cam.stop()
            cam.close()
        img = Image.fromarray(buf)
        if img.mode != "RGB":
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90)  # inspection images, favour detail
        return out.getvalue()
