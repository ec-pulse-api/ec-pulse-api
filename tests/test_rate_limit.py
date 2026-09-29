from datetime import datetime, timezone

from app.services import rate_limit


class FakeCursor:
    def __init__(self, state):
        self.state = state

    def fetchone(self):
        return self.state["row"]


class FakeConnection:
    def __init__(self):
        self.state = {"row": None}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        if sql.startswith("SELECT window_start, request_count"):
            return FakeCursor(self.state)
        if sql.startswith("INSERT INTO api_rate_limits"):
            self.state["row"] = (params[1], 1)
            return FakeCursor(self.state)
        if sql.startswith("UPDATE api_rate_limits"):
            self.state["row"] = (self.state["row"][0], params[0])
            return FakeCursor(self.state)
        raise AssertionError(sql)


def test_free_rate_limit_blocks_after_30_requests(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(rate_limit.psycopg, "connect", lambda *_args, **_kwargs: fake_conn)

    first = rate_limit.check_rate_limit("hash", "free")
    assert first["allowed"] is True
    assert first["remaining"] == 29

    for _ in range(28):
        assert rate_limit.check_rate_limit("hash", "free")["allowed"] is True

    blocked = rate_limit.check_rate_limit("hash", "free")
    assert blocked["allowed"] is False
    assert blocked["remaining"] == 0


def test_rate_limit_resets_on_new_window(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(rate_limit.psycopg, "connect", lambda *_args, **_kwargs: fake_conn)

    class FakeDateTime(datetime):
        current = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(rate_limit, "datetime", FakeDateTime)

    for _ in range(30):
        assert rate_limit.check_rate_limit("hash", "free")["allowed"] is True
    assert rate_limit.check_rate_limit("hash", "free")["allowed"] is False

    FakeDateTime.current = datetime(2026, 9, 29, 0, 1, tzinfo=timezone.utc)
    reset = rate_limit.check_rate_limit("hash", "free")
    assert reset["allowed"] is True
    assert reset["remaining"] == 29
