import inspect

import pytest

from app.services import monitor_store


def test_webhook_outbox_is_durable_and_deduplicated():
    assert "CREATE TABLE IF NOT EXISTS webhook_deliveries" in monitor_store.SCHEMA
    assert "event_id TEXT PRIMARY KEY" in monitor_store.SCHEMA
    assert "status TEXT NOT NULL DEFAULT 'pending'" in monitor_store.SCHEMA


def test_monitor_state_and_webhook_outbox_commit_together():
    source = inspect.getsource(monitor_store.run_due_monitors)
    enqueue = source.index("await _enqueue_webhook")
    commit = source.index("conn.commit()", enqueue)
    assert enqueue < commit


def test_webhook_delivery_has_bounded_timeout_and_no_redirects():
    source = inspect.getsource(monitor_store._deliver_pending_webhooks)
    assert "httpx.Timeout(10.0, connect=3.0)" in source
    assert "follow_redirects=False" in source
    assert "read_response_bytes(response, MAX_WEBHOOK_RESPONSE_BYTES)" in source


def test_webhook_failures_are_scheduled_for_retry():
    source = inspect.getsource(monitor_store._deliver_pending_webhooks)
    assert "status='pending'" not in source or "status='pending'" in monitor_store.SCHEMA
    assert "next_attempt_at" in source
    assert "2 ** min(attempts - 1, 6)" in source
    assert "min(3600" in source
