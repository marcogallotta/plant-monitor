import json
import os
from datetime import datetime, timezone
from pathlib import Path

from camera import Camera


def run_capture(camera: Camera, output_dir: Path, now: datetime | None = None) -> None:
    if now is None:
        now = datetime.now(tz=timezone.utc)

    stem = now.strftime("%Y-%m-%dT%H%M%SZ")
    image_filename = f"{stem}.jpg"

    output_dir.mkdir(parents=True, exist_ok=True)

    image_bytes = camera.capture()

    image_path = output_dir / image_filename
    meta_path = output_dir / f"{stem}.json"
    image_tmp = image_path.with_suffix(".jpg.tmp")
    meta_tmp = meta_path.with_suffix(".json.tmp")

    try:
        image_tmp.write_bytes(image_bytes)
        meta_tmp.write_text(
            json.dumps({"captured_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "filename": image_filename})
        )
        image_tmp.rename(image_path)
        meta_tmp.rename(meta_path)
    except Exception:
        image_tmp.unlink(missing_ok=True)
        meta_tmp.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    import sys
    from camera import FakeCamera, PiCamera

    camera_type = os.getenv("CAMERA", "fake")
    camera = PiCamera() if camera_type == "pi" else FakeCamera()

    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("capture")
    run_capture(camera=camera, output_dir=output_dir)
