import json
from pathlib import Path
from typing import Callable


PostFn = Callable[[str, str, bytes, bytes], bool]


def _httpx_post(url: str, stem: str, image_bytes: bytes, meta_bytes: bytes) -> bool:
    import httpx
    try:
        response = httpx.post(
            f"{url}/photos",
            files={
                "image": (f"{stem}.jpg", image_bytes, "image/jpeg"),
                "metadata": (f"{stem}.json", meta_bytes, "application/json"),
            },
            timeout=30,
        )
        return response.status_code == 200
    except Exception:
        return False


def run_upload(
    capture_dir: Path,
    uploaded_dir: Path,
    backend_url: str,
    post_fn: PostFn | None = None,
) -> None:
    if post_fn is None:
        post_fn = _httpx_post

    for jpg in sorted(capture_dir.glob("*.jpg")):
        meta = jpg.with_suffix(".json")
        if not meta.exists():
            continue

        image_bytes = jpg.read_bytes()
        meta_bytes = meta.read_bytes()

        success = post_fn(backend_url, jpg.stem, image_bytes, meta_bytes)
        if not success:
            continue

        uploaded_dir.mkdir(parents=True, exist_ok=True)

        dest_jpg = uploaded_dir / jpg.name
        dest_meta = uploaded_dir / meta.name

        if dest_jpg.exists() or dest_meta.exists():
            # destination already (partially) populated — leave capture pair alone
            continue

        tmp_jpg = dest_jpg.with_suffix(".jpg.tmp")
        tmp_meta = dest_meta.with_suffix(".json.tmp")
        try:
            tmp_jpg.write_bytes(image_bytes)
            tmp_meta.write_bytes(meta_bytes)
            tmp_jpg.rename(dest_jpg)
            tmp_meta.rename(dest_meta)
            jpg.unlink()
            meta.unlink()
        except Exception:
            tmp_jpg.unlink(missing_ok=True)
            tmp_meta.unlink(missing_ok=True)
            # TODO: scan for leftover *.tmp files in uploaded/ at startup and clean them up
            raise


if __name__ == "__main__":
    import sys

    config = json.loads(Path("config.json").read_text())
    capture_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("capture")
    uploaded_dir = capture_dir.parent / "uploaded"
    run_upload(capture_dir, uploaded_dir, config["backend_url"])
