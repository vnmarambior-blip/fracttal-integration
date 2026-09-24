---
name: aemp-integration
description: Multi-OEM heavy-equipment telemetry integration using AEMP 2.0 / ISO 15143-3 as normalization reference. Use when adding OEM adapters, mapping OEM fields, or evolving the telemetry layer without rewriting the core integration.
---
# Skill: AEMP Integration

## Purpose

This skill defines the architecture and implementation rules for integrating heavy-equipment telematics from multiple OEMs using AEMP 2.0 / ISO 15143-3 as the common architectural reference where applicable.

The objective is to build a multi-OEM telemetry layer that can evolve without rewriting the core integration for every manufacturer.

---

## Core Principle

AEMP / ISO 15143-3 is a normalization reference.

It is NOT a guarantee that every OEM API:

- exposes the same endpoints
- exposes the same fields
- uses the same identifiers
- returns the same timestamp semantics
- provides the same data quality
- implements every standard capability identically

Always verify the actual OEM API.

---

## Intended Architecture

Preferred architecture:

OEM API
↓
OEM Adapter
↓
AEMP / ISO-aligned interpretation
↓
Normalized Telemetry Model
↓
SQL Server
↓
Fracttal
↓
Power BI

Examples:

MyDevelon
→ mydevelon.py
→ normalized telemetry

KOMTRAX
→ komtrax.py
→ normalized telemetry

CAT
→ cat.py
→ normalized telemetry

The common integration engine consumes normalized telemetry.

---

## Adapter Principle

Each OEM should have an adapter responsible for:

- authentication
- API communication
- OEM-specific endpoints
- OEM-specific field names
- OEM-specific transformations
- OEM-specific pagination
- OEM-specific errors
- source timestamps
- OEM identity

The adapter should NOT define the entire internal architecture.

---

## Normalized Model

The internal model should represent common telemetry concepts.

Conceptually:

TelemetryAsset

and:

TelemetryReading

A normalized asset may contain:

- source
- source_asset_id
- serial
- manufacturer
- model
- equipment_identifier
- metadata

A normalized reading may contain:

- source
- source_asset_id
- serial
- metric
- value
- unit
- reading_datetime
- retrieved_at
- quality
- source_metadata

The exact Python implementation should follow the existing project architecture.

Do not introduce unnecessary frameworks solely to implement this model.

---

## Identity

The preferred cross-system identity is:

OEM serial / PIN

For example:

MyDevelon:
PIN

KOMTRAX:
OEM serial

CAT:
machine serial number

The adapter must map the OEM-specific identity into:

normalized serial

Do not use OEM-specific EquipmentID as the universal identity unless explicitly required and documented.

---

## Standard vs OEM-Specific Data

Separate:

### Common standardized data

Examples:

- serial
- manufacturer
- model
- operating hours
- position
- timestamp
- location
- engine information where standardized

### OEM-specific data

Examples:

- proprietary fault codes
- proprietary health indicators
- OEM-specific machine states
- OEM-specific diagnostic parameters
- OEM-specific fields

Do not discard useful OEM-specific data merely because it does not fit the common model.

Preserve it in:

source_metadata

or another documented OEM-specific structure.

---

## AEMP Interpretation

When an OEM exposes an AEMP/ISO 15143-3 compatible endpoint:

1. identify the endpoint version
2. identify the actual fields returned
3. verify identifier semantics
4. verify timestamp semantics
5. verify units
6. verify pagination
7. verify authentication
8. map fields to the normalized model

Do not assume compliance from the endpoint name alone.

---

## MyDevelon

Current MyDevelon AEMP-related endpoint family:

/api/rest/aemp/2.0/

Relevant concepts include:

- Fleet
- Equipment
- MakeModelSerial
- CumulativeOperatingHours
- PIN
- EquipmentID
- timestamps

The actual response must be inspected before implementing mappings.

For MyDevelon:

PIN is the primary asset identity.

Operating hours are represented through the normalized telemetry model.

---

## Common Telemetry Model

The common model should allow the core system to process:

MyDevelon

KOMTRAX

CAT

Sennebogen

and future OEMs

without changing the core business logic for every new manufacturer.

The core engine should operate on concepts such as:

asset
serial
metric
value
unit
reading_datetime
retrieved_at
source
quality

---

## Avoid OEM Conditionals in Core Logic

Avoid:

if oem == "MYDEVELON":
    ...
elif oem == "KOMTRAX":
    ...
elif oem == "CAT":
    ...

inside the core synchronization engine.

Prefer:

adapter = get_adapter(oem)

reading = adapter.get_reading(asset)

normalized = normalize(reading)

result = process(normalized)

OEM-specific behavior belongs in the adapter.

---

## Timestamp Semantics

Every adapter must preserve the distinction between:

reading_datetime

and:

retrieved_at

reading_datetime:

when the OEM says the measurement occurred.

retrieved_at:

when the integration obtained the response.

If an OEM provides multiple timestamps:

document which one represents the actual measurement.

Do not silently choose one.

---

## Units

Normalize units where possible.

For operating hours:

preferred normalized unit:

HRS

The adapter must verify the OEM source unit.

Do not assume that a field named:

hours

always represents operating hours.

Document transformations where required.

---

## Data Quality

The AEMP integration layer must preserve source quality information.

Potential quality states include:

VALID
STALE
MISSING
INVALID
ESTIMATED
CORRECTED

Only use states that are actually implemented in the project.

Do not invent quality values simply to fill fields.

---

## Source Metadata

When useful, preserve OEM-specific evidence.

Example:

source_metadata = {
    OEM-specific fields
}

This allows the normalized layer to remain simple while retaining traceability.

Do not throw away fields that may later be required for:

- diagnostics
- auditing
- troubleshooting
- new mappings
- regulatory requirements

---

## SQL Integration

SQL Server should store normalized integration information and historical decisions.

Relevant structures include:

machinery
machine_meters
horometer_updates
telemetry_sync_config

The normalized layer should make it possible to trace:

OEM source
→ normalized reading
→ SQL asset
→ Fracttal equipment
→ Fracttal meter

---

## Fracttal Independence

The OEM adapter must not contain Fracttal-specific logic.

Bad:

mydevelon.py
→ directly updates Fracttal

Preferred:

mydevelon.py
→ normalized telemetry
→ common engine
→ Fracttal adapter/integration

This separation allows the same OEM source to feed other consumers later.

---

## Versioning

Track the version of relevant source standards and OEM APIs where useful.

Examples:

- AEMP 2.0
- ISO 15143-3
- OEM API version
- adapter version

Do not assume an API is immutable.

If an OEM changes:

- endpoint
- authentication
- field
- identifier
- timestamp
- pagination

the adapter should be updated without requiring a redesign of the entire integration.

---

## Testing New OEMs

For every new OEM adapter, test at least:

1. authentication
2. asset listing
3. serial extraction
4. model extraction
5. manufacturer extraction
6. operating-hour extraction
7. timestamp extraction
8. unit extraction
9. pagination
10. empty response
11. API error
12. timeout
13. duplicate asset
14. malformed asset
15. missing serial
16. stale source
17. normalization
18. SQL mapping
19. Fracttal mapping

---

## Mapping Documentation

Every adapter should document:

OEM field
→ normalized field

Example:

MyDevelon.PIN
→ TelemetryAsset.serial

MyDevelon.CumulativeOperatingHours
→ TelemetryReading.value

MyDevelon.timestamp
→ TelemetryReading.reading_datetime

Document transformations explicitly.

---

## Do Not Over-Normalize

The normalized model should contain common concepts.

Do not attempt to force every OEM-specific field into the common model.

The goal is:

common core + preserved OEM-specific information

not:

one gigantic universal schema.

---

## Implementation Strategy

When adding a new OEM:

1. inspect the API
2. identify authentication
3. identify asset endpoint
4. identify serial
5. identify operating hours
6. identify timestamp
7. identify units
8. identify pagination
9. implement adapter
10. normalize response
11. test independently
12. connect to SQL
13. connect to Fracttal
14. run audit
15. enable production synchronization only after validation

Do not start by modifying the entire system.

---

## Architectural Goal

The final system should behave like:

OEM 1 ─┐
OEM 2 ─┤
OEM 3 ─┤
OEM 4 ─┤
        ↓
   OEM Adapters
        ↓
Normalized Telemetry
        ↓
   SQL Control Layer
        ↓
   Fracttal Integration
        ↓
      Power BI

Adding an OEM should primarily require:

1. a new adapter
2. field mappings
3. tests
4. configuration

It should NOT require rewriting the synchronization engine.

---

## Design Philosophy

Use AEMP / ISO 15143-3 to create interoperability.

Use OEM adapters to handle reality.

Use SQL Server to maintain control and traceability.

Use Fracttal as the operational destination.

Use Power BI as the analytical consumer.

Do not confuse standardization with identical APIs.

The architecture must be standardized without pretending that OEM APIs are identical.