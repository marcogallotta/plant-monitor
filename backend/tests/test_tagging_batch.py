"""Tests for the Batch-API tagging pipeline scripts.

Covers pure helper functions (no network, no Anthropic calls) and the DB
write path for ingest_tagging_batch via a minimal mock of the Anthropic
client.  The DB tests use the real test database (plantmonitoring_test),
mocking only the Anthropic SDK calls.
"""

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.models import Photo, PhotoAiSuggestion


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _photo(db_session, filename="abc123.jpg"):
    photo = Photo(
        filename=filename,
        captured_at=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        storage_path="/tmp/a.jpg",
        metadata_path="/tmp/a.json",
    )
    db_session.add(photo)
    db_session.commit()
    db_session.refresh(photo)
    return photo


def _make_jpeg_bytes(width=100, height=200) -> bytes:
    img = Image.new("RGB", (width, height), color=(34, 139, 34))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _fake_batch_result(photo_id: int, regions: list[dict]):
    text_block = SimpleNamespace(type="text", text=json.dumps(regions))
    message = SimpleNamespace(content=[text_block])
    result = SimpleNamespace(type="succeeded", message=message)
    return SimpleNamespace(custom_id=str(photo_id), result=result)


def _fake_batch(batch_id: str):
    return SimpleNamespace(
        id=batch_id,
        processing_status="ended",
        request_counts=SimpleNamespace(processing=0, succeeded=1, errored=0),
    )


def _write_manifest(run_dir: Path, run_id: str, batch_id: str, photo_ids: list[int], prior: str = "rich"):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "run_id": run_id,
        "batch_id": batch_id,
        "prior": prior,
        "model": "claude-sonnet-4-6",
        "photo_ids": photo_ids,
        "status": "submitted",
    }))


# ---------------------------------------------------------------------------
# submit_tagging_batch — _resize_and_encode
# ---------------------------------------------------------------------------

class TestResizeAndEncode:
    def test_returns_base64_string(self, tmp_path):
        from scripts.submit_tagging_batch import _resize_and_encode
        import base64

        p = tmp_path / "photo.jpg"
        p.write_bytes(_make_jpeg_bytes(200, 100))
        result = _resize_and_encode(p)
        assert result is not None
        img = Image.open(io.BytesIO(base64.b64decode(result)))
        assert img.format == "JPEG"

    def test_downsizes_long_edge_to_1024(self, tmp_path):
        from scripts.submit_tagging_batch import _resize_and_encode, MAX_LONG_EDGE
        import base64

        p = tmp_path / "big.jpg"
        p.write_bytes(_make_jpeg_bytes(2000, 800))
        result = _resize_and_encode(p)
        img = Image.open(io.BytesIO(base64.b64decode(result)))
        assert max(img.size) == MAX_LONG_EDGE

    def test_does_not_upscale_small_image(self, tmp_path):
        from scripts.submit_tagging_batch import _resize_and_encode
        import base64

        p = tmp_path / "small.jpg"
        p.write_bytes(_make_jpeg_bytes(400, 300))
        result = _resize_and_encode(p)
        img = Image.open(io.BytesIO(base64.b64decode(result)))
        assert img.size == (400, 300)

    def test_missing_file_returns_none(self, tmp_path):
        from scripts.submit_tagging_batch import _resize_and_encode

        assert _resize_and_encode(tmp_path / "nonexistent.jpg") is None

    def test_corrupt_file_returns_none(self, tmp_path):
        from scripts.submit_tagging_batch import _resize_and_encode

        p = tmp_path / "corrupt.jpg"
        p.write_bytes(b"not an image")
        assert _resize_and_encode(p) is None

    def test_rotation_90_transposes_dimensions(self, tmp_path):
        import base64
        from scripts.submit_tagging_batch import _resize_and_encode

        # 200×100 landscape; rotation=90 should produce a 100×200 portrait output.
        p = tmp_path / "landscape.jpg"
        p.write_bytes(_make_jpeg_bytes(200, 100))
        result = _resize_and_encode(p, rotation=90)
        assert result is not None
        img = Image.open(io.BytesIO(base64.b64decode(result)))
        w, h = img.size
        assert w < h, f"expected portrait after 90° rotation, got {w}×{h}"

    def test_rotation_0_leaves_dimensions_unchanged(self, tmp_path):
        import base64
        from scripts.submit_tagging_batch import _resize_and_encode

        p = tmp_path / "photo.jpg"
        p.write_bytes(_make_jpeg_bytes(200, 100))
        result = _resize_and_encode(p, rotation=0)
        img = Image.open(io.BytesIO(base64.b64decode(result)))
        assert img.size == (200, 100)


# ---------------------------------------------------------------------------
# submit_tagging_batch — system prompts
# ---------------------------------------------------------------------------

class TestSystemPrompts:
    def test_rich_prompt_contains_container_map(self):
        from scripts.submit_tagging_batch import SYSTEM_PROMPT_RICH

        assert "CONTAINER MAP" in SYSTEM_PROMPT_RICH
        assert "genovese basil" in SYSTEM_PROMPT_RICH
        assert "Moroccan mint" in SYSTEM_PROMPT_RICH

    def test_thin_prompt_omits_container_map(self):
        from scripts.submit_tagging_batch import SYSTEM_PROMPT_THIN

        assert "CONTAINER MAP" not in SYSTEM_PROMPT_THIN
        assert "KNOWN PLANTS" in SYSTEM_PROMPT_THIN
        assert "RULES" in SYSTEM_PROMPT_THIN

    def test_prompts_share_output_schema(self):
        from scripts.submit_tagging_batch import SYSTEM_PROMPT_RICH, SYSTEM_PROMPT_THIN

        for prompt in (SYSTEM_PROMPT_RICH, SYSTEM_PROMPT_THIN):
            assert '"plant"' in prompt
            assert '"options"' in prompt
            assert '"confidence"' in prompt
            assert '"region"' in prompt
            assert "No prose outside the array" in prompt

    def test_both_thai_basils_mentioned(self):
        from scripts.submit_tagging_batch import SYSTEM_PROMPT_RICH

        assert "Thai basil vendita" in SYSTEM_PROMPT_RICH

    def test_key_confusables_in_both_prompts(self):
        from scripts.submit_tagging_batch import SYSTEM_PROMPT_RICH, SYSTEM_PROMPT_THIN

        for prompt in (SYSTEM_PROMPT_RICH, SYSTEM_PROMPT_THIN):
            assert "peppermint" in prompt.lower()
            assert "SEEDLINGS" in prompt


# ---------------------------------------------------------------------------
# ingest_tagging_batch — _parse_model_output
# ---------------------------------------------------------------------------

class TestParseModelOutput:
    def test_valid_array(self):
        from scripts.ingest_tagging_batch import _parse_model_output

        data = [{"plant": "Dill", "options": [], "confidence": "high",
                 "photo_type": "overview", "labels": [], "region": None, "observation": "mature"}]
        assert _parse_model_output(json.dumps(data), photo_id=1) == data

    def test_array_with_preamble(self):
        from scripts.ingest_tagging_batch import _parse_model_output

        text = 'Here is my analysis:\n[{"plant": "Sorrel", "options": [], "confidence": "high", "photo_type": null, "labels": [], "region": null, "observation": "young"}]'
        result = _parse_model_output(text, photo_id=1)
        assert len(result) == 1
        assert result[0]["plant"] == "Sorrel"

    def test_invalid_json_returns_empty(self):
        from scripts.ingest_tagging_batch import _parse_model_output

        assert _parse_model_output("not json at all", photo_id=99) == []

    def test_empty_array(self):
        from scripts.ingest_tagging_batch import _parse_model_output

        assert _parse_model_output("[]", photo_id=1) == []

    def test_strips_whitespace(self):
        from scripts.ingest_tagging_batch import _parse_model_output

        assert _parse_model_output("  []  ", photo_id=1) == []


# ---------------------------------------------------------------------------
# ingest_tagging_batch — _region_to_coords
# ---------------------------------------------------------------------------

class TestRegionToCoords:
    def test_valid_region(self):
        from scripts.ingest_tagging_batch import _region_to_coords

        assert _region_to_coords([0.1, 0.2, 0.8, 0.9]) == (0.1, 0.2, 0.8, 0.9)

    def test_none_returns_all_none(self):
        from scripts.ingest_tagging_batch import _region_to_coords

        assert _region_to_coords(None) == (None, None, None, None)

    def test_wrong_length_returns_none(self):
        from scripts.ingest_tagging_batch import _region_to_coords

        assert _region_to_coords([0.1, 0.2]) == (None, None, None, None)

    def test_clamps_out_of_range(self):
        from scripts.ingest_tagging_batch import _region_to_coords

        x, y, x2, y2 = _region_to_coords([-0.5, 0.0, 1.5, 1.0])
        assert x == 0.0
        assert x2 == 1.0

    def test_non_numeric_returns_none(self):
        from scripts.ingest_tagging_batch import _region_to_coords

        assert _region_to_coords(["a", "b", "c", "d"]) == (None, None, None, None)


# ---------------------------------------------------------------------------
# agreement_gate — _is_flagged
# ---------------------------------------------------------------------------

class TestIsFlagged:
    def _row(self, **kwargs):
        row = SimpleNamespace(suggested_options=None, confidence="high", suggested_plant_name="Dill")
        for k, v in kwargs.items():
            setattr(row, k, v)
        return row

    def test_high_confidence_no_options_not_flagged(self):
        from scripts.agreement_gate import _is_flagged
        assert not _is_flagged(self._row())

    def test_has_options_is_flagged(self):
        from scripts.agreement_gate import _is_flagged
        assert _is_flagged(self._row(suggested_options=["Peppermint", "Moroccan mint"]))

    def test_low_confidence_is_flagged(self):
        from scripts.agreement_gate import _is_flagged
        assert _is_flagged(self._row(confidence="low"))

    def test_medium_confidence_is_flagged(self):
        from scripts.agreement_gate import _is_flagged
        assert _is_flagged(self._row(confidence="medium"))

    def test_seedlings_is_flagged(self):
        from scripts.agreement_gate import _is_flagged
        assert _is_flagged(self._row(suggested_plant_name="SEEDLINGS"))

    def test_empty_options_not_flagged(self):
        from scripts.agreement_gate import _is_flagged
        assert not _is_flagged(self._row(suggested_options=[]))


# ---------------------------------------------------------------------------
# agreement_gate — _plants_agree
# ---------------------------------------------------------------------------

class TestPlantsAgree:
    def test_same_plant_agrees(self):
        from scripts.agreement_gate import _plants_agree
        assert _plants_agree("Dill", [], "Dill", [])

    def test_different_plants_disagree(self):
        from scripts.agreement_gate import _plants_agree
        assert not _plants_agree("Dill", [], "Rosemary", [])

    def test_both_null_agrees(self):
        from scripts.agreement_gate import _plants_agree
        assert _plants_agree(None, [], None, [])

    def test_both_seedlings_agrees(self):
        from scripts.agreement_gate import _plants_agree
        assert _plants_agree("SEEDLINGS", [], "SEEDLINGS", [])

    def test_overlapping_options_disagrees(self):
        # Peppermint/Moroccan vs Moroccan/Spearmint share Moroccan, but neither model
        # committed to a single plant — still a human-choice case, not agreement.
        from scripts.agreement_gate import _plants_agree
        assert not _plants_agree(
            "Peppermint", ["Peppermint", "Moroccan mint"],
            "Moroccan mint", ["Moroccan mint", "Spearmint"],
        )

    def test_no_overlap_in_options_disagrees(self):
        from scripts.agreement_gate import _plants_agree
        assert not _plants_agree(
            "Peppermint", ["Peppermint"],
            "Moroccan mint", ["Moroccan mint"],
        )

    def test_plant_in_other_options_disagrees(self):
        # Opus still lists candidates (options non-empty) — not a confident match.
        from scripts.agreement_gate import _plants_agree
        assert not _plants_agree("Peppermint", [], "Moroccan mint", ["Moroccan mint", "Peppermint"])

    def test_same_plant_with_options_disagrees(self):
        # Both name the same plant but one carries options — still uncertain.
        from scripts.agreement_gate import _plants_agree
        assert not _plants_agree("Dill", [], "Dill", ["Dill", "Parsley"])

    def test_case_insensitive(self):
        from scripts.agreement_gate import _plants_agree
        assert _plants_agree("dill", [], "Dill", [])


# ---------------------------------------------------------------------------
# ingest_tagging_batch — end-to-end DB write via mocked Anthropic client
# ---------------------------------------------------------------------------

class TestIngestBatch:
    """Uses the real test DB; only the Anthropic network calls are mocked."""

    def test_ingest_inserts_suggestions(self, db_session, tmp_path):
        from scripts.ingest_tagging_batch import ingest_batch

        photo = _photo(db_session)
        run_id = "test_run_abc"
        batch_id = "msgbatch_fake_abc"
        _write_manifest(tmp_path / run_id, run_id, batch_id, [photo.id])

        regions = [
            {"plant": "Dill", "options": [], "confidence": "high",
             "photo_type": "overview", "labels": [], "region": None, "observation": "mature"},
            {"plant": "Parsley", "options": [], "confidence": "medium",
             "photo_type": "overview", "labels": [], "region": [0.5, 0.0, 1.0, 1.0], "observation": "young"},
        ]
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = _fake_batch(batch_id)
        mock_client.messages.batches.results.return_value = iter([_fake_batch_result(photo.id, regions)])

        with (
            patch("scripts.ingest_tagging_batch.RUNS_DIR", tmp_path),
            patch("anthropic.Anthropic", return_value=mock_client),
        ):
            ingest_batch(run_id=run_id, api_key="fake", poll=False, status_only=False)

        suggestions = db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).all()
        assert len(suggestions) == 2
        assert {s.suggested_plant_name for s in suggestions} == {"Dill", "Parsley"}

    def test_ingest_skips_duplicates(self, db_session, tmp_path):
        from scripts.ingest_tagging_batch import ingest_batch

        photo = _photo(db_session, filename="dedup123.jpg")
        run_id = "test_run_dedup"
        batch_id = "msgbatch_dedup"
        _write_manifest(tmp_path / run_id, run_id, batch_id, [photo.id])

        regions = [{"plant": "Sage", "options": [], "confidence": "high",
                    "photo_type": "closeup", "labels": [], "region": None, "observation": "mature"}]
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = _fake_batch(batch_id)
        mock_client.messages.batches.results.side_effect = [
            iter([_fake_batch_result(photo.id, regions)]),
            iter([_fake_batch_result(photo.id, regions)]),
        ]

        with (
            patch("scripts.ingest_tagging_batch.RUNS_DIR", tmp_path),
            patch("anthropic.Anthropic", return_value=mock_client),
        ):
            ingest_batch(run_id=run_id, api_key="fake", poll=False, status_only=False)
            ingest_batch(run_id=run_id, api_key="fake", poll=False, status_only=False)

        assert db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).count() == 1

    def test_ingest_different_x2y2_is_not_a_duplicate(self, db_session, tmp_path):
        # Two regions with the same top-left but different extents must both be inserted.
        from scripts.ingest_tagging_batch import ingest_batch

        photo = _photo(db_session, filename="bbox_dedup.jpg")
        run_id = "test_run_bbox"
        batch_id = "msgbatch_bbox"
        _write_manifest(tmp_path / run_id, run_id, batch_id, [photo.id])

        region_a = {"plant": "Dill", "options": [], "confidence": "high",
                    "photo_type": "overview", "labels": [], "region": [0.0, 0.0, 0.4, 0.5], "observation": ""}
        region_b = {"plant": "Dill", "options": [], "confidence": "high",
                    "photo_type": "overview", "labels": [], "region": [0.0, 0.0, 0.9, 0.9], "observation": ""}
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = _fake_batch(batch_id)
        mock_client.messages.batches.results.side_effect = [
            iter([_fake_batch_result(photo.id, [region_a])]),
            iter([_fake_batch_result(photo.id, [region_b])]),
        ]

        with (
            patch("scripts.ingest_tagging_batch.RUNS_DIR", tmp_path),
            patch("anthropic.Anthropic", return_value=mock_client),
        ):
            ingest_batch(run_id=run_id, api_key="fake", poll=False, status_only=False)
            ingest_batch(run_id=run_id, api_key="fake", poll=False, status_only=False)

        assert db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).count() == 2

    def test_ingest_stores_provenance_in_prompt_context(self, db_session, tmp_path):
        from scripts.ingest_tagging_batch import ingest_batch

        photo = _photo(db_session, filename="ctx456.jpg")
        run_id = "test_run_ctx"
        batch_id = "msgbatch_ctx"
        _write_manifest(tmp_path / run_id, run_id, batch_id, [photo.id], prior="thin")

        regions = [{"plant": "Rocket", "options": [], "confidence": "high",
                    "photo_type": "overview", "labels": [], "region": None, "observation": "dense"}]
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = _fake_batch(batch_id)
        mock_client.messages.batches.results.return_value = iter([_fake_batch_result(photo.id, regions)])

        with (
            patch("scripts.ingest_tagging_batch.RUNS_DIR", tmp_path),
            patch("anthropic.Anthropic", return_value=mock_client),
        ):
            ingest_batch(run_id=run_id, api_key="fake", poll=False, status_only=False)

        row = db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).first()
        assert row.prompt_context["run_id"] == run_id
        assert row.prompt_context["batch_id"] == batch_id
        assert row.prompt_context["prior"] == "thin"

    def test_ingest_handles_parse_error_gracefully(self, db_session, tmp_path):
        from scripts.ingest_tagging_batch import ingest_batch

        photo = _photo(db_session, filename="err789.jpg")
        run_id = "test_run_err"
        batch_id = "msgbatch_err"
        _write_manifest(tmp_path / run_id, run_id, batch_id, [photo.id])

        # Model returns prose instead of JSON
        text_block = SimpleNamespace(type="text", text="Sorry, I cannot classify this image.")
        bad_result = SimpleNamespace(
            custom_id=str(photo.id),
            result=SimpleNamespace(type="succeeded", message=SimpleNamespace(content=[text_block])),
        )
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = _fake_batch(batch_id)
        mock_client.messages.batches.results.return_value = iter([bad_result])

        with (
            patch("scripts.ingest_tagging_batch.RUNS_DIR", tmp_path),
            patch("anthropic.Anthropic", return_value=mock_client),
        ):
            ingest_batch(run_id=run_id, api_key="fake", poll=False, status_only=False)

        row = db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).first()
        assert row is not None
        assert "parse_error" in (row.suggested_labels or [])

    def test_ingest_normalises_invalid_confidence(self, db_session, tmp_path):
        from scripts.ingest_tagging_batch import ingest_batch

        photo = _photo(db_session, filename="conf999.jpg")
        run_id = "test_run_conf"
        batch_id = "msgbatch_conf"
        _write_manifest(tmp_path / run_id, run_id, batch_id, [photo.id])

        regions = [{"plant": "Mint", "options": [], "confidence": "very_high",
                    "photo_type": "overview", "labels": [], "region": None, "observation": ""}]
        mock_client = MagicMock()
        mock_client.messages.batches.retrieve.return_value = _fake_batch(batch_id)
        mock_client.messages.batches.results.return_value = iter([_fake_batch_result(photo.id, regions)])

        with (
            patch("scripts.ingest_tagging_batch.RUNS_DIR", tmp_path),
            patch("anthropic.Anthropic", return_value=mock_client),
        ):
            ingest_batch(run_id=run_id, api_key="fake", poll=False, status_only=False)

        row = db_session.query(PhotoAiSuggestion).filter_by(photo_id=photo.id).first()
        # Invalid confidence falls back to "low" rather than raising
        assert row.confidence == "low"
