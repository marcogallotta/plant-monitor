from typing import Protocol, runtime_checkable


@runtime_checkable
class Camera(Protocol):
    def capture(self) -> bytes: ...


class FakeCamera:
    def capture(self) -> bytes:
        return b"FAKEJPEG"


class PiCamera:
    def capture(self) -> bytes:
        import io
        from picamera2 import Picamera2  # only available on real Pi hardware
        from PIL import Image
        cam = Picamera2()
        cam.start()
        try:
            buf = cam.capture_array()
        finally:
            cam.stop()
            cam.close()
        img = Image.fromarray(buf)
        out = io.BytesIO()
        img.save(out, format="JPEG")
        return out.getvalue()
