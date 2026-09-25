---
name: project-governance
description: Use when working in this repo before editing code, running syncs, touching SQL, or deciding scope. Triggers also on Spanish: reglas del proyecto, que puedo modificar, puedo hacer sync, como trabajo aqui, audita, se puede, es seguro, da permiso, autoriza.
---

# Project Governance

Authority lives in `AGENTS.md` (root) + `PROJECT_SPEC.md` (spec wins on conflict). This skill is a pointer, not a copy.

## When to Use

- Before any edit, sync, migration, or test run in this project.
- When deciding scope, files to touch, or whether an action needs approval.
- When NOT to use: generic coding questions outside this repo.

## Core Pattern

Objetivo → mínimo diagnóstico → acción → prueba mínima → resultado → STOP (`AGENTS.md:18-26`).

## Quick Reference

- Scope: one goal, one success criterion; out-of-scope findings get noted, never fixed inline.
- Edits: identify file + function, explain change, verify necessity; one file beats many.
- Tests: smallest proving test first (`pytest -q <file>`), full suite only on cross-cutting changes.
- Git: no auto commit/branch/merge/reset/history rewrites.
- Production: PUT/PATCH/DELETE, SQL writes, and full syncs need explicit approval. READ-ONLY means READ-ONLY.
- Secrets: never print tokens, connection strings, API keys, `.env` content.
- Files: don't create `_tmp`, `debug_*`, `check_*`, `verify_*`, reports, backups, `*_old/new/fixed`. Reuse before duplicating.
- SQL Server: `SQL_CONNECTION_STRING` from `.env` only; DB `FracttalIntegration` on `MSSQLSERVER`; `migrate_*.sql` before persistence tests.
- Done format: Resultado / Evidencia / Cambios / Bloqueos.

## Local Defaults (this machine/repo)

- Repo root: `C:\Users\vn246\Documents\Code\fracttal-integration` — always work here, never in parent `Code\`.
- Python: `.\.venv\Scripts\python.exe` (Windows PowerShell; no `tail/head/grep/wc`, use `Select-Object`).
- Quotas: MyDevelon fetch ≥900s apart; Komtrax ≥300s per URL. Never busy-wait against them.
- Branch discipline: daily work on `main`; confirm with `git branch --show-current` before committing.
- OEM quirks: MyDevelon `/token` may return HTTP 200 with JSON error — reject bodies starting with `{`; never cache them; never record fetch on empty fleet.
- `--live` never falls back to fixture silently; fixture only without `--live`.
- Worktrees under `Temp\opencode\wt-*` often locked (`Permission denied`) — don't force-delete.

## Safety Boundaries

- Suite must pass with `SQL_CONNECTION_STRING=''` (R1: test execution writes nothing to prod DB).
- No parallel syncs (P1.1 covers races, but sequential is the contract).
- No silent source substitution: header/report must show the real source (`live` vs `file:<path>`).
- Reports (`ejecucion_*.md`, `simulacion_*.md`, `reports/`) stay untracked; never commit run outputs.
- Single-PUT E2E: only with live readings newer than Fracttal + explicit approval per machine.

## Verification (evidence levels)

- `collect-only` ≠ executed. Claim `PASS` only with a real command + result.
- Distinguish: executed-this-session vs pre-existing evidence vs inferred-from-code.
- Confirm read-only runs wrote nothing (e.g., re-query `MAX(id)` range or run suite with blank connection string).
- Spot-check live state after E2E (Fracttal value + SQL row), don't trust the return dict alone.

## Handoff

- Requirement work → `spec-driven-qa` (implement) or `audit-project` (read-only).
- Architecture mapping → `project-architecture`.
- Telemetry/SQL/Fracttal → `telemetry-audit`, `fracttal-integration`, `data-quality`, `aemp-integration`.
