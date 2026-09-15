"""Regression tests for the three specific Gemini batch-mode bugs recorded in
TODO.md: `batches.create()` missing `model=`, job states compared against
plain lowercase strings instead of `JobState.JOB_STATE_*`, and results read
from a nonexistent `job.output_uri` instead of `job.dest.file_name`. Uses
mocks throughout - there's no GEMINI_API_KEY configured for this project and
no reason to spend real quota just to exercise error paths."""
import sys
import types as py_types
from unittest.mock import MagicMock

import pytest

from src.vision.batch_manager import BatchManager


def _install_fake_google_genai(monkeypatch, client):
    """`from google import genai` inside BatchManager methods needs a fake
    `google.genai` module in sys.modules whose `Client()` returns our mock."""
    fake_genai = py_types.ModuleType("google.genai")
    fake_genai.Client = MagicMock(return_value=client)
    fake_google = py_types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)


def test_submit_job_passes_required_model_param(monkeypatch, tmp_path):
    """`batches.create()` requires `model=` - omitting it (the original bug)
    raises a TypeError before any request is sent."""
    jsonl_path = tmp_path / "job.jsonl"
    jsonl_path.write_text('{"request": {}}\n')

    client = MagicMock()
    client.files.upload.return_value = MagicMock(name="files/abc123")
    client.files.upload.return_value.name = "files/abc123"
    created_job = MagicMock()
    created_job.name = "batches/xyz789"
    client.batches.create.return_value = created_job
    _install_fake_google_genai(monkeypatch, client)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    bm = BatchManager("gemini")
    job_id = bm.submit_job(str(jsonl_path), model="gemini-2.0-flash-001")

    assert job_id == "batches/xyz789"
    _, kwargs = client.batches.create.call_args
    assert kwargs["model"] == "gemini-2.0-flash-001"
    assert kwargs["src"] == "files/abc123"


@pytest.mark.parametrize("state_name,expected", [
    ("JOB_STATE_QUEUED", "pending"),
    ("JOB_STATE_RUNNING", "running"),
    ("JOB_STATE_SUCCEEDED", "succeeded"),
    ("JOB_STATE_FAILED", "failed"),
    ("JOB_STATE_CANCELLED", "failed"),
])
def test_check_status_normalizes_gemini_job_state_enum(monkeypatch, state_name, expected):
    """job.state is a JobState enum member, not a string - comparing it
    directly against `"succeeded"` (the original bug) never matches."""
    fake_state = MagicMock()
    fake_state.name = state_name
    job = MagicMock()
    job.state = fake_state

    client = MagicMock()
    client.batches.get.return_value = job
    _install_fake_google_genai(monkeypatch, client)

    bm = BatchManager("gemini")
    assert bm.check_status("batches/xyz789") == expected


def test_download_results_uses_dest_file_name_not_output_uri(monkeypatch, tmp_path):
    """BatchJob has no `output_uri` field - results for a file-based
    (non-GCS) batch live at `job.dest.file_name`, fetched via the Files API."""
    job = MagicMock()
    job.dest.file_name = "files/results-abc"
    assert not hasattr(job, "output_uri") or isinstance(job.output_uri, MagicMock)

    client = MagicMock()
    client.batches.get.return_value = job
    _install_fake_google_genai(monkeypatch, client)

    bm = BatchManager("gemini")
    out_path = tmp_path / "results.jsonl"
    bm.download_results("batches/xyz789", str(out_path))

    client.files.download.assert_called_once_with(
        file="files/results-abc", destination=str(out_path)
    )


def test_download_results_raises_when_no_dest_yet(monkeypatch, tmp_path):
    job = MagicMock()
    job.dest = None

    client = MagicMock()
    client.batches.get.return_value = job
    _install_fake_google_genai(monkeypatch, client)

    bm = BatchManager("gemini")
    with pytest.raises(ValueError):
        bm.download_results("batches/xyz789", str(tmp_path / "out.jsonl"))
