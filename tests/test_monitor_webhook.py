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


def test_monitor_results_require_active_lease_before_persisting():
    source = inspect.getsource(monitor_store.run_due_monitors)
    assert "AND lease_token = %s" in source
    assert "AND locked_until > CURRENT_TIMESTAMP" in source
    assert "FOR UPDATE" in source
    lease_check = source.index("lease_owned =")
    history_insert = source.index("INSERT INTO price_history")
    assert lease_check < history_insert



def test_webhook_delivery_state_updates_require_current_lease():
    source = inspect.getsource(monitor_store._deliver_pending_webhooks)
    delivered = source[source.index("SET status='delivered'") : source.index("delivered += 1")]
    failed = source[source.index("SET attempts=%s") : source.index("conn.commit()", source.index("SET attempts=%s"))]
    assert "WHERE event_id=%s AND lease_token=%s" in delivered
    assert "WHERE event_id=%s AND lease_token=%s" in failed


def test_webhook_claim_uses_skip_locked_and_expiring_lease():
    source = inspect.getsource(monitor_store._deliver_pending_webhooks)
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "d.locked_until IS NULL OR d.locked_until <= %s" in source
    assert "locked_until = %s, lease_token = %s" in source
