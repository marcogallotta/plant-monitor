import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from camera import Camera


def _capture_plate(camera: Camera, n: int) -> bytes:
    """Capture n frames and collapse them to a per-pixel MEAN plate.

    Averaging a short burst (same light, no real change) cancels foliage sway,
    which a single frame can't (see docs/ai-tagging-design.md). A MEAN is used
    rather than a median because it streams: each frame is decoded, added to a
    running accumulator, and discarded — so nothing is staged to the SD card
    (no flash wear beyond the final plate) and peak RAM stays well under the
    512MB Pi's budget. The accumulate and the divide are done in horizontal
    strips so no full-frame temporary is ever materialised. numpy+PIL only — no
    cv2 on the Pi. Undecodable bytes (the test FakeCamera) fall back to the
    first frame, no collapse.

    Mean (not median) is a deliberate, measured choice: on real Pi bursts the
    mean plate's residual sway floor was ~5.45 vs the median's ~5.01 (~9% worse),
    but the mean STREAMS — no frames staged to the SD card — so flash wear stays
    at the single-frame baseline at any cadence. The 9% costs little for a rough
    harvest read; the trade-off bought is zero staging wear. Mean's only real
    loss vs median is rejecting a rare one-frame outlier (a bird/hand mid-frame
    ghosts in at ~1/n); acceptable, and the next capture is clean.
    """
    import sys
    import numpy as np
    from PIL import Image

    # uint16 accumulator: n frames * 255 must fit (<= 65535).
    if not 1 <= n <= 257:
        raise ValueError(f"frames must be 1..257 for the uint16 accumulator, got {n}")

    acc = None
    first_bytes = None
    count = 0
    for i in range(n):
        data = camera.capture()
        if first_bytes is None:
            first_bytes = data
        try:
            arr = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), dtype=np.uint8)
        except Exception as e:
            if acc is None:
                return first_bytes  # first frame not an image (FakeCamera) — skip collapse
            print(f"capture: frame {i} failed to decode ({e}); skipping", file=sys.stderr)
            continue
        if acc is None:
            acc = np.zeros(arr.shape, dtype=np.uint16)
        elif arr.shape != acc.shape:
            print(f"capture: frame {i} shape {arr.shape} != {acc.shape}; skipping", file=sys.stderr)
            continue
        height = arr.shape[0]
        step = max(1, (height + 7) // 8)
        for y in range(0, height, step):
            acc[y:y + step] += arr[y:y + step]  # uint16 += uint8 strip (temp is one strip)
        count += 1
        del arr, data

    if acc is None or count == 0:
        return first_bytes  # nothing decoded (all frames failed) — fall back

    plate = np.empty(acc.shape, dtype=np.uint8)
    height = acc.shape[0]
    step = max(1, (height + 7) // 8)
    for y in range(0, height, step):
        plate[y:y + step] = ((acc[y:y + step] + count // 2) // count).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(plate).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def run_capture(camera: Camera, output_dir: Path, now: datetime | None = None,
                frames: int = 1) -> None:
    if now is None:
        now = datetime.now(tz=timezone.utc)

    stem = now.strftime("%Y-%m-%dT%H%M%SZ")
    image_filename = f"{stem}.jpg"

    output_dir.mkdir(parents=True, exist_ok=True)

    image_bytes = _capture_plate(camera, frames) if frames > 1 else camera.capture()

    image_path = output_dir / image_filename
    meta_path = output_dir / f"{stem}.json"
    image_tmp = image_path.with_suffix(".jpg.tmp")
    meta_tmp = meta_path.with_suffix(".json.tmp")

    try:
        image_tmp.write_bytes(image_bytes)
        meta = {"captured_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "filename": image_filename}
        if frames > 1:
            # Provenance: this is a derived plate, not a single raw camera JPEG.
            meta.update({"burst_frames": frames, "collapse": "mean", "derived_plate": True})
        meta_tmp.write_text(json.dumps(meta))
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
    # Intended production default: capture a 10-frame burst and save one averaged
    # plate (see _capture_plate). Not experiment residue. Override with BURST_FRAMES.
    frames = int(os.getenv("BURST_FRAMES", "10"))
    run_capture(camera=camera, output_dir=output_dir, frames=frames)
