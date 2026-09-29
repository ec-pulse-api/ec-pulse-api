from app.services import monitor_store


class FakeConn:
    def __init__(self):
        self.events = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.events.append(("execute", normalized))
        return self

    def fetchall(self):
        return []

    def commit(self):
        self.events.append(("commit", ""))


def test_research_trend_reads_previous_run_before_commit(monkeypatch):
    conn = FakeConn()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_args, **_kwargs: conn)
    monkeypatch.setattr(monitor_store, "_SCHEMA_READY", True)

    result = monitor_store.save_research_run(
        "ecp_live_test-key",
        {"url": "https://example.com", "comments": []},
        {"pain_points": []},
    )

    assert result["previous_run_id"] is None
    previous_index = next(i for i, event in enumerate(conn.events) if event[0] == "execute" and event[1].startswith("SELECT rr.id, rr.created_at"))
    commit_indices = [i for i, event in enumerate(conn.events) if event[0] == "commit"]
    assert commit_indices
    assert commit_indices[-1] > previous_index


def test_research_previous_run_order_has_stable_id_tiebreaker(monkeypatch):
    conn = FakeConn()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_args, **_kwargs: conn)
    monkeypatch.setattr(monitor_store, "_SCHEMA_READY", True)

    monitor_store.save_research_run(
        "ecp_live_test-key",
        {"url": "https://example.com", "comments": []},
        {"pain_points": []},
    )

    sql = next(event[1] for event in conn.events if event[0] == "execute" and event[1].startswith("SELECT rr.id, rr.created_at"))
    assert "ORDER BY rr.created_at DESC, rr.id DESC" in sql


def test_research_list_order_has_stable_id_tiebreaker(monkeypatch):
    conn = FakeConn()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_args, **_kwargs: conn)
    monkeypatch.setattr(monitor_store, "_SCHEMA_READY", True)

    monitor_store.list_research_runs("ecp_live_test-key")
    sql = next(event[1] for event in conn.events if event[0] == "execute" and event[1].startswith("WITH ranked AS"))
    assert "ORDER BY rr.created_at ASC, rr.id ASC" in sql
