---
name: telemetry-audit
description: Audit OEM telematics against Transmaco SQL Server and Fracttal without modifying production data. Use when investigating hourmeters, asset matching, telemetry freshness, meter validity, synchronization decisions, or OEM-to-Fracttal inconsistencies.
---

# Telemetry Audit

## Purpose

Perform a controlled, read-only audit of OEM telemetry against the
Transmaco asset database and Fracttal.

The audit must identify:

- whether the OEM asset matches a Transmaco asset
- whether the Fracttal equipment is correctly identified
- whether the correct meter is being used
- whether the OEM reading is current
- whether the reading should be accepted
- whether the value should be updated or corrected
- whether the case requires review
- whether a data-quality problem exists

The audit must not modify production data.

---

# Core principle

The objective of the audit is:

source
→ identify asset
→ validate identity
→ validate source timestamp
→ identify Fracttal equipment
→ identify valid meter
→ compare values
→ apply business rule
→ produce an auditable decision

Do not skip validation steps merely because an asset appears obvious.

---

# Read-only rule

Telemetry audits are READ ONLY.

During an audit:

DO NOT:

- update Fracttal
- delete Fracttal meters
- modify Fracttal equipment
- modify SQL production records
- modify telemetry configuration
- create or delete meters
- silently correct source data

The audit may read:

- OEM APIs
- SQL Server
- Fracttal APIs
- local configuration
- logs
- existing audit/history tables

Any production write must be performed by a separate controlled process.

---

# Asset identity

The primary identity of an OEM asset is its stable serial number
or OEM PIN.

For MyDevelon:

MyDevelon PIN
→ machinery.serial

Do not use the following as the primary identity:

- EquipmentID
- model
- equipment name
- equipment code
- position
- description

These values may be used as supporting evidence but not as the
primary identity when a reliable serial/PIN exists.

---

# Identity validation

For every asset being audited:

1. Extract the OEM serial/PIN.
2. Normalize the value if necessary.
3. Search SQL Server for the corresponding serial.
4. Confirm the expected Transmaco/Fracttal asset.
5. Confirm the Fracttal equipment.
6. Confirm the meter associated with that equipment.

Expected relationship:

OEM PIN / serial
→ machinery.serial
→ Fracttal equipment
→ Fracttal meter

If the serial does not uniquely identify an asset:

NO_MATCH_SERIAL

or

ERROR

Do not guess.

---

# OEM source timestamp

Always distinguish:

reading_datetime
= time when the OEM measurement was actually recorded

retrieved_at
= time when the integration retrieved the data

The audit must use reading_datetime to determine source freshness.

Do not substitute local execution time for the OEM measurement time.

---

# Source freshness

For the current MyDevelon business rule:

A source reading older than 48 hours is considered stale.

If:

current_time - reading_datetime > 48 hours

classify:

REVIEW_OLD_SOURCE

The 48-hour rule applies only to source freshness.

It does NOT define the maximum acceptable difference between
the OEM hourmeter and the Fracttal hourmeter.

A large hourmeter difference must not automatically be treated
as a stale-source condition.

---

# Fracttal equipment validation

When validating the Fracttal equipment:

Use the Fracttal item endpoint.

Equipment identity must be confirmed using stable fields,
especially the serial.

Do not rely solely on:

- equipment name
- model
- description
- equipment code

When multiple Fracttal assets could match the OEM asset:

REVIEW

Do not select an arbitrary match.

---

# Fracttal meter validation

The correct meter must be identified before comparing or proposing
an hourmeter update.

A valid operating-hour meter should satisfy:

units_code = HRS

and:

is_counter = true

The meter description must NOT contain:

NO UTILIZAR

Preferred validation:

meter serial == equipment serial

If the meter serial matches the equipment serial, this is strong
evidence of correct association.

If several valid meters exist and no unique match can be established:

NO_VALID_METER

or

REVIEW

Do not guess.

---

# "NO UTILIZAR" meters

Meters marked:

NO UTILIZAR

must never be selected for synchronization.

Never:

- update them
- delete them
- rename them
- reactivate them
- use them as the comparison source

The existence of a valid replacement meter must be handled separately.

---

# MyDevelon business rule

For Develon operating hours:

MyDevelon is the source of truth.

Let:

OEM = MyDevelon hourmeter
FRACTTAL = current valid Fracttal hourmeter

If:

OEM == FRACTTAL

Decision:

SKIP_EQUAL

If:

OEM > FRACTTAL

and the OEM reading is recent:

Decision:

UPDATE

If:

OEM < FRACTTAL

and the OEM reading is recent:

Decision:

CORRECT

Do NOT reject a lower value merely because it is lower.

If the OEM source is older than 48 hours:

Decision:

REVIEW_OLD_SOURCE

This rule concerns source freshness, not value difference.

---

# Decision hierarchy

Apply the following order:

1. Validate source availability.
2. Validate OEM timestamp.
3. Validate OEM serial/PIN.
4. Match the asset.
5. Validate Fracttal equipment.
6. Validate Fracttal meter.
7. Validate meter usability.
8. Validate source freshness.
9. Compare hourmeter values.
10. Apply the business rule.
11. Produce an audit decision.
12. Record evidence.

Do not compare hourmeters before validating the identity and meter.

---

# Standard audit decisions

Use explicit decision codes.

## SKIP_EQUAL

OEM and Fracttal values are equal.

No synchronization is required.

---

## UPDATE

The OEM value is greater than the Fracttal value and the source
reading is recent.

The case is eligible for a forward synchronization.

The audit itself must NOT perform the write.

---

## CORRECT

The OEM value is lower than the Fracttal value and the source
reading is recent.

Because MyDevelon is the source of truth, the Fracttal value should
be corrected by the controlled write process.

The audit itself must NOT perform the write.

---

## REVIEW_OLD_SOURCE

The OEM reading is older than 48 hours.

Do not automatically synchronize.

---

## REVIEW_SOURCE_DATE

The source timestamp is missing, malformed, ambiguous, or otherwise
cannot be trusted.

---

## NO_MATCH_SERIAL

No unique Transmaco/Fracttal asset can be identified using the
OEM serial/PIN.

---

## NO_VALID_METER

No valid operating-hour meter can be identified.

Examples:

- no HRS meter
- meter is not a counter
- all candidate meters are marked NO UTILIZAR
- serial association is inconsistent
- multiple meters exist without a unique valid selection

---

## ERROR

The audit cannot safely determine a decision because of a technical
or data-integrity failure.

---

# Audit output

Every audited asset should produce an explicit result containing,
when available:

- OEM source
- OEM asset identifier
- OEM PIN/serial
- OEM model
- OEM EquipmentID
- reading_datetime
- retrieved_at
- OEM hourmeter
- SQL machinery ID
- SQL machinery serial
- Fracttal equipment ID
- Fracttal equipment code
- Fracttal equipment serial
- Fracttal meter ID
- Fracttal meter description
- Fracttal meter serial
- Fracttal hourmeter
- source age
- difference
- decision
- reason
- error/review details

Do not hide failed matches or validation errors.

---

# Evidence

The audit result must explain WHY a decision was produced.

Bad:

DECISION = UPDATE

Good:

DECISION = UPDATE

Reason:
MyDevelon reading is 4,812.3 HRS and the valid Fracttal meter
reads 4,799.1 HRS. The OEM reading was captured 6 hours ago.
The OEM PIN matches machinery.serial and the selected meter
belongs to the corresponding Fracttal equipment.

The audit should provide enough evidence for another engineer
to reproduce the decision.

---

# SQL Server usage

SQL Server is the integration control and audit layer.

Relevant structures include:

machinery
machine_meters
horometer_updates
telemetry_sync_config

When auditing:

- use machinery for asset identity
- use machine_meters for known meter relationships
- use telemetry_sync_config for synchronization configuration
- use horometer_updates for historical evidence

Do not assume SQL state is correct merely because it exists.

If SQL and Fracttal disagree, report the inconsistency.

---

# telemetry_sync_config

Telemetry synchronization configuration is independent from:

machinery.active

Never infer telemetry synchronization permission from
machinery.active.

Check telemetry_sync_config when the audit needs to determine
whether the asset is configured for synchronization.

Relevant concepts include:

- OEM source
- sync_enabled
- action policy
- comparison basis
- reason
- notes

If synchronization configuration is missing or ambiguous:

REVIEW

Do not invent a configuration.

---

# Audit vs production synchronization

The audit answers:

"What SHOULD happen?"

The production synchronization process answers:

"Perform the approved action."

Therefore:

Audit:
READ ONLY

Production synchronization:
controlled WRITE

Never combine the two implicitly.

---

# Error handling

Do not silently catch errors and continue as if the asset were valid.

Examples:

Bad:

try:
    ...
except:
    pass

Preferred:

try:
    ...
except Exception as error:
    return ERROR with explicit reason

Errors must remain visible.

---

# Multi-OEM compatibility

The audit architecture must not be coupled exclusively to MyDevelon.

The common audit flow should operate on normalized telemetry concepts:

- source
- asset identifier
- serial
- reading_datetime
- operating_hours

OEM-specific extraction belongs inside the corresponding adapter.

Avoid implementing OEM-specific conditions throughout the audit logic.

Preferred:

OEM adapter
→ normalized telemetry
→ common audit engine

Not:

common audit engine
→ if MyDevelon
→ if KOMTRAX
→ if Sennebogen
→ etc.

---

# Data-quality philosophy

Never hide a data-quality problem with a machine-specific exception.

Bad:

if machine == "MH40":
    use_meter("12345")

Good:

if meter.serial == equipment.serial:
    select_meter()

If the relationship cannot be validated:

REVIEW

The purpose of the audit is to expose where the flow breaks.

---

# Dry-run behavior

If a production synchronization function supports:

dry_run=True

use dry-run mode whenever testing a proposed synchronization.

A dry run must:

- execute matching
- execute validation
- calculate the proposed decision
- display the proposed change
- NOT write to Fracttal

Never disable validation simply because dry-run is enabled.

---

# Testing requirements

Before modifying production synchronization logic:

1. Test equal values.
2. Test OEM > Fracttal.
3. Test OEM < Fracttal.
4. Test stale source.
5. Test missing timestamp.
6. Test missing serial.
7. Test duplicate serial.
8. Test missing meter.
9. Test NO UTILIZAR meter.
10. Test mismatched meter serial.
11. Test multiple candidate meters.
12. Test missing telemetry configuration.
13. Test dry-run.
14. Test API failure.
15. Test SQL failure.

No single happy-path test is sufficient.

---

# Required behavior when asked to audit

When the user asks to audit telemetry:

1. Inspect the existing implementation before creating new code.
2. Identify the current source adapter.
3. Identify the current SQL queries.
4. Identify the Fracttal matching logic.
5. Identify the meter-selection logic.
6. Run or inspect the audit process.
7. Report inconsistencies.
8. Do not modify production data.
9. Separate:
   - confirmed facts
   - inferred conditions
   - unresolved issues
10. Recommend the smallest robust correction.

Do not rewrite the entire integration merely because the audit
finds one defect.

---

# Guiding principle

The audit exists to answer:

"Where does the telemetry flow break?"

not:

"How can we force every asset to synchronize?"

Reliability and traceability are more important than synchronization
coverage.