---
name: fracttal-integration
description: Interact with the Fracttal ONE API (equipment, meters, readings) with SQL Server as control/audit layer. Use when writing or verifying Fracttal reads/writes, idempotency, or controlled updates.
---
# Skill: Fracttal Integration

## Purpose

This skill defines how to interact with the Fracttal ONE API within the telemetry integration project.

Fracttal is the operational destination for telemetry values.

SQL Server is the control, audit, configuration, and historical integration layer.

The integration must prioritize correctness, traceability, idempotency, and controlled writes.

---

## Architecture

The intended flow is:

OEM / Telematics
→ Python OEM Adapter
→ Normalized Telemetry
→ SQL Server
→ Fracttal
→ Power BI

Fracttal should not become the primary integration control layer.

SQL Server maintains the integration state and audit trail.

---

## Existing API

Reuse the existing Fracttal authentication and API helpers.

Do not create a second authentication system unnecessarily.

Do not invent endpoint paths when an existing implementation already provides the required functionality.

Current relevant endpoints:

### Equipment

/api/items/

### Meters

/api/meters/

### Meter readings

/api/meter_reading/

---

## Pagination

Fracttal pagination uses:

start

Do not assume:

offset

unless the current API implementation explicitly uses it for a different endpoint.

When implementing pagination:

1. inspect the existing API helper
2. confirm the response structure
3. follow the established project pattern
4. avoid creating a parallel pagination abstraction unnecessarily

---

## Equipment Mapping

Current equipment fields:

field_1 = name
field_2 = manufacturer
field_3 = model
field_4 = serial
code = equipment code

Equipment type:

item_type = 2

Serial is the primary identity attribute.

Do not use:

- name
- model
- code
- EquipmentID

as the primary asset identity when a serial is available.

---

## Equipment Matching

Preferred matching order:

1. exact serial
2. documented OEM-specific identity mapping
3. explicit configuration mapping

Do not guess based only on:

- similar names
- similar models
- equipment codes
- partial descriptions

If multiple equipment records match:

stop and classify the mapping as ambiguous.

Do not silently choose the first result.

---

## Meter Validation

A valid operating-hour meter must satisfy:

units_code = HRS

and:

is_counter = true

and:

description does not contain:

NO UTILIZAR

The meter must belong to the correct Fracttal equipment.

Where serial information is available, the meter serial should match the equipment serial.

---

## NO UTILIZAR

Meters marked:

NO UTILIZAR

must never be:

- selected
- updated
- reactivated
- deleted
- used as fallback

They may be reported as evidence of a data-quality issue.

---

## Multiple Meters

If an equipment has multiple candidate hourmeters:

Do not guess.

Evaluate:

- units
- counter status
- description
- equipment relationship
- serial
- active state
- historical usage
- documented configuration

If uniqueness cannot be demonstrated:

return a review/error condition.

Do not implement machine-specific exceptions merely to make the process pass.

---

## Meter Serial Mismatch

A meter serial mismatch is a data-quality issue.

Example:

Equipment serial:
DX12345

Meter serial:
DX98765

Do not silently use the meter.

Report the inconsistency and allow the audit/control process to determine remediation.

---

## Meter Reading

The meter reading endpoint is used to write operating-hour values.

Production writes must be controlled.

Before writing:

1. validate asset identity
2. validate equipment
3. validate meter
4. validate source reading
5. validate source timestamp
6. evaluate business rule
7. determine decision
8. log decision
9. perform write only if authorized

---

## Idempotency

The integration should avoid unnecessary writes.

If:

OEM reading == Fracttal reading

Decision:

SKIP_EQUAL

No write should be performed.

The integration must not generate unnecessary duplicate readings merely because the synchronization job ran again.

---

## MyDevelon Rule

For MyDevelon:

MyDevelon is the source of truth for operating hours.

Rules:

OEM == Fracttal
→ SKIP_EQUAL

OEM > Fracttal and source recent
→ UPDATE

OEM < Fracttal and source recent
→ CORRECT

OEM source older than 48h
→ REVIEW_OLD_SOURCE

The 48-hour threshold concerns source freshness, not the numerical difference between meters.

---

## Timestamp Handling

Maintain two distinct concepts:

reading_datetime

and

retrieved_at

reading_datetime:
when the OEM measurement occurred.

retrieved_at:
when the integration retrieved the data.

Do not replace reading_datetime with the local execution time unless the source genuinely provides no measurement timestamp and the limitation is explicitly documented.

---

## SQL Integration

SQL Server stores integration state and audit information.

Relevant tables:

machinery

machine_meters

horometer_updates

telemetry_sync_config

Use SQL to maintain:

- asset mapping
- meter mapping
- telemetry configuration
- historical decisions
- synchronization history
- auditability

---

## telemetry_sync_config

Telemetry synchronization must be controlled independently from asset activity.

Do not use:

machinery.active

as a synonym for:

telemetry_sync_config.sync_enabled

These represent different concepts.

Example:

A machine may be active in Fracttal but temporarily disabled for telemetry synchronization.

That is valid.

---

## Production Writes

Writes must be explicit.

Before modifying Fracttal:

- validate the data
- validate the target meter
- validate the business rule
- support dry-run
- log the decision
- handle API errors
- never log credentials or tokens

Do not perform writes as an accidental side effect of an audit.

---

## Dry Run

The production process should support:

dry_run=True

When dry-run is enabled:

- perform all validations
- calculate the decision
- show the intended write
- do not modify Fracttal

Example:

Would update meter:
Equipment = DX12345
Current = 1200.4
Source = 1203.1
Decision = UPDATE

No write performed.

---

## Error Handling

Handle explicitly:

- authentication failures
- authorization failures
- HTTP errors
- timeout
- connection errors
- malformed JSON
- empty responses
- missing equipment
- missing meter
- ambiguous meter
- invalid meter
- source/target mismatch

Do not catch all exceptions and continue silently.

Bad:

try:
    ...
except:
    pass

Good:

- capture the error
- identify the asset
- identify the operation
- record the failure
- allow the process to continue only when safe

---

## Credentials

Credentials belong in:

.env

Never hardcode:

- client secrets
- passwords
- access tokens
- refresh tokens
- API keys

Never print secrets to logs.

---

## Multi-OEM

Fracttal integration should consume normalized telemetry.

The Fracttal layer should not need to understand:

- MyDevelon API structures
- KOMTRAX API structures
- CAT-specific API structures

OEM-specific transformations belong upstream.

Preferred flow:

OEM adapter
→ normalized telemetry
→ Fracttal integration

Not:

Fracttal integration
→ if MyDevelon
→ if Komtrax
→ if CAT

---

## Code Principles

Prefer:

- small functions
- explicit variables
- simple Python
- reusable existing helpers
- clear logging
- deterministic decisions

Avoid:

- unnecessary frameworks
- excessive abstraction
- speculative architecture
- unrelated refactoring
- machine-specific hacks

---

## Testing

Test at minimum:

1. valid equipment + valid meter
2. missing equipment
3. duplicate equipment
4. missing meter
5. multiple valid meters
6. NO UTILIZAR meter
7. meter serial mismatch
8. equal reading
9. higher reading
10. lower reading
11. old source
12. API failure
13. timeout
14. dry-run
15. real write
16. repeated synchronization

---

## Implementation Rule

Before changing the Fracttal integration:

1. inspect the current API helper
2. understand authentication
3. understand existing endpoint usage
4. understand current data structures
5. make the smallest robust change
6. test
7. report what changed

Do not rewrite the integration simply because a cleaner architecture can be imagined.

Correctness comes before elegance.