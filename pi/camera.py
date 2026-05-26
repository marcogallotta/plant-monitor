from typing import Protocol, runtime_checkable


@runtime_checkable
class Camera(Protocol):
    def capture(self) -> bytes: ...


class FakeCamera:
    def capture(self) -> bytes:
        return b"FAKEJPEG"


class PiCamera:
    def capture(self) -> bytes:
        from picamera2 import Picamera2  # only available on real Pi hardware
        cam = Picamera2()
        cam.start()
        buf = cam.capture_array()
        cam.stop()
        cam.close()
        # encode to JPEG bytes
        import io
        from PIL import Image
        img = Image.fromarray(buf)
        out = io.BytesIO()
        img.save(out, format="JPEG")
        return out.getvalue()
