"""R17: importar un módulo no debe producir efectos externos.

Sin POSTs, sin conexiones SQL, sin UPDATE/DELETE, sin secretos por stdout.
"""

import importlib

import pytest

MODULES = [
    "oauth",
    "check_machinery_serials",
    "inspect_machinery",
    "setup_telemetry_sync",
    "check_sql",
    "check_env",
    "cleanup_mydevelon_config",
    "check_equipment_by_serial",
    "reconcile",
]


def _block(*args, **kwargs):
    raise AssertionError("efecto lateral al importar")


@pytest.mark.parametrize("name", MODULES)
def test_import_has_no_side_effects(monkeypatch, capsys, name):
    import mssql_python
    import requests

    monkeypatch.setattr(mssql_python, "connect", _block)
    monkeypatch.setattr(requests, "post", _block)
    monkeypatch.setattr(requests, "get", _block)

    module = importlib.import_module(name)
    importlib.reload(module)

    out, _ = capsys.readouterr()
    assert out == ""


TOOLS_MODULES = [
    "audit_hourmeters",
    "audit_mydevelon_fleet",
    "check_database",
    "check_fracttal_develon",
    "check_fracttal_sql",
    "consultar_fracttal",
    "export_database_excel",
    "inspect_telemetry_config",
    "main",
    "setup_database",
    "sync_machinery",
    "_compare_hours",
    "_reconcile_komtrax",
]


@pytest.mark.parametrize("name", TOOLS_MODULES)
def test_tools_import_has_no_side_effects(monkeypatch, capsys, name):
    import mssql_python
    import requests

    monkeypatch.setattr(mssql_python, "connect", _block)
    monkeypatch.setattr(requests, "post", _block)
    monkeypatch.setattr(requests, "get", _block)

    module = importlib.import_module(name)
    importlib.reload(module)

    out, _ = capsys.readouterr()
    assert out == ""
