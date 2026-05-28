import json
import pytest
from pathlib import Path

from upload import run_upload

STEM = "2026-05-26T103000Z"
IMAGE_BYTES = b"FAKEJPEG"
META = {"captured_at": "2026-05-26T10:30:00Z", "filename": f"{STEM}.jpg"}


def _write_pair(directory: Path, stem: str = STEM, image_bytes: bytes = IMAGE_BYTES):
    (directory / f"{stem}.jpg").write_bytes(image_bytes)
    (directory / f"{stem}.json").write_text(json.dumps(META))


def _ok_post(url, stem, image_bytes, meta_bytes):
    return True


def _fail_post(url, stem, image_bytes, meta_bytes):
    return False


@pytest.fixture()
def dirs(tmp_path):
    capture = tmp_path / "capture"
    uploaded = tmp_path / "uploaded"
    capture.mkdir()
    return capture, uploaded


# --- successful upload ---

def test_success_moves_jpg_to_uploaded(dirs):
    capture, uploaded = dirs
    _write_pair(capture)
    run_upload(capture, uploaded, "http://backend", post_fn=_ok_post)
    assert (uploaded / f"{STEM}.jpg").exists()


def test_success_moves_json_to_uploaded(dirs):
    capture, uploaded = dirs
    _write_pair(capture)
    run_upload(capture, uploaded, "http://backend", post_fn=_ok_post)
    assert (uploaded / f"{STEM}.json").exists()


def test_success_removes_from_capture(dirs):
    capture, uploaded = dirs
    _write_pair(capture)
    run_upload(capture, uploaded, "http://backend", post_fn=_ok_post)
    assert not (capture / f"{STEM}.jpg").exists()
    assert not (capture / f"{STEM}.json").exists()


def test_uploaded_dir_created_if_missing(dirs):
    capture, uploaded = dirs
    _write_pair(capture)
    run_upload(capture, uploaded, "http://backend", post_fn=_ok_post)
    assert uploaded.exists()


# --- failed upload ---

def test_failure_leaves_jpg_in_capture(dirs):
    capture, uploaded = dirs
    _write_pair(capture)
    run_upload(capture, uploaded, "http://backend", post_fn=_fail_post)
    assert (capture / f"{STEM}.jpg").exists()


def test_failure_leaves_json_in_capture(dirs):
    capture, uploaded = dirs
    _write_pair(capture)
    run_upload(capture, uploaded, "http://backend", post_fn=_fail_post)
    assert (capture / f"{STEM}.json").exists()


def test_failure_does_not_create_uploaded(dirs):
    capture, uploaded = dirs
    _write_pair(capture)
    run_upload(capture, uploaded, "http://backend", post_fn=_fail_post)
    assert not (uploaded / f"{STEM}.jpg").exists()


# --- multiple files ---

def test_all_files_attempted(dirs):
    capture, uploaded = dirs
    stems = ["2026-05-26T103000Z", "2026-05-26T110000Z", "2026-05-26T113000Z"]
    for stem in stems:
        _write_pair(capture, stem=stem)
    run_upload(capture, uploaded, "http://backend", post_fn=_ok_post)
    for stem in stems:
        assert (uploaded / f"{stem}.jpg").exists()


def test_failure_of_one_does_not_block_others(dirs):
    capture, uploaded = dirs
    _write_pair(capture, stem="2026-05-26T103000Z")
    _write_pair(capture, stem="2026-05-26T110000Z")

    calls = []
    def post_fn(url, stem, image_bytes, meta_bytes):
        calls.append(stem)
        return stem != "2026-05-26T103000Z"

    run_upload(capture, uploaded, "http://backend", post_fn=post_fn)
    assert calls == ["2026-05-26T103000Z", "2026-05-26T110000Z"]
    assert (capture / "2026-05-26T103000Z.jpg").exists()
    assert (uploaded / "2026-05-26T110000Z.jpg").exists()


# --- incomplete pairs ---

def test_jpg_without_json_is_skipped(dirs):
    capture, uploaded = dirs
    (capture / f"{STEM}.jpg").write_bytes(IMAGE_BYTES)
    run_upload(capture, uploaded, "http://backend", post_fn=_ok_post)
    assert (capture / f"{STEM}.jpg").exists()
    assert not (uploaded / f"{STEM}.jpg").exists()


def test_json_without_jpg_is_skipped(dirs):
    capture, uploaded = dirs
    (capture / f"{STEM}.json").write_text(json.dumps(META))
    called = []
    run_upload(capture, uploaded, "http://backend", post_fn=lambda *a: called.append(a) or True)
    assert called == []
    assert (capture / f"{STEM}.json").exists()


# --- destination already exists ---

def test_both_destinations_exist_cleans_up_source(dirs):
    # Archive is complete — source is redundant and should be removed to stop retry loop.
    capture, uploaded = dirs
    uploaded.mkdir()
    _write_pair(capture)
    _write_pair(uploaded)
    run_upload(capture, uploaded, "http://backend", post_fn=_ok_post)
    assert not (capture / f"{STEM}.jpg").exists()
    assert not (capture / f"{STEM}.json").exists()


def test_both_destinations_exist_skips_post(dirs):
    capture, uploaded = dirs
    uploaded.mkdir()
    _write_pair(capture)
    _write_pair(uploaded)
    calls = []
    run_upload(capture, uploaded, "http://backend", post_fn=lambda *a: calls.append(a) or True)
    assert calls == []


def test_partial_destination_exists_skips_move(dirs):
    # jpg already in uploaded but json is not — leave capture pair untouched
    capture, uploaded = dirs
    uploaded.mkdir()
    _write_pair(capture)
    (uploaded / f"{STEM}.jpg").write_bytes(IMAGE_BYTES)
    run_upload(capture, uploaded, "http://backend", post_fn=_ok_post)
    assert (capture / f"{STEM}.jpg").exists()
    assert (capture / f"{STEM}.json").exists()


# --- atomic move ---

def test_no_tmp_files_remain_after_success(dirs):
    capture, uploaded = dirs
    _write_pair(capture)
    run_upload(capture, uploaded, "http://backend", post_fn=_ok_post)
    assert list(uploaded.glob("*.tmp")) == []


# --- post_fn receives correct data ---

def test_post_fn_receives_backend_url(dirs):
    capture, uploaded = dirs
    _write_pair(capture)
    received = {}
    def post_fn(url, stem, image_bytes, meta_bytes):
        received["url"] = url
        return True
    run_upload(capture, uploaded, "http://mybackend:8000", post_fn=post_fn)
    assert received["url"] == "http://mybackend:8000"


def test_post_fn_receives_correct_bytes(dirs):
    capture, uploaded = dirs
    _write_pair(capture, image_bytes=b"REALIMGDATA")
    received = {}
    def post_fn(url, stem, image_bytes, meta_bytes):
        received["image"] = image_bytes
        received["meta"] = json.loads(meta_bytes)
        return True
    run_upload(capture, uploaded, "http://backend", post_fn=post_fn)
    assert received["image"] == b"REALIMGDATA"
    assert received["meta"]["filename"] == f"{STEM}.jpg"
