from app.services.billing import _apply_subscription


class FakeCursor:
    def __init__(self, rows):
        self.rows = iter(rows)

    def fetchone(self):
        return next(self.rows)


class FakeConn:
    def __init__(self, state=(None, None)):
        self.updates = 0
        self.last_params = None
        self.state = state
        self.state_sql = None

    def execute(self, sql, params=()):
        if "SELECT api_key_hash" in sql:
            return FakeCursor([("account-hash",)])
        if "SELECT last_stripe_event_created" in sql:
            self.state_sql = sql
            return FakeCursor([self.state])
        self.updates += 1
        self.last_params = params
        return FakeCursor([])


def _subscription(status="active", event_id="evt_123"):
    return {
        "id": "sub_123",
        "customer": "cus_123",
        "status": status,
        "items": {"data": [{"price": {"id": "price_pro"}}]},
        "_ec_pulse_event_id": event_id,
    }


def test_active_subscription_applies_plan(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn()
    assert _apply_subscription(conn, _subscription("active"), 100) is True
    assert conn.updates == 1
    assert conn.last_params[-3] == "evt_123"


def test_past_due_subscription_keeps_plan_during_retry(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn()
    assert _apply_subscription(conn, _subscription("past_due"), 100) is True
    assert conn.updates == 1
    assert conn.last_params[0] == "pro"


def test_canceled_subscription_downgrades_to_free(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn()
    assert _apply_subscription(conn, _subscription("canceled"), 100) is True
    assert conn.updates == 1
    assert conn.last_params[0] == "free"


def test_event_id_does_not_act_as_fake_ordering(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn()
    subscription = _subscription("active")
    subscription["_ec_pulse_event_id"] = "evt_001"
    assert _apply_subscription(conn, subscription, 200) is True
    subscription["_ec_pulse_event_id"] = "evt_999"
    assert _apply_subscription(conn, subscription, 100) is True
    assert conn.updates == 2


def test_older_event_created_is_ignored(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn((200, "evt_002"))
    assert _apply_subscription(conn, _subscription("active"), 100) is False
    assert conn.updates == 0


def test_same_timestamp_does_not_compare_ids(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn((100, "evt_002"))
    assert _apply_subscription(conn, _subscription("active", "evt_001"), 100) is True
    assert conn.updates == 1


def test_subscription_state_row_is_locked_during_update(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn()
    assert _apply_subscription(conn, _subscription("active"), 100) is True
    assert "FOR UPDATE" in conn.state_sql


def test_subscription_state_row_is_locked_during_cancellation(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("cus_123", "sub_123", "active", None, False)

    class Conn:
        def __init__(self):
            self.sql = None
        def execute(self, sql, params=()):
            self.sql = sql
            return Cursor()
        def rollback(self):
            pass
        def commit(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    class FakeSubscription:
        @staticmethod
        def modify(subscription_id, **kwargs):
            assert subscription_id == "sub_123"
            assert kwargs["cancel_at_period_end"] is True
            assert kwargs["idempotency_key"]
            return {"id": "sub_123", "status": "active", "cancel_at_period_end": True}

    class FakeStripe:
        Subscription = FakeSubscription

    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr("app.services.monitor_store._account_hash", lambda key: "account-hash")

    result = billing.cancel_subscription("secret")
    assert result["cancel_at_period_end"] is True


def test_canceled_subscription_cannot_be_canceled_again(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("cus_123", "sub_123", "canceled", None, False)

    class Conn:
        def execute(self, sql, params=()):
            return Cursor()
        def commit(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_account_hash", lambda key: "account-hash")
    try:
        billing.cancel_subscription("secret")
    except ValueError as exc:
        assert "No active Stripe subscription" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_checkout_rejects_existing_active_subscription(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("account-hash", "cus_123", "sub_123", "active", None, None)

    class Conn:
        def execute(self, sql, params=()):
            assert "FOR UPDATE" in sql
            return Cursor()
        def commit(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr("app.services.monitor_store._account_hash", lambda key: "account-hash")

    try:
        billing.create_checkout("secret", "pro")
    except ValueError as exc:
        assert "active Stripe subscription" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_checkout_sets_pending_before_stripe_call(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("account-hash", None, None, None, None, None)

    class Conn:
        def __init__(self):
            self.committed = False
            self.closed = False
            self.sql = None
        def execute(self, sql, params=()):
            self.sql = sql
            return Cursor()
        def commit(self):
            self.committed = True
        def rollback(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.closed = True

    conn = Conn()
    class Checkout:
        @staticmethod
        def create(**kwargs):
            assert conn.committed is True
            return type("Session", (), {"url": "https://checkout.example/session"})()

    class FakeStripe:
        checkout = type("CheckoutContainer", (), {"Session": Checkout})

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: conn)
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr("app.services.monitor_store._account_hash", lambda key: "account-hash")

    result = billing.create_checkout("secret", "pro")
    assert result == "https://checkout.example/session"
    assert conn.committed is True
    assert "FOR UPDATE" in conn.sql


def test_checkout_uses_owning_account_hash_in_metadata(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("account-hash", None, None, None, None, None)

    class Conn:
        def execute(self, sql, params=()):
            return Cursor()
        def commit(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    class Checkout:
        @staticmethod
        def create(**kwargs):
            assert kwargs["metadata"]["api_key_hash"] == "account-hash"
            return type("Session", (), {"url": "https://checkout.example/session"})()

    class FakeStripe:
        checkout = type("CheckoutContainer", (), {"Session": Checkout})

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr(billing, "_account_hash", lambda key: "key-hash")

    assert billing.create_checkout("shared-key", "pro") == "https://checkout.example/session"


def test_checkout_rejects_existing_pending_checkout(monkeypatch):
    import app.services.billing as billing
    from datetime import datetime, timezone, timedelta

    class Cursor:
        def fetchone(self):
            return ("account-hash", "cus_123", None, None, "pending-key", datetime.now(timezone.utc) + timedelta(minutes=5))

    class Conn:
        def execute(self, sql, params=()):
            return Cursor()
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_account_hash", lambda key: "account-hash")
    try:
        billing.create_checkout("secret", "pro")
    except ValueError as exc:
        assert "checkout is already in progress" in str(exc)
    else:
        raise AssertionError("expected ValueError")
