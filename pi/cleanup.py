from datetime import datetime, timezone, timedelta
from pathlib import Path

MAX_AGE_DAYS = 7
# TODO: monitor available disk space and alert or force early cleanup if storage runs low


def run_cleanup(uploaded_dir: Path, now: datetime | None = None) -> None:
    if not uploaded_dir.exists():
        return

    if now is None:
        now = datetime.now(tz=timezone.utc)

    cutoff = now - timedelta(days=MAX_AGE_DAYS)

    for f in uploaded_dir.iterdir():
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            f.unlink()


if __name__ == "__main__":
    import sys

    uploaded_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("uploaded")
    run_cleanup(uploaded_dir)
