from datetime import datetime, timezone

from app.services import rate_limit


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        assert sql.startswith("INSERT INTO api_rate_limits")
        assert "ON CONFLICT (api_key_hash) DO UPDATE" in sql
        assert "LEAST(api_rate_limits.request_count + 1, %s)" in sql
        current_window = params[1]
        limit_plus_one = params[2]
        if self.row is None or self.row[0] != current_window:
            self.row = (current_window, 1)
        else:
            self.row = (current_window, min(self.row[1] + 1, limit_plus_one))
        return FakeCursor(self.row)


def test_free_rate_limit_blocks_after_30_requests(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(rate_limit.psycopg, "connect", lambda *_args, **_kwargs: fake_conn)

    for _ in range(30):
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


def test_plan_rate_limit_boundaries(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    for plan, limit in (("pro", 300), ("business", 3000)):
        fake_conn = FakeConnection()
        monkeypatch.setattr(rate_limit.psycopg, "connect", lambda *_args, _conn=fake_conn, **_kwargs: _conn)
        for _ in range(limit):
            assert rate_limit.check_rate_limit(f"{plan}-hash", plan)["allowed"] is True
        blocked = rate_limit.check_rate_limit(f"{plan}-hash", plan)
        assert blocked["allowed"] is False
        assert blocked["remaining"] == 0
        assert blocked["limit"] == limit
