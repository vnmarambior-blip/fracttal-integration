# Komtrax → Fracttal Hourmeter Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync the 8 validated Komtrax UPDATE candidates to Fracttal through the canonical write path, dry-run first, with quota guards and P1.1 idempotency preserved.

**Architecture:** Mirror `run_mydevelon_sync.py`: a `run_komtrax_sync.py` executor that reuses Komtrax acquisition helpers and calls `api.process_equipment(..., dry_run=True)` per machine. No new write path; only a `source` parameter addition. Productive writes stay blocked by `SYNC_DRY_RUN` default plus Regla 0 / H1 gates.

**Tech Stack:** Python, pytest, requests (mocked in tests), existing `api.py` / `mydevelon.py` helpers.

**Spec:** `PROJECT_SPEC.md` Reglas 21 (Komtrax), 22 (space normalization), P1.1 (idempotency), Regla 0 (orphan intents), Regla 4/H1; `docs/komtrax-iso-api.md` (endpoints, quota, retention).

## Global Constraints

- READ-ONLY until gates pass: no productive sync until Regla 0 (21 orphan intents reconciled) and H1 closed.
- `SYNC_DRY_RUN` defaults to true; productive mode requires explicit opt-in.
- Komtrax Fleet: max 1 GET per URL per 300 s; token reused for 7000 s; `Accept: application/xml`.
- Komtrax identity = Fracttal `code` + `field_4` (never Fracttal `serial`, always `None`); `is_serial_control: False`.
- Only `UPDATE` decisions from `decide_comparison` reach the write path; `SKIP_EQUAL` / `REVIEW_*` / `ERROR` never write.
- No secrets in logs (Regla 18): serials/values/counts only.
- TDD for every behavior change; full suite green before completion.

## Review Focus

- Komatsu serial with spaces (`CF 01` vs `CF01`): normalization must apply before any match — expect `CF01` to resolve.
- Serial present in Fleet but without `CumulativeOperatingHours` (retention gap): expect `REVIEW_INCONSISTENCY`, never sent to `process_equipment`.
- `process_equipment` called with `source="Komtrax"`: expect audit rows stamped Komtrax, MyDevelon rows unchanged.
- Second run with identical readings: expect idempotent skip via P1.1, no duplicate write intent.
- `--live` with gates open: expect refusal with non-zero exit and zero writes.

---

### Task 1: Make `_compare_hours.py` import-safe

**Files:**
- Modify: `_compare_hours.py` (wrap top-level main block in `def main():` + `if __name__ == "__main__":` guard; keep all function signatures identical)
- Test: `test_komtrax_rate_limit.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: importable `get_komtrax_token`, `get_komtrax_token_cached`, `get_komtrax_fleet`, `parse_komtrax_hours`, `classify_komtrax_gap`, `decide_comparison`, `get_fracttal_items`, `get_fracttal_hourmeter`, `KOMTRAX_MACHINES` with zero side effects on import.

- [ ] **Step 1: Write the failing test**

```python
def test_import_compare_hours_has_no_side_effects(compare_module, monkeypatch):
    import requests

    get = Mock(side_effect=AssertionError("no network on import"))
    post = Mock(side_effect=AssertionError("no network on import"))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)

    assert callable(compare_module.decide_comparison)
    assert len(compare_module.KOMTRAX_MACHINES) == 13
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest -q test_komtrax_rate_limit.py::test_import_compare_hours_has_no_side_effects`
Expected: FAIL (import executes network calls / NameError from main block)

- [ ] **Step 3: Write minimal implementation**

Wrap the `# Main` block: indent existing top-level statements into `def main():`, append:

```python
if __name__ == "__main__":
    main()
```

Change nothing else (same prints, same logic, same order).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest -q test_komtrax_rate_limit.py`
Expected: all PASS (note: the AST fixture loads definitions only, so update the fixture to a plain import now that import is side-effect free; keep all existing tests green).

- [ ] **Step 5: Commit**

```bash
git add _compare_hours.py test_komtrax_rate_limit.py
git commit -m "refactor: guard _compare_hours main block for safe import"
```

### Task 2: Add `source` parameter to `process_equipment`

**Files:**
- Modify: `api.py:1323` (`process_equipment` signature + audit `source=` usages)
- Test: `test_komtrax_sync.py` (new file)

**Interfaces:**
- Consumes: `api.process_equipment(token, serial, new_value, dry_run, reading_datetime, retrieved_at)`.
- Produces: `api.process_equipment(..., source="MyDevelon")` — default preserves every existing caller.

- [ ] **Step 1: Write the failing test**

```python
def test_process_equipment_accepts_source_parameter():
    import inspect
    import api

    params = inspect.signature(api.process_equipment).parameters
    assert params["source"].default == "MyDevelon"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest -q test_komtrax_sync.py::test_process_equipment_accepts_source_parameter`
Expected: FAIL with `KeyError: 'source'`

- [ ] **Step 3: Write minimal implementation**

```python
def process_equipment(
    token,
    serial,
    new_value,
    dry_run=True,
    reading_datetime=None,
    retrieved_at=None,
    source="MyDevelon",
):
```

Replace the three hardcoded `source="MyDevelon"` audit calls in that function with `source=source`. No other changes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest -q test_komtrax_sync.py test_r6_audit_states.py test_p1_1_idempotency.py`
Expected: all PASS (existing MyDevelon callers unchanged).

- [ ] **Step 5: Commit**

```bash
git add api.py test_komtrax_sync.py
git commit -m "feat: source parameter on process_equipment, default MyDevelon"
```

### Task 3: `run_komtrax_sync.py` dry-run executor

**Files:**
- Create: `run_komtrax_sync.py` (mirror `run_mydevelon_sync.py:57-124`: `--live` / `--fleet-xml` / `--report` args, `SYNC_DRY_RUN` default true, per-machine loop)
- Test: `test_komtrax_sync.py` (append)

**Interfaces:**
- Consumes: `_compare_hours.get_komtrax_token_cached`, `get_komtrax_fleet`, `parse_komtrax_hours`, `classify_komtrax_gap`, `decide_comparison`, `api.process_equipment`, `api.get_access_token`.
- Produces: `run_komtrax_sync.main(argv)` returning a counts dict; file mode uses zero network.

- [ ] **Step 1: Write the failing test**

```python
def test_dry_run_sends_only_update_decisions(tmp_path):
    import run_komtrax_sync

    calls = []
    fixture = tmp_path / "fleet.xml"
    fixture.write_text(_SYNTH_FLEET_WITH_ONE_UPDATE, encoding="utf-8")

    with patch.object(run_komtrax_sync, "process_equipment", side_effect=lambda **kw: calls.append(kw) or {"status": "UPDATE", "serial": kw["serial"]}):
        result = run_komtrax_sync.main(["--fleet-xml", str(fixture)])

    assert result["UPDATE"] == 1
    assert all(c["dry_run"] is True and c["source"] == "Komtrax" for c in calls)
```

(with `_SYNTH_FLEET_WITH_ONE_UPDATE`: 1 machine with hours above fixture Fracttal value, 1 `SKIP_EQUAL`, 1 `NO_HOURS` gap; mock `get_fracttal_*` to return fixed readings.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest -q test_komtrax_sync.py::test_dry_run_sends_only_update_decisions`
Expected: FAIL with "No module named run_komtrax_sync"

- [ ] **Step 3: Write minimal implementation**

Executor flow (mirror `run_mydevelon_sync.main`):
1. `dry_run = env_flag("SYNC_DRY_RUN", default=True)`; file mode default (no `--live` → fixture, zero network).
2. Live mode only: cached token + guarded single Fleet GET (reuses Task 1 helpers, so quota rules apply automatically).
3. Per serial in `KOMTRAX_MACHINES`: gap check → `decide_comparison` → only `UPDATE` calls `process_equipment(..., source="Komtrax", dry_run=dry_run, reading_datetime=kt_dt, retrieved_at=now)`.
4. Return counts dict `{UPDATE, SKIP_EQUAL, REVIEW_OLD_SOURCE, REVIEW_INCONSISTENCY, ERROR}`; print summary table.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest -q test_komtrax_sync.py`
Expected: all PASS with zero network (assert `requests.get/post` mocks uncalled in file mode).

- [ ] **Step 5: Commit**

```bash
git add run_komtrax_sync.py test_komtrax_sync.py
git commit -m "feat: run_komtrax_sync dry-run executor"
```

- [ ] **Step 6: Pin Regla 22 space normalization (review-focus test)**

```python
def test_cf01_with_space_normalizes_before_match():
    import run_komtrax_sync

    assert run_komtrax_sync.normalize_unit("CF 01") == "CF01"
```

Run: `.venv\Scripts\python.exe -m pytest -q test_komtrax_sync.py -k normalize`
Expected: FAIL then PASS after adding the normalization helper used for `unit` matching. Applies to code matching only; Fracttal `code` values are never rewritten.

### Task 4: Gate productive mode on Regla 0 / H1 + docs

**Files:**
- Modify: `run_komtrax_sync.py` (gate check), `PROJECT_SPEC.md` (Regla 21: executor + gates)
- Test: `test_komtrax_sync.py` (append)

**Interfaces:**
- Consumes: existing gate state (Regla 0 orphan-intent count; H1 flag — reuse whatever `reconcile.py` exposes; if no query helper exists, gate on explicit env `KOMTRAX_SYNC_GATES_OK=1` set only after manual closure).
- Produces: `--live` + `SYNC_DRY_RUN=false` with gates open → refusal, non-zero exit, zero writes.

- [ ] **Step 1: Write the failing test**

```python
def test_live_mode_refuses_when_gates_open(tmp_path):
    import run_komtrax_sync

    fixture = tmp_path / "fleet.xml"
    fixture.write_text(_SYNTH_FLEET_WITH_ONE_UPDATE, encoding="utf-8")

    with pytest.raises(SystemExit):
        run_komtrax_sync.main(["--live", "--fleet-xml", str(fixture)])
```

(with gates forced open via monkeypatched gate query returning open, and `SYNC_DRY_RUN=false`).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest -q test_komtrax_sync.py::test_live_mode_refuses_when_gates_open`
Expected: FAIL (live proceeds instead of refusing)

- [ ] **Step 3: Write minimal implementation**

At start of live path, before any network:

```python
if not dry_run and not gates_closed():
    print("BLOQUEADO: Regla 0 / H1 abiertos; solo dry-run permitido.")
    raise SystemExit(2)
```

- [ ] **Step 4: Run full suite to verify**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: 151+ new tests PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add run_komtrax_sync.py test_komtrax_sync.py PROJECT_SPEC.md
git commit -m "feat: gate komtrax productive sync on Regla 0/H1"
```
