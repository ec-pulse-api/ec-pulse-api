from app.services import monitor_store


def test_history_rows_use_id_as_deterministic_tiebreaker(monkeypatch):
    captured = []

    class Cursor:
        def execute(self, sql, params):
            captured.append((sql, params))
            return self

        def fetchall(self):
            return []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            return Cursor().execute(sql, params)

    monitor_store._history_rows(Connection(), "monitor-1", 10)

    assert "ORDER BY captured_at DESC, id DESC LIMIT %s" in captured[0][0]
    assert captured[0][1] == ("monitor-1", 10)
