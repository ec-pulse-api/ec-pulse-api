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
        self.update_params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True

    def execute(self, sql, params=()):
        if "SELECT a.api_key_hash, a.credits_balance" in sql:
            self.select_sql = sql
            return FakeCursor(("account-hash", 10))
        if "UPDATE api_accounts SET credits_balance" in sql:
            self.update_params = params
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
    assert conn.update_params[-1] == "account-hash"


def test_ensure_api_account_resolves_owning_account(monkeypatch):
    class Cursor:
        def fetchone(self):
            return ("pro", 97, __import__("datetime").datetime(2026, 9, 29), __import__("datetime").datetime(2026, 9, 29))

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params=()):
            assert "JOIN api_accounts a ON a.api_key_hash = k.account_key_hash" in sql
            assert "k.active = TRUE" in sql
            return Cursor()

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_args, **_kwargs: Conn())
    monkeypatch.setattr(monitor_store, "_SCHEMA_READY", True)
    result = monitor_store.ensure_api_account("ecp_live_shared-key")
    assert result["plan"] == "pro"
    assert result["credits_balance"] == 97



def test_get_account_usage_aggregates_all_keys_on_owning_account(monkeypatch):
    from datetime import datetime

    class Cursor:
        def __init__(self, row=None, rows=None):
            self.row = row
            self.rows = rows or []
        def fetchone(self): return self.row
        def fetchall(self): return self.rows

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params=()):
            if "SELECT a.plan, a.credits_balance" in sql:
                assert "JOIN api_keys k ON k.account_key_hash = a.api_key_hash" in sql
                assert "k.active = TRUE" in sql
                return Cursor(("pro", 97, datetime(2026, 9, 29), datetime(2026, 9, 29)))
            if "GROUP BY u.endpoint" in sql:
                assert "JOIN api_keys k ON k.api_key_hash = u.api_key_hash" in sql
                return Cursor(rows=[("POST /v1/products", 8, 2)])
            if "date_trunc('month'" in sql:
                return Cursor((8, 2))
            if "INTERVAL '24 hours'" in sql:
                return Cursor((8, 2))
            raise AssertionError(sql)

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_args, **_kwargs: Conn())
    monkeypatch.setattr(monitor_store, "_SCHEMA_READY", True)

    result = monitor_store.get_account_usage("ecp_live_shared-key")

    assert result["credits_balance"] == 97
    assert result["total_credits_used"] == 8
    assert result["usage"] == [{"endpoint": "POST /v1/products", "credits": 8, "requests": 2}]
    assert result["period_usage"]["month_to_date"] == {"credits": 8, "requests": 2}
    assert result["period_usage"]["last_24_hours"] == {"credits": 8, "requests": 2}
