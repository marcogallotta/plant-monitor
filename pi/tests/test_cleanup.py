import os
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from cleanup import run_cleanup

NOW = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
AGE_8_DAYS = NOW - timedelta(days=8)
AGE_7_DAYS = NOW - timedelta(days=7)
AGE_6_DAYS = NOW - timedelta(days=6)


def _make_file(path: Path, age: datetime) -> Path:
    path.write_bytes(b"data")
    mtime = age.timestamp()
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture()
def uploaded(tmp_path):
    d = tmp_path / "uploaded"
    d.mkdir()
    return d


# --- files older than 7 days are removed ---

def test_removes_jpg_older_than_7_days(uploaded):
    f = _make_file(uploaded / "2026-05-18T120000Z.jpg", AGE_8_DAYS)
    run_cleanup(uploaded, now=NOW)
    assert not f.exists()


def test_removes_json_older_than_7_days(uploaded):
    f = _make_file(uploaded / "2026-05-18T120000Z.json", AGE_8_DAYS)
    run_cleanup(uploaded, now=NOW)
    assert not f.exists()


def test_removes_both_files_of_old_pair(uploaded):
    jpg = _make_file(uploaded / "2026-05-18T120000Z.jpg", AGE_8_DAYS)
    meta = _make_file(uploaded / "2026-05-18T120000Z.json", AGE_8_DAYS)
    run_cleanup(uploaded, now=NOW)
    assert not jpg.exists()
    assert not meta.exists()


# --- files at or under 7 days are kept ---

def test_keeps_file_exactly_7_days_old(uploaded):
    f = _make_file(uploaded / "2026-05-19T120000Z.jpg", AGE_7_DAYS)
    run_cleanup(uploaded, now=NOW)
    assert f.exists()


def test_keeps_file_6_days_old(uploaded):
    f = _make_file(uploaded / "2026-05-20T120000Z.jpg", AGE_6_DAYS)
    run_cleanup(uploaded, now=NOW)
    assert f.exists()


# --- mix of old and recent ---

def test_only_removes_old_files(uploaded):
    old = _make_file(uploaded / "2026-05-18T120000Z.jpg", AGE_8_DAYS)
    recent = _make_file(uploaded / "2026-05-20T120000Z.jpg", AGE_6_DAYS)
    run_cleanup(uploaded, now=NOW)
    assert not old.exists()
    assert recent.exists()


# --- edge cases ---

def test_missing_uploaded_dir_is_noop(tmp_path):
    run_cleanup(tmp_path / "uploaded", now=NOW)


def test_empty_uploaded_dir_is_noop(uploaded):
    run_cleanup(uploaded, now=NOW)


def test_does_not_touch_capture_dir(tmp_path):
    uploaded = tmp_path / "uploaded"
    uploaded.mkdir()
    capture = tmp_path / "capture"
    capture.mkdir()
    old_in_capture = _make_file(capture / "2026-05-18T120000Z.jpg", AGE_8_DAYS)
    run_cleanup(uploaded, now=NOW)
    assert old_in_capture.exists()
