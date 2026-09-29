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

    def execute(self, sql, params=()):
        if "SELECT api_key_hash" in sql:
            return FakeCursor([("account-hash",)])
        if "SELECT last_stripe_event_created" in sql:
            return FakeCursor([self.state])
        self.updates += 1
        self.last_params = params
        return FakeCursor([])


def _subscription(status="active"):
    return {
        "id": "sub_123",
        "customer": "cus_123",
        "status": status,
        "items": {"data": [{"price": {"id": "price_pro"}}]},
        "_ec_pulse_event_id": "evt_123",
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


def test_same_timestamp_older_event_id_is_ignored(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn((100, "evt_002"))
    assert _apply_subscription(conn, _subscription("active"), 100) is False
    assert conn.updates == 0


def test_same_timestamp_newer_event_id_is_applied(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn((100, "evt_001"))
    assert _apply_subscription(conn, _subscription("active"), 100) is True
    assert conn.updates == 1
