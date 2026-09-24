# fracttal-integration

Hourmeter telemetry sync: **MyDevelon / Komtrax → SQL Server (audit + idempotency) → Fracttal**.

## Entry points

- `python run_mydevelon_sync.py` — daily MyDevelon → Fracttal executor (also run by CI).
  Default mode is fixture-based (`mydevelon_fleet_minutes.xml`, zero network).
  `--live` queries the real API respecting the 15-min quota guard.
- `python reconcile.py` — closes orphan P1.1 intents (Regla 0). Read-only verification, never PUTs.
- `python _compare_hours.py` — read-only Komtrax vs Fracttal hourmeter comparison (13 reconciled units).

## Safety model

- `SYNC_DRY_RUN=true` by default: everything is computed and audited, nothing is written to Fracttal.
- Productive sync requires Regla 0 (orphan intents) and H1 closed.
- Komtrax Fleet: 1 request per URL per 5 min (`RATE_LIMITED_LOCAL` otherwise); token reused ~2 h.
- Logs never contain tokens, connection strings, full XML, headers or `.env` content.

## Tests

```text
.venv\Scripts\python.exe -m pytest -q
```

CI runs the mock-safe subset listed in `.github/workflows/daily-mydevelon-sync.yml`.
Files named `test_*` without `test_*` functions are manual probes (see `tools/` after cleanup).

## Configuration

Copy `.env.example` to `.env` and fill real values locally. `.env` is gitignored and must never be committed.
