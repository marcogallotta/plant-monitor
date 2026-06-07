import json
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from capture import run_capture, _agg_burst
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


# --- exposure/gain/AWB metadata logging ---

class _MetaCamera(FakeCamera):
    """A camera that exposes the auto algorithms' chosen settings (instance-level
    so instances never share a mutable dict)."""
    def __init__(self):
        super().__init__()
        self.last_metadata = {"exposure_us": 5000, "analogue_gain": 1.5,
                              "colour_gains": [1.8, 1.6], "lux": 12000}


def test_metadata_omits_camera_block_when_unavailable(output_dir):
    # default FakeCamera has empty last_metadata -> no "camera" key
    _capture(output_dir)
    meta = json.loads((output_dir / f"{EXPECTED_STEM}.json").read_text())
    assert "camera" not in meta
    assert "burst_camera" not in meta


def test_metadata_includes_camera_block_when_present(output_dir):
    run_capture(camera=_MetaCamera(), output_dir=output_dir, now=FIXED_TIME)
    meta = json.loads((output_dir / f"{EXPECTED_STEM}.json").read_text())
    assert meta["camera"] == _MetaCamera().last_metadata


def test_agg_burst_means_and_count():
    # _agg_burst is pure (no numpy/PIL), unlike the collapse path it rides with.
    agg = _agg_burst([
        {"exposure_us": 4000, "analogue_gain": 1.0, "digital_gain": 1.0, "lux": 100},
        {"exposure_us": 6000, "analogue_gain": 2.0, "digital_gain": 1.0, "lux": 300},
        {},  # a frame with no metadata is ignored
    ])
    assert agg["frame_count_with_metadata"] == 2
    assert agg["exposure_us_mean"] == 5000
    assert agg["analogue_gain_mean"] == 1.5
    assert agg["digital_gain_mean"] == 1.0
    assert agg["lux_mean"] == 200


def test_agg_burst_none_when_no_metadata():
    assert _agg_burst([]) is None
    assert _agg_burst([{}, {}]) is None


def test_burst_camera_block_written(output_dir, monkeypatch):
    # Stub the collapse (it needs numpy/PIL, absent in the pi test image) so we
    # exercise only the run_capture wiring of the burst aggregate.
    import capture
    cam = _MetaCamera()  # provides the single `camera` block
    monkeypatch.setattr(
        capture, "_capture_plate",
        lambda camera, n: (b"PLATE", {"frame_count_with_metadata": n,
                                      "exposure_us_mean": 5000}))
    run_capture(camera=cam, output_dir=output_dir, now=FIXED_TIME, frames=10)
    meta = json.loads((output_dir / f"{EXPECTED_STEM}.json").read_text())
    assert meta["burst_camera"] == {"frame_count_with_metadata": 10, "exposure_us_mean": 5000}
    assert meta["camera"] == _MetaCamera().last_metadata  # last-frame block still present


def test_picamera_records_exposure_metadata():
    modules, mock_cam = _pi_mocks()
    mock_cam.capture_metadata.return_value = {
        "ExposureTime": 5000, "AnalogueGain": 1.5, "DigitalGain": 1.02,
        "ColourGains": [1.8, 1.6], "Lux": 12000.0,
    }
    with patch.dict(sys.modules, modules):
        cam = PiCamera()
        cam.capture()
    assert cam.last_metadata["exposure_us"] == 5000
    assert cam.last_metadata["analogue_gain"] == 1.5
    assert cam.last_metadata["digital_gain"] == 1.02
    assert cam.last_metadata["colour_gains"] == [1.8, 1.6]
    assert cam.last_metadata["lux"] == 12000.0
