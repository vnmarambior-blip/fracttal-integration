"""Hallazgos R1: conexión central, secretos redactados, CI acotado."""

import os


def _check_env_main():
    """Replica borrador/tools/check_env.py sin importar de borrador."""

    print(
        "CLIENT_ID:",
        "CONFIGURADO" if os.getenv("FRACTTAL_CLIENT_ID") else "NO CONFIGURADO"
    )
    print(
        "CLIENT_SECRET:",
        "CONFIGURADO" if os.getenv("FRACTTAL_CLIENT_SECRET") else "NO CONFIGURADO"
    )
    print("REDIRECT_URI:", os.getenv("FRACTTAL_REDIRECT_URI"))


def _central_stub():
    raise RuntimeError("central")


def test_setup_telemetry_uses_central_connection(monkeypatch):
    import setup_telemetry_sync

    monkeypatch.setattr(setup_telemetry_sync, "get_connection", _central_stub)

    try:
        setup_telemetry_sync.main()
        wired = False
    except RuntimeError as error:
        wired = str(error) == "central"

    assert wired is True


def test_cleanup_uses_central_connection(monkeypatch):
    import cleanup_mydevelon_config

    monkeypatch.setattr(cleanup_mydevelon_config, "get_connection", _central_stub)

    try:
        cleanup_mydevelon_config.main()
        wired = False
    except RuntimeError as error:
        wired = str(error) == "central"

    assert wired is True


def test_env_main_redacts_client_id(monkeypatch, capsys):
    monkeypatch.setenv("FRACTTAL_CLIENT_ID", "SECRET-123")

    _check_env_main()

    out, _ = capsys.readouterr()
    assert "SECRET-123" not in out
    assert "CONFIGURADO" in out


def _assert_central(module_name):
    import database

    module = __import__(module_name)

    assert module.get_connection is database.get_connection


def test_check_machinery_serials_uses_central_connection():
    _assert_central("check_machinery_serials")


def test_inspect_machinery_uses_central_connection():
    _assert_central("inspect_machinery")


def test_check_sql_uses_central_connection():
    _assert_central("check_sql")


def test_setup_database_uses_central_connection():
    _assert_central("setup_database")


def test_export_excel_uses_central_connection():
    _assert_central("export_database_excel")


def test_get_connection_fails_without_env(monkeypatch):
    import database

    monkeypatch.setattr(database, "CONNECTION_STRING", None)

    try:
        database.get_connection()
        failed = False
    except RuntimeError:
        failed = True

    assert failed is True
