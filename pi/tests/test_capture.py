import json
from datetime import datetime, timezone

import pytest

from capture import run_capture
from camera import FakeCamera

FIXED_TIME = datetime(2026, 5, 26, 10, 30, 0, tzinfo=timezone.utc)
EXPECTED_STEM = "2026-05-26T103000Z"


@pytest.fixture()
def output_dir(tmp_path):
    return tmp_path


def _capture(output_dir, time=FIXED_TIME):
    run_capture(camera=FakeCamera(), output_dir=output_dir, now=time)


def test_capture_writes_jpg(output_dir):
    _capture(output_dir)
    assert (output_dir / f"{EXPECTED_STEM}.jpg").exists()


def test_capture_writes_json(output_dir):
    _capture(output_dir)
    assert (output_dir / f"{EXPECTED_STEM}.json").exists()


def test_jpg_contains_image_bytes(output_dir):
    _capture(output_dir)
    assert len((output_dir / f"{EXPECTED_STEM}.jpg").read_bytes()) > 0


def test_metadata_has_captured_at(output_dir):
    _capture(output_dir)
    meta = json.loads((output_dir / f"{EXPECTED_STEM}.json").read_text())
    assert meta["captured_at"] == "2026-05-26T10:30:00Z"


def test_metadata_has_filename(output_dir):
    _capture(output_dir)
    meta = json.loads((output_dir / f"{EXPECTED_STEM}.json").read_text())
    assert meta["filename"] == f"{EXPECTED_STEM}.jpg"


def test_metadata_filename_matches_jpg(output_dir):
    _capture(output_dir)
    meta = json.loads((output_dir / f"{EXPECTED_STEM}.json").read_text())
    assert (output_dir / meta["filename"]).exists()


def test_stem_uses_utc(output_dir):
    # a time that would give a different stem in a non-UTC timezone
    t = datetime(2026, 5, 26, 23, 0, 0, tzinfo=timezone.utc)
    run_capture(camera=FakeCamera(), output_dir=output_dir, now=t)
    assert (output_dir / "2026-05-26T230000Z.jpg").exists()


def test_output_dir_created_if_missing(tmp_path):
    output_dir = tmp_path / "nested" / "capture"
    _capture(output_dir)
    assert (output_dir / f"{EXPECTED_STEM}.jpg").exists()
