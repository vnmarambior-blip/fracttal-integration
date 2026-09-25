# PROJECT_SPEC.md — Estabilización y corrección de fracttal-integration

## Objetivo

Restablecer la confiabilidad técnica y operativa de `fracttal-integration`, asegurando que los flujos MyDevelon → Fracttal y Komtrax → Fracttal puedan ejecutarse, validarse y auditarse de principio a fin sin errores estructurales, registros inconsistentes ni actualizaciones no verificadas.

## Alcance

* Reconciliar las 21 intenciones P1.1 huérfanas (`INTENT_RECORDED` del 22/09/2026) antes de cualquier nueva ejecución productiva.
* Cerrar la causa raíz del `event_id=None, filas=0` (hipótesis H1: `SCOPE_IDENTITY()` NULL).
* Recuperar la ejecución completa de la suite de pruebas.
* Corregir los bloqueantes identificados en la auditoría técnica.
* Corregir el flujo de idempotencia P1.1 y su persistencia en SQL.
* Asegurar una clasificación correcta de respuestas HTTP de Fracttal.
* Garantizar que los estados relevantes del proceso queden auditados en SQL.
* Eliminar duplicidad de eventos de actualización.
* Robustecer el procesamiento de datos provenientes de MyDevelon, Komtrax y Fracttal.
* Validar correctamente valores, fechas, timestamps, `NaN` e infinitos antes de actualizar.
* Proteger la identidad de maquinaria y evitar remapeos automáticos inseguros.
* Definir política multi-horómetro (caso MH07) y runbook de creación manual (caso MH46).
* Alinear inicialización, migraciones y estructura real de la base de datos.
* Centralizar la configuración de conexión y eliminar configuraciones contradictorias.
* Mantener el principio de actualización: **solo actualizar cuando la lectura del OEM sea posterior a la última lectura válida de Fracttal**.
* Reconciliar el inventario Komtrax contra Fracttal (13 unidades confirmadas, 1 con `unit_name=vacio` → `CF05`).
* Dejar el sistema en condiciones de ser probado de forma controlada antes de una nueva ejecución productiva.

## Fuera de alcance

* Cambiar la arquitectura general OEM → SQL → Fracttal → Power BI.
* Cambiar la fuente de datos MyDevelon.
* Cambiar la fuente de datos Komtrax.
* Cambiar la lógica de identidad de maquinaria basada en PIN/serial, salvo fallback justificado técnicamente (caso MH07 serie vacía) con justificación documentada.
* Cambiar los valores de horómetro de Fracttal manualmente.
* Ejecutar una sincronización productiva como mecanismo de prueba.
* Introducir nuevos OEM distintos de DEVELON y KOMATSU.
* Desarrollar nuevas funcionalidades de Power BI.
* Eliminar la auditoría SQL existente.
* Modificar el corpus o documentación externa al proyecto.
* Reemplazar P1.1 por un mecanismo sin idempotencia.
* Modificar la interfaz de usuario de Fracttal.
* Sincronizar datos de Komtrax que no tengan equivalente en Fracttal (caso CF 01/CF 02 con espacio, serial `19144` con `unit_name=vacio`).

## Reglas

### 0. Reconciliación previa (P0-0, antes que todo)

Las 21 filas `INTENT_RECORDED` del 22/09/2026 son intenciones huérfanas: su PUT probablemente se ejecutó pero el resultado jamás se registró ni verificó. Antes de cualquier run productivo o prueba con efectos:

1. Para cada intención huérfana, comparar `new_value` contra el valor actual en Fracttal.
2. Transicionar con evidencia a `VERIFIED` (valor coincide) o `ERROR_RETRYABLE` (no coincide / incierto).
3. Registrar la evidencia de cada transición en SQL.

Aceptación: cero filas en estado `INTENT_RECORDED` residual; cada una con estado final y evidencia.

### 1. Pruebas ejecutables

El proyecto debe permitir ejecutar `pytest` sin errores de colección.

Para los 3 tests que importan `parse_equipment_snapshot_xml` (`test_mydevelon_fracttal.py:6`, `test_mydevelon_single.py:4`, `test_mydevelon_sql.py:4`): decisión tomada — opción (a), función real implementada en `mydevelon.py:634` con TDD (es funcionalidad faltante).

No se debe crear una función ficticia únicamente para satisfacer un import roto.

Adicionalmente:

* `test_p1_1_idempotency.py` debe ejecutarse en CI.
* `.venv` local debe contener `mssql-python` y `openpyxl` (paridad con CI).
* Ver Regla 17: la colección no debe producir efectos secundarios.

### 2. Dependencias

Toda dependencia utilizada por código ejecutable debe estar declarada en `requirements.txt`. En particular `openpyxl` (`export_database_excel.py:4-7`). Una instalación limpia debe poder instalar todo sin depender del entorno local del desarrollador.

### 3. Clasificación HTTP

Clasificación exacta según naturaleza **y punto del flujo**:

| Contexto | Clasificación |
|---|---|
| `2xx` | Operación aceptada; continuar con verificación |
| `4xx` excepto 408/429 | Rechazo determinista terminal (`ERROR`); sin retry automático |
| 429 / 408 / `5xx` / timeout con PUT ya enviado | `WRITE_AMBIGUOUS` (pudo haberse aplicado) |
| `5xx` / timeout sin PUT enviado (falló la conexión) | `ERROR_RETRYABLE` con backoff |
| PUT ok + GET de verificación falla | `WRITE_AMBIGUOUS` (conducta actual, conservar) |

Un `4xx` no debe clasificarse como `ERROR_RETRYABLE` por defecto.

### 4. P1.1 e idempotencia

Toda actualización debe registrar una intención antes del PUT. La intención debe producir exactamente un identificador de evento válido y una única fila persistida.

* Prohibido asumir `SCOPE_IDENTITY()`: usar `OUTPUT INSERTED.id` o re-lectura por `idempotency_key`, verificado contra `TableHasIdentity` real (causa H1).
* `event_id=None, filas=0` es fallo de persistencia, nunca intención registrada.
* Prohibido continuar hacia el PUT si la intención no quedó registrada con `event_id` válido.
* `mark_horometer_write_in_progress` debe verificar `rowcount == 1` igual que `update_horometer_write_result`.
* La reejecución respeta el estado idempotente existente (`VERIFIED` → no-op, `WRITE_AMBIGUOUS` → bloqueo, `ERROR_RETRYABLE` → reutiliza `event_id`).

### 5. Verificación de actualización

Un PUT exitoso no constituye actualización confirmada. Flujo obligatorio:

```text
Intent → PUT → GET de verificación → VERIFIED / WRITE_AMBIGUOUS / ERROR_RETRYABLE / ERROR
```

`VERIFIED` solo con evidencia de que Fracttal contiene el valor esperado. Tolerancia: igualdad exacta tras normalización a 2 decimales (`DECIMAL(18,2)`).

### 6. Estados auditables

Todo resultado relevante de `process_equipment` debe reconstruirse desde SQL. Mínimo: `UPDATED`, `VERIFIED`, `SKIP_EQUAL`, `NO_VALID_METER`, `REVIEW_SOURCE_DATE`, `REVIEW_*`, `ERROR_*`, `WRITE_AMBIGUOUS`, `ERROR_RETRYABLE`.

`ERROR_NO_PIN`, `ERROR_SOURCE_HOURS` (nacen en `run_mydevelon_sync.py` sin `machinery_id`/`meter_id`) se persisten con FKs nulables + `serial` + `error_code`, o en tabla de nivel-sync. Criterio: ningún estado vive solo en memoria/stdout.

Métrica de cobertura por corrida (`sincronizados/total`) con umbral de alerta: una corrida 100% errores de fuente no es éxito aunque no haya `ERROR_UNEXPECTED`.

### 7. Un único evento de actualización

El evento canónico de una actualización verificada es la fila de intención en `VERIFIED`. Se eliminó el segundo insert `UPDATED` de `process_equipment`; mismo criterio para el path de error. Toda fila de auditoría conserva su `idempotency_key` cuando corresponda. Sin razón explícita y modelo que diferencie ambos eventos, no hay segunda fila.

### 8. Datos MyDevelon

Un dato inválido de un equipo no aborta la flota. Aislamiento por ítem (try/except por equipo en el loop + en el parser):

```text
Equipo A → lectura válida → procesar
Equipo B → Hour="N/A" → registrar error → continuar
Equipo C → lectura válida → procesar
```

Cubre: horas inválidas, fechas inválidas, `NaN`, `Inf`, no numéricos. En cambio, sobre corrupta (XML malformado total, vacío, namespace cambiado, flota vacía) → `ERROR` ruidoso con alerta, jamás "0 equipos" como éxito.

### 9. Normalización de valores

Una sola función de normalización a tipo numérico común usada por ambos lados antes de comparar. Prohibida comparación directa `str` vs `float` (caso `"9" > "10"`). `NaN` e infinitos se rechazan en el borde de parseo, no en la comparación.

### 10. Regla temporal de actualización

```text
MyDevelon reading_datetime > Fracttal last_data.date  →  candidato a UPDATE
```

Lectura sin fecha válida → estado revisión/error auditado (Regla 6). Lectura antigua nunca actualiza lectura Fracttal más reciente. Decisión explícita y documentada sobre `MAX_SOURCE_AGE_HOURS=48` / `ALLOW_OLD_SOURCE_UPDATES`: **eliminados** — la telemetría es la verdad sin importar su antigüedad; solo el orden temporal decide (`reading_datetime` vs `last_data.date`). Sin tercer estado.

### 11. Lecturas iguales

Valor MyDevelon equivalente al de Fracttal (normalizado, Regla 9) → `SKIP_EQUAL`, salvo otra condición que exija revisión.

### 12. Lecturas antiguas ≠ lecturas iguales

```text
MyDevelon: valor = 1437.67, fecha = 2022-11-30
Fracttal:  valor = 4318,     fecha = 2026-07-13
```

Este caso (MH18 real) jamás es `SKIP_EQUAL`: pasa por validación temporal y queda en revisión/error. Test de regresión nombrado obligatorio.

### 13. Identidad de maquinaria

Prohibido remapear `serial` automáticamente por coincidencia de `equipment_code` (`database.py`, función `upsert_machinery`). Un conflicto `equipment_code` / `serial` / `machinery_id` detiene el remapeo y genera estado auditable. Sin sobrescritura silenciosa.

**Komtrax**: la identidad se establece por `code` (= `unit_name` Komtrax) y `field_4` (= `SerialNumber` Komtrax), no por el campo `serial` de Fracttal (siempre `None`). `is_serial_control: False` para equipos Komtrax. Cualquier conflicto entre `code` y `field_4` debe detener el flujo y generar estado auditable.

**Namespace**: el parser XML debe ser namespace-agnostic (Regla 21). No usar URI de namespace fijo para buscar elementos XML.

### 14. Base de datos

`initialize_database` y migraciones con única fuente de verdad: DB nueva contiene todas las columnas, restricciones e índices P1.1. Migraciones con `WITH NOCHECK` + backfill para no bloquearse con estados legacy (`migrate_horometer_status.sql:21`).

### 15. Concurrencia

El patrón check-then-insert (`save_horometer_update`, `create_horometer_write_intent`) usa `TRY/CATCH` de violación única → traducir a `IdempotencyConflictError`, o centralizar toda escritura con key en la función de intención. Una carrera no genera duplicados ni aborta la corrida. `attempt_count` se incrementa por intento, nunca fijo en 1. El `return existing` del dedup define si actualiza mensaje/estado o ignora (documentado, no silencioso).

### 16. Configuración

Única fuente: `SQL_CONNECTION_STRING` vía `database.get_connection()` para código productivo y scripts auxiliares. Prohibidos los 7 strings `Server=localhost` hardcodeados. Sin env var → fallo explícito al arrancar, jamás default local silencioso.

### 17. Importaciones sin efectos laterales

Importar un módulo no debe: ejecutar POST a APIs, abrir conexiones reales, imprimir secretos, operar destructivamente ni modificar la BD. Todo script ejecutable bajo `if __name__ == "__main__":` explícito. Los archivos `cleanup_mydevelon_config.p` y `get_equipment_by_serial()` con paréntesis ya no existen (higiene aplicada: solo `cleanup_mydevelon_config.py` y `check_equipment_by_serial.py`, ambos con guarda). Excepción conocida: `_compare_hours.py` y `_reconcile_komtrax.py` aún se ejecutan al importar (Etapa 2 de limpieza).

### 18. Seguridad de logs

Lista blanca (logueable): serial, valores, conteos, `event_id`, `error_code`. Lista negra (prohibido): tokens, connection strings, XML completo de flota, headers, contenido de `.env`. Aplica a `mydevelon.py:109-129,191-214` y `test_env.py:6-11`.

### 19. MyDevelon

Validar formato real de respuesta de auth (texto vs JSON, `mydevelon.py:72`), detectar expiración de token, retry con backoff ante transitorios, no asumir paginación: verificar si `/Fleet/1` es total o página (si hay páginas, recorrerlas y distinguir procesados vs disponibles). Validar unidad de `Hour` del lado MyDevelon (horas vs minutos) como ya se hace del lado Fracttal.

### 20. Resultado de corrida

Resumen final con conteos de: procesados, actualizados, verificados, omitidos, revisiones, errores recuperables, errores terminales, no procesados. Tabla de salida:

| Estado | Exit |
|---|---|
| `ERROR_UNEXPECTED` presente | ≠ 0 |
| Cobertura bajo umbral | ≠ 0 |
| Resto (`SKIP`/`REVIEW`/errores de fuente aislados) | 0 con resumen y métrica |

### 21. Komtrax / Komatsu

Komtrax usa ISO 15143-3 AEMP con **namespace diferente** al de MyDevelon: `http://www.jcmanet.or.jp/english2017/ISO/15143/-3/20190501` vs `http://standards.iso.org/iso/15143/-3`. El parser XML debe ser **namespace-agnostic** (buscar por nombre local, no por URI).

- Autenticación: OAuth2 `grant_type=password` + `username` + `password` en el body (URL-encoded, sin HTTP Basic Auth) sobre `/provider/token`. Respuesta con `access_token` (`token_type: bearer`, `expires_in: 7199` ≈ **2 horas**).
- Endpoints: `{Host}/{SubscriberID}/Fleet/{PageNumber}` (paginación real, recorrer páginas).
- Mapeo de campos a Fracttal: `SerialNumber` → `field_4`, `EquipmentID`/`Unit name` → `code`, `Model` → `field_3`, `OEMName` → `field_2`.
- `is_serial_control: False` en Fracttal para equipos Komtrax — la identidad se maneja por `code` y `field_4`, no por `serial`.
- **Normalización**: `unit_name` puede tener espacios (`CF 01`) en Komtrax pero no en Fracttal (`CF01`). Normalizar espacios antes de comparar.
- **Seriales huérfanos**: Komtrax puede tener `unit_name=vacio` para serials reales. Verificar contra `field_4` en Fracttal para descubrir la asignación correcta (ej: serial `19144` → `CF05`).
- **Fleet vacía / namespace inesperado** → `FleetEmptyError` explícito, no silencioso.
- **No mezclar fuentes**: Komtrax y MyDevelon son flujos independientes. La comparación se hace contra Fracttal, nunca entre sí.
- **Cuota**: Komtrax tiene rate limit por URL (ver `docs/komtrax-iso-api.md`).

### 22. Normalización de espacios en códigos

Los códigos de equipo (`code`, `unit_name`) pueden tener espacios en el origen (Komtrax: `CF 01`) pero no en Fracttal (`CF01`). Toda comparación de código debe normalizar espacios internos antes del match. Test de regresión nombrado obligatorio para este caso.

## Restricciones

* No realizar PUT productivos durante la corrección inicial.
* No re-ejecutar el sync productivo hasta reconciliar las 21 intenciones huérfanas (Regla 0) y cerrar H1 (Regla 4).
* No modificar manualmente los horómetros de Fracttal para hacer pasar pruebas.
* No eliminar P1.1 ni sus controles de idempotencia.
* No eliminar la auditoría SQL como solución a errores de persistencia.
* No ocultar errores cambiando simplemente su clasificación a SKIP.
* No crear funciones dummy para satisfacer imports sin validar primero la intención de los tests.
* No cambiar silenciosamente la identidad de maquinaria.
* No introducir dependencias innecesarias para el funcionamiento real.
* No considerar una actualización exitosa sin evidencia de verificación.
* No ejecutar nuevamente el sync productivo hasta que la suite y las pruebas controladas de P1.1 sean satisfactorias.
* Los cambios deben ser verificables individualmente mediante tests.
* La BD productiva es fuente de datos real, no entorno de prueba.
* La regla temporal usa `reading_datetime` de MyDevelon y `last_data.date` de Fracttal.
* Compatibilidad con la arquitectura existente salvo modificación necesaria para un problema identificado.

## Criterio de aceptación

El proyecto se considera estabilizado cuando:

* `pytest --collect-only` termina sin errores de importación ni efectos secundarios.
* La suite ejecuta en verde; toda excepción listada explícitamente con justificación y fecha (no "fallos no bloqueantes" genéricos).
* Regla 0 cumplida: cero intenciones huérfanas, cada una con estado final y evidencia.
* H1 cerrado: `TableHasIdentity` verificado + mecanismo `OUTPUT INSERTED.id`/re-lectura en código.
* Una actualización válida completa: MyDevelon → validación → intención P1.1 → PUT → GET verificación → `VERIFIED` → auditoría SQL.
* 4xx y 5xx producen los estados distintos de la tabla de la Regla 3 (test por caso).
* Lectura igual → `SKIP_EQUAL`; lectura antigua → nunca actualiza (test de regresión MH18 nombrado); fecha inválida → revisión/error auditado.
* Caso multi-horómetro (MH07) y runbook de creación manual (MH46) definidos y probados.
* Equipo con datos corruptos no detiene al resto de la flota.
* Cero eventos de actualización duplicados.
* Cero remapeos automáticos de identidad ante conflictos.
* DB nueva estructuralmente compatible con P1.1.
* Corrida con errores relevantes no termina con código de éxito silencioso.
* Sin secretos ni XML completos en logs.
* Producción solo tras validación completa en entorno controlado.
* Komtrax: parser namespace-agnostic probado (MyDevelon + Komtrax ambos funcionan).
* Komtrax: 13/13 serials encontrados por `field_4` en Fracttal, mapeo `code` = `unit_name` verificado.
* Komtrax: normalización de espacios en códigos (`CF 01` → `CF01`) funcionando.
* Komtrax: serial `19144` (`unit_name=vacio`) resuelto contra `CF05` en Fracttal.
* Komtrax y MyDevelon son flujos independientes sin mezcla de fuentes.

## Orden de ejecución

* **Fase 0** — Reglas 0 y 4 (reconciliación + causa H1). Sin esto nada más es verificable.
* **Fase 1** — Reglas 15, 7, 5 (persistencia, evento único, verificación).
* **Fase 2** — Reglas 3, 6, 20 (clasificación, auditoría, resultado de corrida).
* **Fase 3** — Reglas 8, 9, 10, 11, 12, 19, 21, 22 (robustez de datos + MyDevelon + Komtrax).
* **Fase 4** — Reglas 1, 2, 13, 14, 16, 17, 18 + política multi-horómetro y runbook MH46.

## Related Skills

Cuando trabajes con este spec, invoca las skills relevantes:

- **telemetry-audit** — para validar reglas de auditoría (Reglas 0, 5, 6, 20) y reconciliación
- **data-quality** — para clasificar inconsistencias (Reglas 8, 9, 11, 12, 13, 21, 22)
- **aemp-integration** — para arquitectura multi-OEM y parsers ISO 15143-3 (Regla 21)
- **fracttal-integration** — para interacciones Fracttal API + SQL control (Reglas 3, 4, 5, 7, 14, 16)
- **python-clean-code** / **clean-*** — para calidad de código al implementar reglas (Regla 17)
- **boy-scout** — mejoras incrementales mientras editas (Regla 17)
- **spec-driven-qa** — ciclo de auditoría/implementación gobernado por este spec
