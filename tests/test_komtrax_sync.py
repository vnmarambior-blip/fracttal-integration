"""Komtrax dry-run executor: decisions to pipeline, never productive writes."""

import inspect
from unittest.mock import Mock

import pytest
import requests


def _block(*args, **kwargs):
    raise AssertionError("red o escritura productiva en test dry-run")


def test_process_equipment_accepts_source_parameter():
    import api

    params = inspect.signature(api.process_equipment).parameters
    assert params["source"].default == "MyDevelon"


def test_dry_run_sends_only_update_to_pipeline(monkeypatch, tmp_path):
    import api
    import run_komtrax_sync

    fleet = (
        '<?xml version="1.0"?>'
        '<Fleet xmlns="http://www.jcmanet.or.jp/english2017/ISO/15143/-3/20190501"'
        ' snapshotTime="2026-09-24T00:00:00Z">'
        "<Equipment><EquipmentHeader>"
        "<OEMName>KOMATSU</OEMName><Model>M</Model>"
        "<EquipmentID>U1</EquipmentID><SerialNumber>S-UPDATE</SerialNumber>"
        "</EquipmentHeader>"
        '<CumulativeOperatingHours datetime="2026-09-24T00:00:00Z">'
        "<Hour>200.0</Hour></CumulativeOperatingHours>"
        "</Equipment>"
        "<Equipment><EquipmentHeader>"
        "<OEMName>KOMATSU</OEMName><Model>M</Model>"
        "<EquipmentID>U2</EquipmentID><SerialNumber>S-SKIP</SerialNumber>"
        "</EquipmentHeader>"
        '<CumulativeOperatingHours datetime="2026-09-24T00:00:00Z">'
        "<Hour>100.0</Hour></CumulativeOperatingHours>"
        "</Equipment>"
        "<Equipment><EquipmentHeader>"
        "<OEMName>KOMATSU</OEMName><Model>M</Model>"
        "<EquipmentID>U3</EquipmentID><SerialNumber>S-GAP</SerialNumber>"
        "</EquipmentHeader>"
        "</Equipment>"
        "</Fleet>"
    )
    fleet_file = tmp_path / "fleet.xml"
    fleet_file.write_text(fleet, encoding="utf-8")

    machines = [
        {"serial": "S-UPDATE", "unit": "U1", "model": "M"},
        {"serial": "S-SKIP", "unit": "U2", "model": "M"},
        {"serial": "S-GAP", "unit": "U3", "model": "M"},
    ]
    monkeypatch.setattr(run_komtrax_sync, "KOMTRAX_MACHINES", machines)
    monkeypatch.setattr(api, "get_access_token", lambda: "ft-token")
    monkeypatch.setattr(run_komtrax_sync, "get_fracttal_items", lambda token: [])

    def fake_hourmeter(ft_token, code, all_items):
        values = {"U1": 100.0, "U2": 100.0}
        if code not in values:
            return {"error": "EQUIPMENT_NOT_FOUND"}
        return {"value": values[code], "date": "2026-09-23T00:00:00"}

    monkeypatch.setattr(
        run_komtrax_sync, "get_fracttal_hourmeter", fake_hourmeter
    )
    calls = []
    monkeypatch.setattr(
        api,
        "process_equipment",
        lambda **kwargs: calls.append(kwargs)
        or {"status": "UPDATE", "serial": kwargs["serial"]},
    )
    monkeypatch.setattr(requests, "put", _block)
    monkeypatch.setattr(requests, "patch", _block)
    monkeypatch.setattr(requests, "delete", _block)

    result = run_komtrax_sync.main(
        ["--fleet-xml", str(fleet_file)], now="2026-09-24T12:00:00+00:00"
    )

    assert result["UPDATE"] == 1
    assert result["SKIP_EQUAL"] == 1
    assert result["REVIEW_INCONSISTENCY"] == 1
    assert len(calls) == 1
    assert calls[0]["serial"] == "S-UPDATE"
    assert calls[0]["source"] == "Komtrax"
    assert calls[0]["dry_run"] is True


def test_production_mode_aborts_before_anything(monkeypatch, tmp_path):
    import run_komtrax_sync

    fleet_file = tmp_path / "fleet.xml"
    fleet_file.write_text("<Fleet />", encoding="utf-8")
    monkeypatch.setenv("SYNC_DRY_RUN", "false")
    monkeypatch.setattr(requests, "get", _block)
    monkeypatch.setattr(requests, "post", _block)

    with pytest.raises(SystemExit) as exc:
        run_komtrax_sync.main(["--fleet-xml", str(fleet_file)])

    assert exc.value.code == 2


def test_executor_import_has_no_side_effects(monkeypatch, capsys):
    import mssql_python

    monkeypatch.setattr(mssql_python, "connect", _block)
    monkeypatch.setattr(requests, "post", _block)
    monkeypatch.setattr(requests, "get", _block)

    import importlib

    import run_komtrax_sync

    importlib.reload(run_komtrax_sync)

    out, _ = capsys.readouterr()
    assert out == ""


def test_apply_meter_reading_threads_source_to_telemetry_config(monkeypatch):
    import api
    from datetime import datetime, timezone

    equipment = {
        "id": 1,
        "code": "MN04",
        "field_4": "55267",
        "field_3": "GD675-5",
    }
    monkeypatch.setattr(
        api, "get_equipment_by_serial", lambda token, serial: dict(equipment)
    )
    monkeypatch.setattr(
        api, "get_machinery_by_id", lambda mid: {"serial": "55267"}
    )
    seen = []
    monkeypatch.setattr(
        api,
        "get_telemetry_sync_config",
        lambda machinery_id, telemetry_source: seen.append(telemetry_source),
    )
    base = dict(
        token="t",
        code="MN04",
        value=10599.8,
        serial="55267",
        reading_datetime=datetime(2026, 8, 11, 5, 0, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc),
        decision="UPDATE",
        dry_run=False,
        equipment=dict(equipment),
        machinery_id=40,
    )

    with pytest.raises(ValueError, match="CONFIG_MISSING"):
        api.apply_meter_reading(**dict(base, source="Komtrax"))
    assert seen == ["KOMTRAX"]

    with pytest.raises(ValueError, match="CONFIG_MISSING"):
        api.apply_meter_reading(**base)
    assert seen == ["KOMTRAX", "MYDEVELON"]
