"""Tests for Dead Letter Queue (DLQ) behaviour.

Covers three layers:
  1. dlq_producer  – publish_to_dlq() calls the Kafka producer with correct headers
  2. kafka_consumer – poll_message() routes corrupt payloads to the DLQ
  3. main          – enrichment / S3 failures are forwarded to the DLQ and offset committed
"""
from unittest.mock import MagicMock, patch, call
import io

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from shared.parquet_io import write_parquet_bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parquet_bytes() -> bytes:
    """Build a minimal valid Parquet payload (same schema as producer output)."""
    schema = pa.schema([
        ("Index", pa.int32()),
        ("Position_Title", pa.string()),
        ("Position_URL", pa.string()),
    ])
    table = pa.table(
        {
            "Index": pa.array([1], type=pa.int32()),
            "Position_Title": pa.array(["Backend Engineer"]),
            "Position_URL": pa.array(["https://wsc-sports.com/Careers/1"]),
        },
        schema=schema,
    )
    return write_parquet_bytes(table)


# ---------------------------------------------------------------------------
# 1. dlq_producer
# ---------------------------------------------------------------------------

class TestPublishToDlq:
    def setup_method(self):
        # Reset the module-level singleton so tests are isolated.
        import src.dlq_producer as mod
        mod._producer = None

    @patch("src.dlq_producer.Producer")
    def test_produces_to_dlq_topic(self, MockProducer):
        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer

        from src.dlq_producer import publish_to_dlq
        publish_to_dlq(b"raw", "enrichment error: boom", "wsc-positions")

        mock_producer.produce.assert_called_once()
        kwargs = mock_producer.produce.call_args[1]
        assert kwargs["topic"] == "wsc-positions-dlq"
        assert kwargs["value"] == b"raw"

    @patch("src.dlq_producer.Producer")
    def test_headers_contain_error_reason(self, MockProducer):
        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer

        from src.dlq_producer import publish_to_dlq
        publish_to_dlq(b"raw", "s3 upload error: timeout", "wsc-positions")

        headers = dict(mock_producer.produce.call_args[1]["headers"])
        assert headers["error-reason"] == b"s3 upload error: timeout"
        assert headers["original-topic"] == b"wsc-positions"
        assert "failed-at" in headers

    @patch("src.dlq_producer.Producer")
    def test_flush_is_called(self, MockProducer):
        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer

        from src.dlq_producer import publish_to_dlq
        publish_to_dlq(b"raw", "any error", "wsc-positions")

        mock_producer.flush.assert_called_once()

    @patch("src.dlq_producer.Producer")
    def test_singleton_producer_reused(self, MockProducer):
        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer

        from src.dlq_producer import publish_to_dlq
        publish_to_dlq(b"a", "err1", "topic")
        publish_to_dlq(b"b", "err2", "topic")

        # Producer() constructor called only once despite two publishes
        assert MockProducer.call_count == 1
        assert mock_producer.produce.call_count == 2


# ---------------------------------------------------------------------------
# 2. kafka_consumer – deserialization failure path
# ---------------------------------------------------------------------------

class TestPollMessageDlqOnDeserError:
    def _make_kafka_message(self, value: bytes, topic: str = "wsc-positions"):
        msg = MagicMock()
        msg.error.return_value = None
        msg.value.return_value = value
        msg.topic.return_value = topic
        msg.partition.return_value = 0
        msg.offset.return_value = 0
        msg.headers.return_value = []
        return msg

    @patch("src.kafka_consumer.commit_offset")
    @patch("src.kafka_consumer._send_to_dlq")
    @patch("src.kafka_consumer.read_parquet_bytes", side_effect=Exception("corrupt payload"))
    def test_corrupt_message_sent_to_dlq(self, _mock_read, mock_dlq, mock_commit):
        from src.kafka_consumer import poll_message

        consumer = MagicMock()
        consumer.poll.return_value = self._make_kafka_message(b"not-parquet")

        result = poll_message(consumer)

        assert result is None
        mock_dlq.assert_called_once()
        reason_arg = mock_dlq.call_args[0][1]
        assert "deserialization error" in reason_arg

    @patch("src.kafka_consumer.commit_offset")
    @patch("src.kafka_consumer._send_to_dlq")
    @patch("src.kafka_consumer.read_parquet_bytes", side_effect=Exception("corrupt"))
    def test_offset_committed_after_dlq_on_deser_error(self, _mock_read, mock_dlq, mock_commit):
        from src.kafka_consumer import poll_message

        consumer = MagicMock()
        consumer.poll.return_value = self._make_kafka_message(b"bad")

        poll_message(consumer)

        mock_commit.assert_called_once_with(consumer)

    @patch("src.kafka_consumer.commit_offset")
    @patch("src.kafka_consumer._send_to_dlq")
    def test_valid_message_not_sent_to_dlq(self, mock_dlq, _mock_commit):
        from src.kafka_consumer import poll_message

        consumer = MagicMock()
        consumer.poll.return_value = self._make_kafka_message(_make_parquet_bytes())

        result = poll_message(consumer)

        assert result is not None
        df, raw = result
        assert isinstance(df, pd.DataFrame)
        mock_dlq.assert_not_called()


# ---------------------------------------------------------------------------
# 3. main – enrichment and S3 failure paths
# ---------------------------------------------------------------------------

class TestMainDlqPaths:
    """Verify that main.run() routes failures to the DLQ and commits offsets."""

    def _make_poll_result(self):
        raw = _make_parquet_bytes()
        df = pd.read_parquet(io.BytesIO(raw))
        return df, raw

    @patch("src.main.commit_offset")
    @patch("src.main.publish_to_dlq")
    @patch("src.main.upload_to_s3")
    @patch("src.main.enrich_positions", side_effect=RuntimeError("enrichment boom"))
    @patch("src.main.poll_message")
    @patch("src.main.create_consumer")
    def test_enrichment_failure_routes_to_dlq(
        self, mock_create, mock_poll, _mock_enrich, mock_s3, mock_dlq, mock_commit
    ):
        mock_poll.side_effect = [self._make_poll_result(), KeyboardInterrupt]

        from src.main import run
        with pytest.raises((KeyboardInterrupt, SystemExit)):
            run()

        mock_dlq.assert_called_once()
        reason = mock_dlq.call_args[0][1]
        assert "enrichment error" in reason
        mock_commit.assert_called()
        mock_s3.assert_not_called()

    @patch("src.main.commit_offset")
    @patch("src.main.publish_to_dlq")
    @patch("src.main.upload_to_s3", side_effect=Exception("s3 down"))
    @patch("src.main.enrich_positions")
    @patch("src.main.poll_message")
    @patch("src.main.create_consumer")
    def test_s3_failure_routes_to_dlq(
        self, mock_create, mock_poll, mock_enrich, _mock_s3, mock_dlq, mock_commit
    ):
        from src.models import EnrichedPosition
        mock_enrich.return_value = [
            EnrichedPosition(
                index=1,
                title="Backend Engineer",
                url="https://wsc-sports.com/Careers/1",
                category="Engineering",
                seniority_level="Senior",
                years_of_experience=5,
                skills_count=8,
                complexity_score=72,
            )
        ]
        mock_poll.side_effect = [self._make_poll_result(), KeyboardInterrupt]

        from src.main import run
        with pytest.raises((KeyboardInterrupt, SystemExit)):
            run()

        mock_dlq.assert_called_once()
        reason = mock_dlq.call_args[0][1]
        assert "s3 upload error" in reason
        mock_commit.assert_called()

    @patch("src.main.commit_offset")
    @patch("src.main.publish_to_dlq")
    @patch("src.main.upload_to_s3")
    @patch("src.main.enrich_positions")
    @patch("src.main.poll_message")
    @patch("src.main.create_consumer")
    def test_successful_processing_does_not_use_dlq(
        self, mock_create, mock_poll, mock_enrich, mock_s3, mock_dlq, mock_commit
    ):
        from src.models import EnrichedPosition
        mock_enrich.return_value = [
            EnrichedPosition(
                index=1,
                title="Backend Engineer",
                url="https://wsc-sports.com/Careers/1",
                category="Engineering",
                seniority_level="Senior",
                years_of_experience=5,
                skills_count=8,
                complexity_score=72,
            )
        ]
        mock_s3.return_value = "positions/year=2026/month=03/day=20/positions_123.parquet"
        mock_poll.side_effect = [self._make_poll_result(), KeyboardInterrupt]

        from src.main import run
        with pytest.raises((KeyboardInterrupt, SystemExit)):
            run()

        mock_dlq.assert_not_called()
        mock_commit.assert_called()
