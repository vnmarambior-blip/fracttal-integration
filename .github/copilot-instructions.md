# Transmaco - Fracttal Integration

## Project purpose

This project integrates heavy machinery telematics from different OEM platforms
with Fracttal ONE.

Main objective:

OEM telematics
→ normalize and validate data
→ SQL Server
→ Fracttal
→ Power BI

Current OEM sources include:
- MyDevelon / Develon
- KOMTRAX / Komatsu
- Sennebogen

The architecture must support multiple OEMs.
Do not design the system around a single manufacturer.

---

## Architecture

The preferred architecture is:

OEM / Telematics
→ AEMP 2.0 / ISO 15143-3 when applicable
→ Python ETL / OEM adapters
→ normalized telemetry model
→ SQL Server
→ Fracttal
→ Power BI

AEMP / ISO 15143-3 should be used as a normalization reference
where the OEM actually provides standard-compatible data.

Do not assume that every OEM endpoint or field is standardized.

OEM-specific logic must remain inside the corresponding adapter.

---

## Asset identity

The primary identity used to match telematics equipment with Transmaco
assets is the machine serial / PIN.

For MyDevelon:

MyDevelon PIN
→ machinery.serial

Do NOT match MyDevelon equipment primarily by EquipmentID or model.

Always validate:

OEM asset
→ serial/PIN
→ Transmaco machinery
→ Fracttal equipment
→ Fracttal meter

before writing telemetry.

---

## MyDevelon business rule

For Develon operating hours:

MyDevelon is the source of truth.

If MyDevelon and Fracttal have the same value:

SKIP_EQUAL

If MyDevelon is greater than Fracttal and the source reading is recent:

UPDATE

If MyDevelon is lower than Fracttal and the source reading is recent:

CORRECT

Do not reject a downward correction simply because the value is lower.

If the MyDevelon reading is older than 48 hours:

REVIEW_OLD_SOURCE

The 48-hour rule applies to source freshness,
NOT to the size of the hourmeter difference.

Do not create machine-specific exceptions to solve data quality problems.

---

## Source timestamps

Always distinguish:

reading_datetime
= timestamp when the OEM measurement was actually taken

retrieved_at
= timestamp when our integration retrieved the data

Do not use retrieval time as the measurement time.

---

## Fracttal

Fracttal is the operational destination for telemetry.

SQL Server is the integration repository and control/audit layer.

Important Fracttal concepts:

Equipment:
GET /api/items/

Equipment type:
item_type = 2

Equipment serial:
field_4

Equipment code:
code

Equipment name:
field_1

Manufacturer:
field_2

Model:
field_3

Meters:
GET /api/meters/

Hourmeters normally use:

units_code = HRS
is_counter = true

Never write to meters whose description contains:

NO UTILIZAR

Before writing a meter reading, validate that the meter belongs
to the correct equipment.

Fracttal pagination uses:

start

not offset.

---

## Database

The SQL Server database is the integration control layer.

Current machinery table contains:

id
serial
equipment_code
name
manufacturer
model
active
created_at
updated_at
asset_type
asset_group_1
asset_group_2

Important:

The machinery table represents Fracttal/source asset information.

Integration enablement must NOT be controlled by overwriting
the machinery.active field.

Integration configuration must remain separate.

---

## Telemetry configuration

Telemetry synchronization state must be independent from
the Fracttal asset active state.

Do not let a Fracttal → SQL synchronization overwrite
local telemetry integration configuration.

Use telemetry_sync_config to determine whether an asset
is enabled for telemetry synchronization.

---

## Data quality

The system must detect and report:

- missing serials
- duplicate serials
- duplicate equipment codes
- missing hourmeters
- invalid hourmeters
- "NO UTILIZAR" meters
- meter serial mismatches
- asset/meter mismatches
- stale OEM readings
- OEM assets without Fracttal matches
- Fracttal assets without OEM matches
- inactive telemetry configuration
- suspicious data corrections

Do not silently ignore data-quality problems.

Prefer generic validation rules over machine-specific exceptions.

---

## Audit rules

Audit scripts must be READ ONLY.

An audit must never modify Fracttal.

Expected flow:

source
→ asset match
→ serial validation
→ timestamp validation
→ source freshness
→ Fracttal meter validation
→ value comparison
→ decision

Possible decisions include:

UPDATE
CORRECT
SKIP_EQUAL
REVIEW_OLD_SOURCE
REVIEW_SOURCE_DATE
NO_VALID_METER
NO_MATCH_SERIAL
ERROR

---

## Production writes

Do not perform production writes automatically unless:

1. The source asset has been correctly matched.
2. The serial/PIN has been validated.
3. The Fracttal equipment has been validated.
4. The correct hourmeter has been identified.
5. The meter is valid.
6. The source reading timestamp is valid.
7. The business rule allows the update.
8. The operation is auditable.

Never modify or delete historical "NO UTILIZAR" meters.

---

## Coding principles

Use simple, readable Python.

Do not over-engineer.

Prefer small functions with clear responsibilities.

Do not introduce frameworks unless there is a concrete reason.

Keep credentials in .env.

Never hardcode API credentials.

Before modifying existing code:

1. Understand the current flow.
2. Identify dependencies.
3. Identify data-model impacts.
4. Identify business-rule impacts.
5. Implement the smallest robust change.
6. Test it.
7. Report what changed.

Do not rewrite working code unnecessarily.

---

## Current development philosophy

The objective is not to create perfect software immediately.

The objective is to make the data flow visible, auditable and reliable.

When investigating problems, prioritize:

root cause
over
machine-specific workaround.

Remember:

"NO NECESITAMOS PROCESOS PERFECTOS.
NECESITAMOS SABER DÓNDE SE ROMPE EL FLUJO."