"""Fase 4 Task 4.1: Health Check module. Todo mockeado, cero red/DB."""

import pytest


def _ok_token(*args, **kwargs):
    return "token-ok"


def _fail_token(*args, **kwargs):
    raise RuntimeError("auth failed")


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)

    def close(self):
        return None


def test_fracttal_ok(monkeypatch):
    import api
    from operational import health

    monkeypatch.setattr(api, "get_access_token", _ok_token)
    monkeypatch.setattr(api, "get_all_equipment", lambda token: [{"id": 1}])

    result = health.check_fracttal()

    assert result["component"] == "Fracttal"
    assert result["status"] == "OK"
    assert result["critical"] is True
    assert result["latency_ms"] >= 0


def test_fracttal_fail_is_critical(monkeypatch):
    import api
    from operational import health

    monkeypatch.setattr(api, "get_access_token", _fail_token)

    result = health.check_fracttal()

    assert result["status"] == "FAIL"
    assert result["critical"] is True


def test_sql_ok(monkeypatch):
    import database
    from operational import health

    monkeypatch.setattr(
        database, "get_connection", lambda: _FakeConnection([(1,)])
    )

    result = health.check_sql()

    assert result["component"] == "SQL Server"
    assert result["status"] == "OK"
    assert result["critical"] is True


def test_sql_fail_is_critical(monkeypatch):
    import database
    from operational import health

    def _fail_connect():
        raise RuntimeError("no sql")

    monkeypatch.setattr(database, "get_connection", _fail_connect)

    result = health.check_sql()

    assert result["status"] == "FAIL"
    assert result["critical"] is True


def test_mydevelon_degraded_on_quota(monkeypatch):
    import mydevelon
    from operational import health

    monkeypatch.setattr(mydevelon, "get_access_token", _ok_token)
    monkeypatch.setattr(
        health, "_mydevelon_fetch_allowed", lambda: (False, 720)
    )

    result = health.check_mydevelon()

    assert result["status"] == "DEGRADED"
    assert result["critical"] is False
    assert "720" in result["detail"] or "12" in result["detail"]


def test_mydevelon_fail_is_warn_not_abort(monkeypatch):
    import mydevelon
    from operational import health

    monkeypatch.setattr(mydevelon, "get_access_token", _fail_token)

    result = health.check_mydevelon()

    assert result["status"] in ("DEGRADED", "FAIL")
    assert result["critical"] is False


def test_komtrax_ok(monkeypatch):
    import komtrax
    from operational import health

    monkeypatch.setattr(komtrax, "get_komtrax_token_cached", _ok_token)
    monkeypatch.setattr(
        health, "_komtrax_fetch_allowed", lambda: (True, 0)
    )

    result = health.check_komtrax()

    assert result["status"] == "OK"
    assert result["critical"] is False


def test_config_warn_when_empty(monkeypatch):
    import database
    from operational import health

    monkeypatch.setattr(database, "get_connection", lambda: _FakeConnection([]))

    result = health.check_config()

    assert result["status"] == "WARN"
    assert result["critical"] is False


def test_overall_exit_code_blocks_on_critical(monkeypatch):
    from operational import health

    monkeypatch.setattr(
        health,
        "check_fracttal",
        lambda: {"component": "Fracttal", "status": "FAIL", "critical": True},
    )
    monkeypatch.setattr(
        health,
        "check_sql",
        lambda: {"component": "SQL Server", "status": "OK", "critical": True},
    )
    monkeypatch.setattr(
        health,
        "check_mydevelon",
        lambda: {"component": "MyDevelon", "status": "OK", "critical": False},
    )
    monkeypatch.setattr(
        health,
        "check_komtrax",
        lambda: {"component": "Komtrax", "status": "OK", "critical": False},
    )
    monkeypatch.setattr(
        health,
        "check_config",
        lambda: {"component": "Config", "status": "OK", "critical": False},
    )

    result = health.run_health_checks()

    assert result["exit_code"] == 2
    assert result["can_proceed"] is False


def test_overall_exit_code_zero_with_warns(monkeypatch):
    from operational import health

    monkeypatch.setattr(
        health,
        "check_fracttal",
        lambda: {"component": "Fracttal", "status": "OK", "critical": True},
    )
    monkeypatch.setattr(
        health,
        "check_sql",
        lambda: {"component": "SQL Server", "status": "OK", "critical": True},
    )
    monkeypatch.setattr(
        health,
        "check_mydevelon",
        lambda: {"component": "MyDevelon", "status": "DEGRADED", "critical": False},
    )
    monkeypatch.setattr(
        health,
        "check_komtrax",
        lambda: {"component": "Komtrax", "status": "OK", "critical": False},
    )
    monkeypatch.setattr(
        health,
        "check_config",
        lambda: {"component": "Config", "status": "WARN", "critical": False},
    )

    result = health.run_health_checks()

    assert result["exit_code"] == 0
    assert result["can_proceed"] is True
