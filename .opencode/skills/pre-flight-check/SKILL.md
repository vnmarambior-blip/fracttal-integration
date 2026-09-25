---
name: pre-flight-check
description: Use when deciding GO or NO-GO before any sync, PUT, migration, or production action. Triggers also on Spanish: se puede, es seguro, dale, verifica gates, antes de actuar, chequear estado.
---

# Pre-Flight Check

GO/NO-GO gate before touching production. Read-only; zero side effects.

## Checks (in order, stop at first NO-GO)

1. **Branch + tree**: `git branch --show-current` (expect `main`) and `git status --short` clean (except known untracked).
2. **Gates R0/H1/R14**: `SELECT status,COUNT(*) FROM horometer_updates GROUP BY status` (R0 = zero `INTENT_RECORDED`); `verify_table_has_identity` (H1); P1.1 columns + unique index present (R14).
3. **Suite**: full `pytest -q` green. If it must run without DB, unset `SQL_CONNECTION_STRING` — it must still pass.
4. **OEM liveness** (only if the task needs live data): token check + one read per source. Never assume yesterday's live still works.

## Verdict

- **GO**: all green → proceed with the authorized action only.
- **NO-GO**: any red → report which check failed, stop, propose the fix as a separate task.

## Rules

- Read-only: SELECTs, GETs, `collect-only`, mocked tests. No PUT/POST/PATCH/DELETE, no SQL writes, no migrations.
- Never print secrets (tokens, connection strings, `.env` content); report counts and statuses only.
- One verdict per run; don't fix findings inline.
