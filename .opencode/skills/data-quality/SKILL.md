---
name: data-quality
description: Identify, classify, investigate, and report data-quality problems across OEM telemetry, SQL Server, and Fracttal. Use when facing identity, mapping, meter, timestamp, value, or configuration inconsistencies.
---
# Skill: Data Quality

## Purpose

This skill defines how to identify, classify, investigate, and report data-quality problems across:

OEM / Telematics
SQL Server
Fracttal

The objective is not to hide inconsistencies.

The objective is to make inconsistencies visible, measurable, traceable, and actionable.

---

## Core Principle

A data-quality problem is not an exception to be hidden.

It is evidence that the process or data flow has a weakness.

Do not solve data-quality problems with hardcoded machine-specific exceptions unless the exception is formally documented and justified.

---

## Scope

Data-quality analysis includes:

- identity
- serial numbers
- equipment mapping
- meters
- meter serials
- timestamps
- hourmeter values
- missing data
- duplicate data
- stale data
- conflicting data
- configuration
- source reliability
- API responses
- historical synchronization

---

## Quality Dimensions

Evaluate at least:

### Completeness

Is the required information present?

Examples:

- missing serial
- missing source reading
- missing timestamp
- missing Fracttal equipment
- missing meter
- missing configuration

### Accuracy

Does the value represent the actual source?

Examples:

- incorrect meter
- wrong serial
- incorrect hourmeter
- stale source

### Consistency

Do systems agree where they should?

Examples:

- OEM serial != SQL serial
- SQL serial != Fracttal serial
- equipment serial != meter serial
- conflicting active states

### Uniqueness

Does one asset map to exactly one intended record?

Examples:

- duplicate serials
- multiple equipment matches
- multiple valid hourmeters

### Timeliness

Is the data recent enough for the business process?

Example:

OEM reading older than 48h.

### Validity

Does the data comply with expected rules?

Examples:

- meter units != HRS
- is_counter = false
- NO UTILIZAR meter
- invalid timestamp
- malformed serial

---

## Asset Identity

The preferred identity is:

OEM serial / PIN

Check consistency across:

OEM
→ SQL
→ Fracttal

Example:

OEM:
PIN = DX12345

SQL:
serial = DX12345

Fracttal:
field_4 = DX12345

This represents consistent identity.

If one system differs:

flag the discrepancy.

Do not automatically modify the other systems.

---

## Duplicate Detection

Detect duplicates in:

- OEM serial
- SQL machinery.serial
- Fracttal equipment serial
- machine-to-meter relationships
- telemetry configuration

Duplicates should be classified explicitly.

Example:

DUPLICATE_SERIAL

Do not arbitrarily select one record as the correct record.

---

## Meter Quality

A valid operating-hour meter should generally satisfy:

- units_code = HRS
- is_counter = true
- correct equipment
- description does not contain NO UTILIZAR
- serial consistent with equipment where available

Possible quality classifications:

VALID_METER
NO_VALID_METER
MULTIPLE_VALID_METERS
METER_SERIAL_MISMATCH
METER_MARKED_NO_UTILIZAR
METER_WRONG_UNIT
METER_NOT_COUNTER

---

## NO UTILIZAR

A meter marked:

NO UTILIZAR

must be treated as invalid for synchronization.

Never:

- update it
- delete it
- reactivate it
- select it as fallback

The presence of such a meter may indicate a historical or configuration issue.

Report it.

---

## Missing Data

Do not convert missing data into artificial values.

Examples:

Missing source timestamp:

Do not invent one.

Missing serial:

Do not derive it from model/name unless there is a documented deterministic mapping.

Missing meter:

Do not create one automatically unless the production process explicitly authorizes meter creation.

---

## Timestamp Quality

Always distinguish:

reading_datetime

from:

retrieved_at

Evaluate:

- presence
- format
- timezone
- future timestamps
- stale timestamps
- impossible dates

The source measurement timestamp should be used for freshness when available.

---

## Source Freshness

For the current MyDevelon operating-hour rule:

<= 48h:

recent

> 48h:

old

Classify old readings separately.

Do not mix:

data freshness

with:

hourmeter difference.

---

## Cross-System Reconciliation

For each asset, compare:

### Identity

OEM serial
vs
SQL serial
vs
Fracttal serial

### Hourmeter

OEM value
vs
Fracttal value

### Timestamp

OEM reading_datetime
vs
retrieved_at

### Meter

SQL mapped meter
vs
Fracttal actual meter

### Configuration

telemetry_sync_config
vs
expected synchronization behavior

---

## Conflict Classification

Use explicit classifications.

Examples:

IDENTITY_MISMATCH
DUPLICATE_IDENTITY
MISSING_SOURCE
MISSING_EQUIPMENT
MISSING_METER
INVALID_METER
MULTIPLE_METERS
METER_SERIAL_MISMATCH
STALE_SOURCE
TIMESTAMP_MISSING
TIMESTAMP_INVALID
SOURCE_TARGET_CONFLICT
CONFIG_MISSING
SYNC_DISABLED
API_ERROR

Avoid generic:

ERROR

when a more useful classification exists.

Use ERROR when the condition cannot be meaningfully classified.

---

## Severity

If severity is required, use an explicit operational severity rather than subjective language.

Suggested levels:

### BLOCKING

The integration must not continue.

Examples:

- unknown asset identity
- ambiguous meter
- missing required source data

### HIGH

The integration can technically continue, but the data should not be trusted without review.

Examples:

- serial mismatch
- conflicting equipment
- invalid meter

### MEDIUM

The process can continue but data quality should be monitored.

Examples:

- stale source
- missing optional field

### LOW

Informational or non-critical issue.

Examples:

- metadata mismatch that does not affect identity

Severity must be documented and consistently applied.

---

## Evidence

Every quality issue should have evidence.

Recommended fields:

- issue_id
- detected_at
- OEM
- asset_serial
- source_value
- SQL_value
- Fracttal_value
- affected_record
- issue_type
- severity
- evidence
- recommended_action
- status

Do not report:

"something is wrong"

when the evidence can be shown.

Prefer:

"OEM PIN DX12345 differs from Fracttal field_4 DX12354."

---

## Remediation

The data-quality skill identifies problems.

It should distinguish between:

### Detection

What is wrong?

### Diagnosis

Why is it likely wrong?

### Remediation

What should be changed?

### Verification

How do we confirm the correction?

Do not automatically modify production data unless the task explicitly belongs to a controlled write process.

---

## Machine-Specific Exceptions

Avoid:

if serial == "ABC123":
    ignore_error()

This creates hidden technical debt.

If an exception is truly necessary:

1. document the reason
2. identify the owner
3. define expiration/review criteria
4. make it configurable
5. log when it is applied

---

## SQL Role

SQL Server should provide the historical and control context necessary to understand quality issues.

Relevant tables:

machinery
machine_meters
horometer_updates
telemetry_sync_config

Use SQL history to distinguish:

- new issue
- recurring issue
- previously corrected issue
- unresolved issue

---

## Data Quality Metrics

When useful, calculate:

- % assets with valid serial
- % assets with unique serial
- % assets with valid meter
- % assets with matching meter serial
- % assets with recent telemetry
- % assets with successful mapping
- % assets requiring review
- % assets with synchronization disabled
- number of duplicate records
- number of stale sources
- number of identity conflicts

Metrics must be reproducible from defined data.

---

## Testing

Test:

1. valid asset
2. missing serial
3. duplicate serial
4. serial mismatch
5. missing equipment
6. missing meter
7. multiple meters
8. NO UTILIZAR meter
9. wrong meter unit
10. meter serial mismatch
11. stale source
12. missing timestamp
13. invalid timestamp
14. conflicting hourmeter
15. missing telemetry configuration
16. disabled synchronization

---

## Output Requirement

A useful data-quality result should answer:

1. What is wrong?
2. Where is it wrong?
3. What evidence proves it?
4. What system is affected?
5. Does it block synchronization?
6. What is the likely cause?
7. What action should be taken?
8. How will the correction be verified?

The goal is not to make the dataset look clean.

The goal is to know whether the dataset can be trusted.