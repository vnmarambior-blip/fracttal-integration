"""run_all_sync: default dry-run, reporte consolidado, fixtures por fuente."""

import subprocess
import sys
from unittest.mock import patch

import run_all_sync


def _result(returncode=0, stdout="out"):
    proc = subprocess.CompletedProcess(args=[], returncode=returncode)
    proc.stdout = stdout
    proc.stderr = ""
    return proc


def test_default_is_dry_run_without_live():
    calls = []
    seen_env = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[1])
        seen_env.append(kwargs["env"]["SYNC_DRY_RUN"])
        return _result(0)

    with patch.object(run_all_sync.subprocess, "run", side_effect=fake_run):
        assert run_all_sync.main([]) == 0

    assert calls == ["run_mydevelon_sync.py", "run_komtrax_sync.py"]
    assert seen_env == ["true", "true"]


def test_live_explicit_enables_production():
    seen_env = []

    def fake_run(cmd, **kwargs):
        seen_env.append(kwargs["env"]["SYNC_DRY_RUN"])
        return _result(0)

    with patch.object(run_all_sync.subprocess, "run", side_effect=fake_run):
        assert run_all_sync.main(["--live"]) == 0

    assert seen_env == ["false", "false"]


def test_both_ok_exits_zero():
    with patch.object(
        run_all_sync.subprocess, "run", return_value=_result(0)
    ) as mocked:
        assert run_all_sync.main([]) == 0
    assert mocked.call_count == 2


def test_mydevelon_fail_still_runs_komtrax_partial():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[1])
        if cmd[1] == "run_mydevelon_sync.py":
            raise subprocess.CalledProcessError(1, cmd)
        return _result(0)

    with patch.object(run_all_sync.subprocess, "run", side_effect=fake_run):
        assert run_all_sync.main([]) == 3
    assert calls == ["run_mydevelon_sync.py", "run_komtrax_sync.py"]


def test_both_fail_exits_one():
    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    with patch.object(run_all_sync.subprocess, "run", side_effect=fake_run):
        assert run_all_sync.main([]) == 1


def test_report_not_forwarded_to_workers(tmp_path):
    calls = []
    report = str(tmp_path / "r.md")

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _result(0, stdout="worker-ok")

    with patch.object(run_all_sync.subprocess, "run", side_effect=fake_run):
        assert run_all_sync.main(["--live", "--report", report]) == 0

    assert calls[0] == [
        run_all_sync.sys.executable,
        "run_mydevelon_sync.py", "--live",
    ]
    assert calls[1] == [
        run_all_sync.sys.executable,
        "run_komtrax_sync.py", "--live",
    ]

    text = open(report, encoding="utf-8").read()
    assert "MyDevelon -> Fracttal" in text
    assert "Komtrax -> Fracttal" in text
    assert text.count("worker-ok") == 2


def test_fixtures_split_per_source():
    parsed = run_all_sync.split_orchestrator_args(
        ["--md-fleet-xml", "m.xml", "--kt-fleet-xml", "k.xml"]
    )

    assert parsed["md_args"] == ["--fleet-xml", "m.xml"]
    assert parsed["kt_args"] == ["--fleet-xml", "k.xml"]
    assert parsed["report"] is None


def test_no_shared_fleet_xml():
    parsed = run_all_sync.split_orchestrator_args(["--fleet-xml", "f.xml"])

    assert parsed["md_args"] == []
    assert parsed["kt_args"] == []
