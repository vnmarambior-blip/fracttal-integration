# MyDevelon Fleet snapshot (hours) — referencia de integración

Fuente: documentación MyDevelon AEMP 2.0 (2026-09-23).

## Request

**GET**

```text
https://extapi.mydevelon.com/api/rest/aemp/2.0/Fleet/{pageNumber}
```

**Header**

```text
Authorization: Bearer <authorizationToken>
```

## Parámetros

| Variable   | Type | Example | Description                                              | Default               | In   | Required? |
|------------|------|---------|----------------------------------------------------------|-----------------------|------|-----------|
| pageNumber | long | 1       | Navegación por página (links current/previous/next/last) | 100 records por página | path | Required  |

## Respuesta

**Schema:** http://standards.iso.org/aemp/2.0/common.xsd

### Campos

| Field                    | Type     | Example                  | Description                                      |
|--------------------------|----------|--------------------------|--------------------------------------------------|
| EquipmentHeader          | object   | ---                      |                                                  |
| OEMName                  | string   | DEVELON                  | Fabricante                                       |
| Model                    | string   | DX85R-3                  | Modelo                                           |
| EquipmentID              | string   | CEAAV-001024             | ID único                                         |
| SerialNumber             | string   | CEAAV-001024             | Serial                                           |
| PIN                      | string   |                          | PIN asignado (= serial canónico)                 |
| Location                 | object   | ---                      |                                                  |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización Location                    |
| Latitude                 | double   | 42,573861                | Latitud                                          |
| Longitude                | double   | -90,709778               | Longitud                                         |
| CumulativeIdleHours      | object   | ---                      |                                                  |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización IdleHours                   |
| Hour                     | double   | 180,6                    | Total idle en horas (¡horas aquí, no minutos!)   |
| CumulativeOperatingHours | object   | ---                      |                                                  |
| datetime                 | datetime | 2017-03-24T09:01:00.000Z | Última actualización OperatingHours              |
| Hour                     | double   | 428,7                    | Total horas operativas (= horómetro)             |
| EngineStatus             | object   | ---                      |                                                  |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización                             |
| EngineNumber             | string   |                          |                                                  |
| Running                  | boolean  | true                     |                                                  |
| FuelUsed                 | object   | ---                      |                                                  |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización FuelUsed                    |
| FuelUnits                | string   | litre                    |                                                  |
| FuelConsumed             | long     | 48                       | Combustible a la fecha                           |
| FuelRemaining            | object   | ---                      |                                                  |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización FuelRemaining               |
| Percent                  | double   | 48,8                     | % estanque                                       |
| FuelTankCapacityUnits    | string   | litre                    | Unidad de capacidad                              |
| FuelTankCapacity         | long     |                          | Capacidad del estanque                           |

## Notas de integración

- Difiere del endpoint `/minutes` **solo** en `CumulativeIdleHours`:
  aquí `Hour` (horas), allá `minutes` (minutos). El fetch vivo usa
  `/Fleet/1` (`FLEET_URL` en `mydevelon.py`); el modo archivo usa el
  fixture `fixtures/mydevelon_fleet_minutes.xml` (formato minutes); no mezclar fuentes.
- Lo consumido por el sync es idéntico: `PIN`, `Hour` de operating
  hours y su `@datetime`.
- Namespace: `http://standards.iso.org/iso/15143/-3`
  (`AEMP_NAMESPACE` único en `mydevelon.py`).

## Related Skills

- **aemp-integration** — parser AEMP 2.0 ISO 15143-3, namespace `http://standards.iso.org/iso/15143/-3`
- **telemetry-audit** — validar `CumulativeOperatingHours`/`Hour` y `@datetime`
- **data-quality** — aislar `Hour` vacío/no-numérico por equipo (Regla 8)
- **fracttal-integration** — mapeo `PIN`→`serial`, `EquipmentID`→`code`
