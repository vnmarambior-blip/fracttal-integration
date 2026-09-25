---
name: single-put-e2e
description: Use when executing exactly one authorized production PUT with verification. Triggers also on Spanish: un put, autoriza put, ejecuta put, e2e controlado, actualiza horometro en produccion.
---

# Single-PUT E2E

Controlled protocol for exactly one production PUT. One machine, one reading, then STOP.

## Preconditions (all required)

- Explicit per-machine authorization (serial + value on record).
- Live source reading newer than Fracttal `last_data.date` (verified, not assumed).
- Pre-flight check GO (gates R0/H1/R14, suite green).

## Protocol

1. **Intent preview**: dry-run the machine first; record decision, `old_value`, `new_value`, `idempotency_key`.
2. **Dedup check**: query the key — `VERIFIED` means already done (STOP, no-op); `WRITE_AMBIGUOUS` means blocked (STOP).
3. **Retryable transition only**: if a prior non-executed intent exists (`WOULD_UPDATE`/`ERROR` with no `verification_value` and Fracttal unchanged), transition it to `ERROR_RETRYABLE` with evidence message. Never touch `VERIFIED` rows.
4. **Single PUT**: one `process_equipment(dry_run=False)` call for that machine only.
5. **Verify**: require `status=VERIFIED` + `verification_status=PASS` + `verification_value` equal to the intended value (2 decimals).
6. **Evidence**: report event id, attempt count, SQL row, and a fresh Fracttal GET confirming the value.
7. **STOP**: no second machine, no full sync, no unrelated fixes in the same run.

## Rules

- One PUT per authorized run. A second machine needs a second authorization.
- Never re-execute a `VERIFIED` or `WRITE_AMBIGUOUS` intent.
- Never print secrets; report ids, values, counts, statuses only.
