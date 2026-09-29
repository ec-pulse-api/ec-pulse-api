from app.services.billing import _apply_subscription


class FakeCursor:
    def __init__(self, rows):
        self.rows = iter(rows)

    def fetchone(self):
        return next(self.rows)


class FakeConn:
    def __init__(self, state):
        self.state = state
        self.updates = 0
        self.last_params = None

    def execute(self, sql, params=()):
        if "SELECT api_key_hash" in sql:
            return FakeCursor([("account-hash",)])
        if "SELECT last_stripe_event_created" in sql:
            return FakeCursor([self.state])
        self.updates += 1
        self.last_params = params
        return FakeCursor([])


def _subscription(event_id: str):
    return {
        "id": "sub_123",
        "customer": "cus_123",
        "status": "active",
        "items": {"data": [{"price": {"id": "price_pro"}}]},
        "_ec_pulse_event_id": event_id,
    }


def test_same_timestamp_older_event_id_is_ignored(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn((100, "evt_002"))
    assert _apply_subscription(conn, _subscription("evt_001"), 100) is False
    assert conn.updates == 0


def test_same_timestamp_newer_event_id_is_applied(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    conn = FakeConn((100, "evt_001"))
    assert _apply_subscription(conn, _subscription("evt_002"), 100) is True
    assert conn.updates == 1
    assert conn.last_params[-3] == "evt_002"
