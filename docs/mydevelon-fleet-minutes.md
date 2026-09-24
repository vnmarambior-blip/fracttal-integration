# MyDevelon Fleet snapshot (minutes) — referencia de integración

Fuente: documentación MyDevelon AEMP 2.0 (2026-09-23).
Última verificación: en uso productivo (`fixtures/mydevelon_fleet_minutes.xml`).

## Request

**GET**

```text
https://extapi.mydevelon.com/api/rest/aemp/2.0/Fleet/minutes/{pageNumber}
```

**Header**

```text
Authorization: Bearer <authorizationToken>
```

## Parámetros

| Variable   | Type | Example | Description                                                   | Default              | In   | Required? |
|------------|------|---------|---------------------------------------------------------------|----------------------|------|-----------|
| pageNumber | long | 1       | Navegación por página (links current/previous/next/last)      | 100 records por página | path | Required  |

## Respuesta

**Schema:** http://standards.iso.org/aemp/2.0/common.xsd

Namespace observado en producción: `http://standards.iso.org/iso/15143/-3`
(ver `AEMP_NAMESPACE` único en `mydevelon.py`; Komtrax usa otro namespace,
parsear por nombre local si se unifica).

### Campos

| Field                    | Type     | Example                  | Description                                         |
|--------------------------|----------|--------------------------|-----------------------------------------------------|
| EquipmentHeader          | object   | ---                      |                                                     |
| OEMName                  | string   | DEVELON                  | Fabricante                                          |
| Model                    | string   | DX85R-3                  | Modelo                                              |
| EquipmentID              | string   | CEAAV-001024             | ID único                                            |
| SerialNumber             | string   | CEAAV-001024             | Serial                                              |
| PIN                      | string   |                          | PIN asignado (= `serial` canónico del sync)         |
| Location                 | object   | ---                      |                                                     |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización Location                       |
| Latitude                 | double   | 42,573861                | Latitud                                             |
| Longitude                | double   | -90,709778               | Longitud                                            |
| CumulativeIdleHours      | object   | ---                      |                                                     |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización IdleHours                      |
| minutes                  | double   | 180,6                    | Total idle (¡en minutos, no horas!)                 |
| CumulativeOperatingHours | object   | ---                      |                                                     |
| datetime                 | datetime | 2017-03-24T09:01:00.000Z | Última actualización OperatingHours                 |
| Hour                     | double   | 428,7                    | Total horas operativas (= horómetro)                |
| EngineStatus             | object   | ---                      |                                                     |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización                                |
| EngineNumber             | string   |                          |                                                     |
| Running                  | boolean  | true                     |                                                     |
| FuelUsed                 | object   | ---                      |                                                     |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización FuelUsed                       |
| FuelUnits                | string   | litre                    |                                                     |
| FuelConsumed             | long     | 48                       | Combustible consumido a la fecha                    |
| FuelRemaining            | object   | ---                      |                                                     |
| datetime                 | datetime | 2017-03-22T18:35:45.000Z | Última actualización FuelRemaining                  |
| Percent                  | double   | 48,8                     | % estanque con combustible                          |
| FuelTankCapacityUnits    | string   | litre                    | Unidad de capacidad                                 |
| FuelTankCapacity         | long     |                          | Capacidad del estanque                              |

## Notas de integración

- Lo único que consume el sync: `PIN` (= serial canónico),
  `CumulativeOperatingHours/Hour` (= horómetro) y su `@datetime`
  (= `reading_datetime`). Resto fuera de alcance.
- **Ojo unidades**: este endpoint trae `CumulativeIdleHours/minutes`
  en **minutos**; `Hour` de operating hours en horas. No mezclar.
- `Hour` vacío/no-numérico → el parser lo aísla por equipo (R8), no
  aborta la flota.
- Cuota observada: ~1 consulta cada 15 min (guardián en `mydevelon.py`,
  `QuotaExceededError`, intervalo configurable).
- Auth: Bearer con token cacheado (`get_cached_token`).
