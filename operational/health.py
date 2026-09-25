# -*- coding: utf-8 -*-
"""Fase 4 Task 4.1: Health checks read-only.

Cada check retorna: component, status (OK/DEGRADED/WARN/FAIL),
latency_ms, detail, critical.
"""

import time

import api
import database
import komtrax
import mydevelon


def _timed(call):
    """Ejecuta call() midiendo latencia. Retorna (ok, value, latency_ms)."""

    started = time.perf_counter()

    try:
        value = call()
    except Exception as error:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return False, error, elapsed_ms

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return True, value, elapsed_ms


def check_fracttal():
    """Auth + 1 item. Critico."""

    def _check():
        token = api.get_access_token()
        items = api.get_all_equipment(token)

        return len(items)

    ok, value, latency_ms = _timed(_check)

    if not ok:
        return {
            "component": "Fracttal",
            "status": "FAIL",
            "latency_ms": latency_ms,
            "detail": str(value),
            "critical": True,
        }

    return {
        "component": "Fracttal",
        "status": "OK",
        "latency_ms": latency_ms,
        "detail": f"{value} equipos",
        "critical": True,
    }


def check_sql():
    """SELECT 1 + tabla horometer_updates. Critico."""

    def _check():
        connection = database.get_connection()

        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_NAME = 'horometer_updates'"
            )
            exists = cursor.fetchone()[0]
        finally:
            connection.close()

        return exists

    ok, value, latency_ms = _timed(_check)

    if not ok or not value:
        return {
            "component": "SQL Server",
            "status": "FAIL",
            "latency_ms": latency_ms,
            "detail": str(value) if not ok else "horometer_updates inexistente",
            "critical": True,
        }

    return {
        "component": "SQL Server",
        "status": "OK",
        "latency_ms": latency_ms,
        "detail": "horometer_updates OK",
        "critical": True,
    }


def _mydevelon_fetch_allowed():
    """Cuota sin consumir fetch. Retorna (allowed, wait_seconds)."""

    from datetime import datetime, timezone

    last = mydevelon._read_timestamp(".mydevelon_last_fetch.txt")

    if last is None:
        return True, 0

    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    interval = 900

    if elapsed >= interval:
        return True, 0

    return False, int(interval - elapsed)


def check_mydevelon():
    """Auth token. WARN (no critico)."""

    def _check():
        return mydevelon.get_access_token()

    ok, value, latency_ms = _timed(_check)

    if not ok:
        return {
            "component": "MyDevelon",
            "status": "DEGRADED",
            "latency_ms": latency_ms,
            "detail": str(value),
            "critical": False,
        }

    allowed, wait_seconds = _mydevelon_fetch_allowed()

    if not allowed:
        minutes = max(1, wait_seconds // 60)
        return {
            "component": "MyDevelon",
            "status": "DEGRADED",
            "latency_ms": latency_ms,
            "detail": f"cuota {wait_seconds}s restantes (~{minutes} min)",
            "critical": False,
        }

    return {
        "component": "MyDevelon",
        "status": "OK",
        "latency_ms": latency_ms,
        "detail": "token OK, cuota disponible",
        "critical": False,
    }


def _komtrax_fetch_allowed():
    """Cuota sin consumir fetch. Retorna (allowed, wait_seconds)."""

    from datetime import datetime, timezone

    last = mydevelon._read_timestamp(".komtrax_fleet_state.txt")

    if last is None:
        return True, 0

    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    interval = 300

    if elapsed >= interval:
        return True, 0

    return False, int(interval - elapsed)


def check_komtrax():
    """Auth token (cache). WARN (no critico)."""

    def _check():
        return komtrax.get_komtrax_token_cached()

    ok, value, latency_ms = _timed(_check)

    if not ok:
        return {
            "component": "Komtrax",
            "status": "DEGRADED",
            "latency_ms": latency_ms,
            "detail": str(value),
            "critical": False,
        }

    allowed, wait_seconds = _komtrax_fetch_allowed()

    if not allowed:
        return {
            "component": "Komtrax",
            "status": "DEGRADED",
            "latency_ms": latency_ms,
            "detail": f"cuota {wait_seconds}s restantes",
            "critical": False,
        }

    return {
        "component": "Komtrax",
        "status": "OK",
        "latency_ms": latency_ms,
        "detail": "token OK, cuota disponible",
        "critical": False,
    }


def check_config():
    """telemetry_sync_config tiene filas. WARN (no critico)."""

    def _check():
        connection = database.get_connection()

        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT telemetry_source, COUNT(*) "
                "FROM telemetry_sync_config GROUP BY telemetry_source"
            )
            rows = cursor.fetchall()
        finally:
            connection.close()

        return [(row[0], row[1]) for row in rows]

    ok, value, latency_ms = _timed(_check)

    if not ok:
        return {
            "component": "Config",
            "status": "WARN",
            "latency_ms": latency_ms,
            "detail": str(value),
            "critical": False,
        }

    if not value:
        return {
            "component": "Config",
            "status": "WARN",
            "latency_ms": latency_ms,
            "detail": "sin filas en telemetry_sync_config",
            "critical": False,
        }

    detail = ", ".join(f"{source}: {count}" for source, count in value)

    return {
        "component": "Config",
        "status": "OK",
        "latency_ms": latency_ms,
        "detail": detail,
        "critical": False,
    }


def run_health_checks():
    """Ejecuta los 5 checks. Critico fallido -> exit 2."""

    checks = [
        check_fracttal(),
        check_sql(),
        check_mydevelon(),
        check_komtrax(),
        check_config(),
    ]

    blocked = any(
        check["critical"] and check["status"] == "FAIL" for check in checks
    )

    return {
        "checks": checks,
        "exit_code": 2 if blocked else 0,
        "can_proceed": not blocked,
    }
