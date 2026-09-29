from app.services import monitor_store


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self):
        self.select_sql = None
        self.commits = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True

    def execute(self, sql, params=()):
        if "SELECT a.credits_balance" in sql:
            self.select_sql = sql
            return FakeCursor((10,))
        return FakeCursor(None)

    def commit(self):
        self.commits += 1


def test_consume_credit_locks_key_and_account_rows_together(monkeypatch):
    conn = FakeConn()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_args, **_kwargs: conn)
    monkeypatch.setattr(monitor_store, "_SCHEMA_READY", True)

    result = monitor_store.consume_credit("ecp_live_test-key", "GET /test", 3)

    assert result == {"credits_used": 3, "credits_remaining": 7}
    assert "FOR UPDATE OF k, a" in conn.select_sql
    assert conn.commits == 1
