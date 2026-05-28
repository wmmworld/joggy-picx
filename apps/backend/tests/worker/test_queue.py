"""Unit tests for RQ queue helpers."""
from unittest.mock import MagicMock, patch

import pytest

from joggy.worker.queue import enqueue_process_erasure


def test_enqueue_process_erasure_returns_job_id():
    """enqueue_process_erasure must enqueue to the correct task with correct timeouts."""
    mock_job = MagicMock()
    mock_job.id = "rq-job-test-abc123"

    with patch("joggy.worker.queue.get_queue") as mock_get_queue:
        mock_get_queue.return_value.enqueue.return_value = mock_job
        result = enqueue_process_erasure("erasure-uuid-001")

    assert result == "rq-job-test-abc123"
    mock_get_queue.return_value.enqueue.assert_called_once_with(
        "joggy.worker.tasks.process_erasure",
        "erasure-uuid-001",
        job_timeout=300,
        result_ttl=86400,
        failure_ttl=604800,
    )


def test_enqueue_process_erasure_passes_erasure_id_as_positional_arg():
    """erasure_id must be passed as second positional arg to enqueue()."""
    mock_job = MagicMock()
    mock_job.id = "any-job-id"

    with patch("joggy.worker.queue.get_queue") as mock_get_queue:
        mock_get_queue.return_value.enqueue.return_value = mock_job
        enqueue_process_erasure("some-erasure-id")
        call_args = mock_get_queue.return_value.enqueue.call_args

    # Second positional arg (index 1) is the erasure_id
    assert call_args[0][1] == "some-erasure-id"
