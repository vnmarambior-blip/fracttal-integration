"""run_all_sync: no aborta Komtrax si MyDevelon falla. Exit 0/1/3."""

import subprocess
import sys
from unittest.mock import patch

import run_all_sync


def _result(returncode=0):
    proc = subprocess.CompletedProcess(args=[], returncode=returncode)
    return proc


def test_both_ok_exits_zero():
    with patch.object(
        run_all_sync.subprocess, "run", return_value=_result(0)
    ) as mocked:
        with patch.object(sys, "argv", ["run_all_sync.py"]):
            assert run_all_sync.main() == 0
    assert mocked.call_count == 2


def test_mydevelon_fail_still_runs_komtrax_partial():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[1])
        if cmd[1] == "run_mydevelon_sync.py":
            raise subprocess.CalledProcessError(1, cmd)
        return _result(0)

    with patch.object(run_all_sync.subprocess, "run", side_effect=fake_run):
        with patch.object(sys, "argv", ["run_all_sync.py"]):
            assert run_all_sync.main() == 3
    assert calls == ["run_mydevelon_sync.py", "run_komtrax_sync.py"]


def test_both_fail_exits_one():
    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    with patch.object(run_all_sync.subprocess, "run", side_effect=fake_run):
        with patch.object(sys, "argv", ["run_all_sync.py"]):
            assert run_all_sync.main() == 1


def test_report_not_forwarded_to_komtrax():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _result(0)

    with patch.object(run_all_sync.subprocess, "run", side_effect=fake_run):
        with patch.object(
            sys, "argv",
            ["run_all_sync.py", "--live", "--report", "r.md"],
        ):
            assert run_all_sync.main() == 0

    assert calls[0] == [
        run_all_sync.sys.executable,
        "run_mydevelon_sync.py", "--live", "--report", "r.md",
    ]
    assert calls[1] == [
        run_all_sync.sys.executable,
        "run_komtrax_sync.py", "--live",
    ]


def test_fleet_xml_value_forwarded_to_komtrax():
    assert run_all_sync.komtrax_args_from(
        ["--live", "--fleet-xml", "f.xml", "--report", "r.md"]
    ) == ["--live", "--fleet-xml", "f.xml"]
    assert run_all_sync.komtrax_args_from([]) == []
