# Komtrax ISO API — referencia de integración

Fuente: manual Komtrax ISO API (FAQ + secciones de endpoints, data items y
token) + probes reales contra el API.
Última verificación: token OK (200), flota pendiente por cuota 429.

## Estándar

- La API cumple **ISO15143-3 (AEMP)**. Parser actual reusable.
- Para el detalle de cada ítem, el manual remite al documento ISO15143-3
  emitido por ISO y a P8 ("Data items supported by Komtrax ISO API").

## Autenticación

- Servidor de certificación: `POST https://isoapi.komtrax.komatsu/provider/token`
  (distinto host-path que los datos; solo POST, nunca GET).
- OAuth2 `grant_type=password` + `username` + `password` en el **body** del
  request → 200 con `access_token`. (`client_credentials` → 400
  `unauthorized_client`.)
- ID y password **deben ir URL-encoded**; no usar texto plano.
- No enviar credenciales por parámetro de URL (query string).
- Respuesta 200 (JSON):
  `access_token`, `token_type: bearer`, `expires_in: 7199` (≈ 2 horas).
- Uso: header `Authorization: Bearer <token>` + request a la API con GET.
- Credenciales: `KOMTRAX_CLIENT_ID` / `KOMTRAX_CLIENT_SECRET` (= username /
  password del subscription). Ya configuradas en `.env` (verificado: SET).
- Token expirado → renovar y reintentar (401).

## Endpoints de datos

- Base: `https://isoapi.komtrax.komatsu/provider/v1`
- SubscriberID propio: `385177` (¡6 dígitos aunque el manual dice 5!).
- Snapshot todas (último valor de todas las máquinas propias):
  `{Host}/{SubscriberID}/Fleet/{PageNumber}` (100/página, con links
  current/previous/next/last — recorrer páginas).
- Snapshot una máquina:
  `{Host}/{SubscriberID}/Fleet/Equipment/MakeModelSerial/{MakeCode}/{Model}/{Serial}`
  con `MakeCode = 0001` siempre para Komatsu.
- Time Series por máquina y por ítem con `{StartDate}/{EndDate}` (YYYY-MM-DD,
  UTC). Probado: NO necesario para horómetros (snapshot basta).

### Parámetros (manual)

| Parámetro | Ejemplo | Nota |
|---|---|---|
| HostURI | `https://isoapi.komtrax.komatsu/provider/v1` | Host URI de la API |
| SubscriberID | `12345` | Subscription ID, números de 5 dígitos |
| PageNumber | `1` | Páginas de máximo 100 máquinas |
| MakeCode | `0001` | Código Komatsu |
| Model | `PC200-10` | Modelo – tipo de máquina |
| Serial | `A12345` | Número de serie |
| DataItem | `Locations` | Ítems de datos (ver catálogo) |
| StartDate | `2022-01-01` | Inicio, YYYY-MM-DD UTC |
| EndDate | `2022-01-01` | Fin, YYYY-MM-DD UTC |

## Catálogo de data items (manual)

**Los ítems disponibles difieren según el equipo**: una máquina puede venir
sin algunos ítems (p. ej. sin `CumulativeOperatingHours`).

| Ítem | Elemento | Contenido |
|---|---|---|
| Header | `EquipmentHeader` | `OEMName`, `Model`, `EquipmentID` (= Customer Machine No. de CFM), `SerialNumber` |
| Ubicación | `Locations` | `datetime`, `Latitude`, `Longitude` |
| Horas acumuladas (SMR) | `CumulativeOperatingHours` | `datetime`, `Hour` |
| Combustible acumulado | `CumulativeFuelUsed` | `datetime`, `FuelUnits`, `FuelConsumed` |
| Combustible 24h | `FuelUsedInThePreceding24Hours` | `datetime`, `FuelUnits`, `FuelConsumed` |
| Distancia acumulada | `Distance` | `datetime`, `OdometerUnits`, `Odometer` |
| Combustible restante | `FuelRemainingRatio` | `datetime`, `Percent` |
| DEF restante | `DEFRemainingRatio` | `datetime`, `Percent` |
| Velocidad pico diaria | `PeakDailySpeed` | `datetime`, `SpeedUnits`, `Speed` |
| Carga acumulada | `CumulativePayloadTotals` | `datetime`, `weightUom`, `weight` |
| Ralentí acumulado | `CumulativeNonProductiveIdleHours` | `datetime`, `Hour` (ojo: nombre distinto a MyDevelon `CumulativeIdleHours`) |
| Fallas | `Faults` | `CodeIdentifier`, `CodeDescription`, `CodeSeverity`, `CodeSource`, `datetime` |

## Formato

- Respuesta XML o JSON según `Accept` → nuestro GET Fleet envía
  `Accept: application/xml`.
- Fechas UTC ISO8601 `YYYY-MM-DDThh:mm:ssZ` (el parser ya convierte `Z`).
- `EquipmentID` = Customer Machine No. registrado en CFM por el cliente
  (clave de cruce identidad).

## Retención y frescura (manual + probes)

- API conserva **mes actual + 1 anterior**. CFM guarda todos los mensuales
  pasados + últimos 15 meses de diarios.
- La API puede responder **sin datos** aunque CFM los muestre (fuera de
  retención).
- Delay CFM→API: el SMR puede venir atrasado vs la web → esperar algunos
  `WRITE_AMBIGUOUS`, es normal. Regla temporal + verificación lo cubren.
- Intervalo de actualización: el manual remite a la hoja de spec (en
  preparación); asumir delay CFM→API.

## Errores HTTP (manual)

| Código | Significado | Acción |
|---|---|---|
| 400 | request incorrecto (fechas, formato) | corregir request |
| 401 | token malo/expirado (2h) | renovar token y 1 reintento |
| 403 | mantenimiento Komatsu | esperar |
| 404 | URL mala / máquina inexistente / sin datos | terminal, verificar |
| 429 | >1 request a la misma URL cada 5 min | backoff por URL (nuestro guardián local 300 s cubre) |
| 500 | error interno | backoff, contactar si es frecuente |

## Cuota observada en probes (2026-09-23/24)

- Token: OK inmediato (formato body `grant_type=password` + `username` +
  `password`, sin HTTP Basic).
- Fleet: 429 `Try again in 61 seconds` tras ~4 probes (token+fleet cuentan).
  Esperar 90s+ entre intentos durante desarrollo.
- Respuesta 429 en JSON: `{"statusCode":429,"message":"..."}`.
- 2026-09-24: endpoint de token respondió 400 `Invalid request` al mismo
  formato que antes obtuvo 200 — causa probable: cuota/bloqueo temporal,
  no formato. Pendiente de confirmar tras enfriar la cuota.

## Diseño pendiente (parcialmente implementado en working tree)

- Estado: comparador read-only implementado en working tree (`_compare_hours.py`); pendiente productivizar `komtrax.py`/`run_komtrax_sync.py`: auth password-grant, TTL 2h
  (reutilizar token, no autenticar por ejecución), quota-guard **por URL**
  (300 s guardián local), retry con backoff, refresh reactivo ante 401, recorrido de
  páginas `/Fleet/N`.
- Mapeo identidad: PIN/serial Komatsu vs `machinery.serial`
  (EquipmentID = Customer Machine No.).
- Alcance: SPEC actual excluye OEMs no-DEVELON → requiere decisión
  (nuevo SPEC o extensión) antes de sincronizar Komatsu a Fracttal.
