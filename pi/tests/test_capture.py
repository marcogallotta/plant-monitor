import json
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from capture import run_capture
from camera import FakeCamera, PiCamera

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


# --- PiCamera resource cleanup ---

def _pi_mocks(capture_side_effect=None):
    mock_picamera2 = MagicMock()
    mock_cam = MagicMock()
    if capture_side_effect:
        mock_cam.capture_array.side_effect = capture_side_effect
    mock_picamera2.Picamera2.return_value = mock_cam

    mock_pil = MagicMock()
    mock_image = MagicMock()
    mock_pil.Image = mock_image

    modules = {"picamera2": mock_picamera2, "PIL": mock_pil, "PIL.Image": mock_image}
    return modules, mock_cam


def test_picamera_stops_and_closes_on_capture_array_error():
    modules, mock_cam = _pi_mocks(capture_side_effect=RuntimeError("hw failure"))
    with patch.dict(sys.modules, modules):
        with pytest.raises(RuntimeError):
            PiCamera().capture()
    mock_cam.stop.assert_called_once()
    mock_cam.close.assert_called_once()


def test_picamera_stops_and_closes_on_success():
    modules, mock_cam = _pi_mocks()
    with patch.dict(sys.modules, modules):
        result = PiCamera().capture()
    mock_cam.stop.assert_called_once()
    mock_cam.close.assert_called_once()
    assert result is not None
