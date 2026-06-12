import json
from pathlib import Path
from typing import Callable


PostFn = Callable[[str, str, bytes, bytes], bool]


def _httpx_post(
    url: str, stem: str, image_bytes: bytes, meta_bytes: bytes, token: str | None = None
) -> bool:
    import sys
    import httpx
    try:
        response = httpx.post(
            f"{url}/photos",
            files={
                "image": (f"{stem}.jpg", image_bytes, "image/jpeg"),
                "metadata": (f"{stem}.json", meta_bytes, "application/json"),
            },
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=30,
        )
    except Exception as e:
        # Transient: network down, DNS, timeout. Retried next cycle.
        print(f"upload {stem}: request failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False
    if response.status_code != 200:
        # 4xx (e.g. 401 bad ingest token, 422 bad payload) won't self-heal on
        # retry — surface the status and body so the journal shows the cause.
        print(
            f"upload {stem}: HTTP {response.status_code}: {response.text[:200]}",
            file=sys.stderr,
        )
        return False
    return True


def run_upload(
    capture_dir: Path,
    uploaded_dir: Path,
    backend_url: str,
    post_fn: PostFn | None = None,
) -> int:
    """Upload all pending capture pairs. Returns the number that failed."""
    if post_fn is None:
        post_fn = _httpx_post

    failures = 0
    for jpg in sorted(capture_dir.glob("*.jpg")):
        meta = jpg.with_suffix(".json")
        if not meta.exists():
            continue

        uploaded_dir.mkdir(parents=True, exist_ok=True)
        dest_jpg = uploaded_dir / jpg.name
        dest_meta = uploaded_dir / meta.name

        if dest_jpg.exists() and dest_meta.exists():
            # Archive already complete — source is redundant, remove it.
            jpg.unlink()
            meta.unlink()
            continue

        if dest_jpg.exists() or dest_meta.exists():
            # Partial archive state — leave capture pair alone.
            continue

        image_bytes = jpg.read_bytes()
        meta_bytes = meta.read_bytes()

        success = post_fn(backend_url, jpg.stem, image_bytes, meta_bytes)
        if not success:
            failures += 1
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
            raise

    return failures


def main(argv: list[str] | None = None) -> int:
    import sys

    if argv is None:
        argv = sys.argv[1:]

    config = json.loads(Path("config.json").read_text())
    token = config.get("api_token")
    if not token:
        print("upload: config.json missing required api_token", file=sys.stderr)
        return 1

    capture_dir = Path(argv[0]) if argv else Path("capture")
    uploaded_dir = capture_dir.parent / "uploaded"
    post_fn = lambda u, s, i, m: _httpx_post(u, s, i, m, token=token)
    failures = run_upload(capture_dir, uploaded_dir, config["backend_url"], post_fn=post_fn)
    if failures:
        # Non-zero exit so systemd marks plant-upload.service failed and the
        # failure is visible in `systemctl status` / `journalctl`.
        return 1
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
