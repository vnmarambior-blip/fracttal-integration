# ARCHITECTURE.md — fracttal-integration (estado real)

> Documenta la arquitectura ACTUAL. No propone una futura.
> Fuente de verdad: `PROJECT_SPEC.md` manda en conflicto.
> Última verificación: suite 217 passed.

---

## 1. Diagrama de capas y flujo

```text
MyDevelon ─┐
           │   adapters                  común OEM               core
           ├──→ mydevelon.py ──┐
           │                   ├─→ oem_common.py ──→ api.py ──→ database.py ──→ SQL Server
           │   komtrax.py ─────┘   (parse AEMP,      (decisiones,  (P1.1, audit)
           │                       token, cuota,     P1.1, PUT)
           └── (Fleet/APIs)        env_flag)
                                                                │
                                                         Fracttal ONE API
                                                                │
                    orchestration                               ▼
                    run_mydevelon_sync.py ──┐            Power BI (fuera de alcance)
                    run_komtrax_sync.py ────┤
                    run_all_sync.py ────────┘
                    reconcile.py (R0) · operational/health.py (Fase 4, solo 4.1)
```

---

## 2. Responsabilidad de cada capa/componente

| Capa | Componentes | Responsabilidad | No hace |
|---|---|---|---|
| **Adapters** | `mydevelon.py`, `komtrax.py` | Auth OEM, fetch Fleet, `komtrax`: gaps/decide | Decisiones de negocio, writes |
| **Común OEM** | `oem_common.py` | Parse AEMP namespace-agnostic, token cache, cuota, `env_flag` | Nada específico de un OEM |
| **Core** | `api.py` | Cliente Fracttal, validaciones, `process_equipment`, P1.1 write path | Orquestación de flota, CLI |
| **Persistence** | `database.py`, `migrate_*.sql` | Conexión única, P1.1, auditoría, `initialize_database` | Lógica OEM/Fracttal |
| **Orchestration** | `run_*_sync.py`, `reconcile.py` | CLI, loops por equipo, gates, reportes | Decisiones (delegan a core) |
| **Observabilidad** | `operational/health.py` | Health checks read-only (Fase 4, solo Task 4.1) | Sync, writes |

---

## 3. Flujo MyDevelon → parser → core → Fracttal/SQL

```text
run_mydevelon_sync.py [--live]
  → mydevelon.get_cached_token → POST /token (Basic)
  → modo live: chequeo cuota 1 vez → get_fleet_xml_pages (sigue next, tope 10,
      anti-loop, fallo HTTP aborta sin parcial) → record 1 vez
  → oem_common.parse_fleet_xml por página → concat_fleet_pages (dedup por PIN)
  → modo live vacío/cuota: RuntimeError, SIN fallback a fixture
  → modo file: fixture explícito
  → por item: api.process_equipment(source="MyDevelon", default)
      → get_equipment_by_serial → get_asset_type → upsert_machinery
      → get_current_hourmeter → validate_source_timestamps
      → validate_reading_is_newer → get_telemetry_sync_config
      → decide UPDATE/SKIP_EQUAL/REVIEW_* → P1.1 intent
      → dry_run? WOULD_UPDATE : PUT → GET verify → VERIFIED
      → save_horometer_update (auditoría)
  → umbral cobertura: 0 éxitos con equipos → COBERTURA BAJA, exit 3
```

Estado OEM 2026-09-25: `/token` responde `{"code":500,"msg":"ID not registered in aemp."}`.
Modo `--live` aborta ruidoso; fixture `fixtures/mydevelon_fleet_minutes.xml` como referencia.

---

## 4. Flujo Komtrax → parser → core → Fracttal/SQL

```text
run_komtrax_sync.py --live
  → komtrax.get_komtrax_token_cached → POST /provider/token (body, TTL 7000s)
  → komtrax.get_komtrax_fleet_all → GET /Fleet/N paginado (cuota 300s/URL)
  → komtrax.parse_komtrax_hours → {serial: hours, datetime}
  → por serial en KOMTRAX_MACHINES (_compare_hours.py):
      → classify_komtrax_gap → get_fracttal_hourmeter
      → komtrax.decide_comparison (valor primero, luego fecha)
      → solo UPDATE → api.process_equipment(source="Komtrax")
      → mismo path P1.1 que MyDevelon
  → umbral cobertura: UPDATE==0 y SKIP_EQUAL==0 → COBERTURA BAJA, exit 3
```

Identidad: `code` (= unit_name) + `field_4` (= SerialNumber); `is_serial_control: False`.
Productivo bloqueado por diseño (`SystemExit(2)` con `SYNC_DRY_RUN=false`).
Estado 2026-09-25: 13/13 evaluados en vivo; 6 UPDATE → `WOULD_UPDATE` (configs KOMTRAX creadas).

---

## 5. Contratos externos actuales

| Sistema | Auth | Endpoints usados | Estado 2026-09-25 |
|---|---|---|---|
| MyDevelon | POST `/token` Basic | `GET /Fleet/{page}` (paginado, A) | 🔴 `ID not registered in aemp` |
| Komtrax | POST `/provider/token` body | `GET /{sub}/Fleet/{page}` | 🟢 operativo |
| Fracttal | OAuth `get_access_token` | `/api/items/`, `/api/meters/`, readings | 🟢 operativo |
| SQL Server | `SQL_CONNECTION_STRING` (.env) | `FracttalIntegration` | 🟢 operativo |

---

## 6. Mapa SPEC → componente → evidencia

| Requisito | Componente | Evidencia |
|---|---|---|
| R0 (huérfanas) | `reconcile.py`, `list_horometer_write_intents` | `INTENT_RECORDED=0`, 46 VERIFIED |
| R1 (suite + ejecución sin writes) | `tests/` (26 archivos) | 217 passed; suite verde con `SQL_CONNECTION_STRING=''` |
| R2 (deps) | `requirements.txt` | `requests`, `dotenv`, `mssql-python`, `openpyxl` |
| R3 (HTTP) | `api.py` | `test_r3_http_classification.py` |
| R4 (P1.1) | `database.py` (OUTPUT INSERTED.id, rowcount=1) | `test_p1_1_*`, `test_r15_concurrency.py` |
| R5 (verify) | `apply_meter_reading` + GET | E2E 55267 VERIFIED/PASS |
| R6 (audit) | `save_horometer_update`, estados | 12+ estados trazables |
| R7 (evento único) | `process_equipment` (sin 2° insert) | `test_r7_single_event.py` |
| R8 (MyDevelon) | `oem_common.parse_fleet_xml` (aisla por ítem) | 25 equipos sin abortar |
| R9 (normalización) | `normalize_comparison_value` | `test_r9_normalization.py` |
| R10 (temporal) | `validate_reading_is_newer` | `test_r10_temporal_policy.py` |
| R11/R12 (equal/old) | comparación + `MH18RegressionTests` | `test_r11_skip_equal.py` |
| R13 (identidad) | `upsert_machinery` (bloquea remapeo) | `test_r13_identity.py` |
| R14 (DB) | `initialize_database` + `migrate_*.sql` | 13 cols + CK + UX verificados |
| R15 (concurrencia) | TRY/CATCH unique + `IdempotencyConflictError` | `test_r15_concurrency.py` |
| R16 (config) | `database.get_connection()` única | `test_aux_config.py` |
| R17 (imports) | `if __name__` guards | `test_import_safety.py` |
| R18 (logs) | lista blanca serial/valores/conteos | `test_log_sanitization.py` |
| R19 (MyDevelon) | token texto, cuota, **paginación obligatoria** | `test_mydevelon_source.py` (6 tests paginación) |
| R20 (reporte) | RESUMEN + exit ERROR/COBERTURA | `test_sync_report.py` (umbral exit 3) |
| R21/R22 (Komtrax) | `komtrax.py`, `normalize_unit` | namespace-agnostic, `CF 01`→`CF01`, 19144→CF05 |

---

## 7. Puntos de entrada

| Entry point | Uso | Modo |
|---|---|---|
| `run_mydevelon_sync.py [--live] [--fleet-xml] [--report] [--record]` | Flota MyDevelon (paginada en live) | default fixture; `--live` aborta si cuota/vacío (sin fallback) |
| `run_komtrax_sync.py [--live] [--fleet-xml]` | Flota Komtrax (13 fijos) | productivo bloqueado por diseño (exit 2) |
| `run_all_sync.py [--live] [--dry-run] [--report] [--md-fleet-xml] [--kt-fleet-xml]` | Orquesta ambos | **default DRY-RUN seguro**; `--live` explícito; reporte consolidado propio; exit 0/1/3 |
| `reconcile.py` (`reconcile_orphan_intents`) | Cierra huérfanas con evidencia | read-only + UPDATEs misma fila; nunca PUT |

---

## 8. P1.1 y garantías principales

```text
Intent (OUTPUT INSERTED.id / re-lectura por key)
  → PUT Fracttal → GET verificación → VERIFIED / WRITE_AMBIGUOUS / ERROR_RETRYABLE / ERROR
```

- `event_id=None, filas=0` = fallo de persistencia, nunca intención.
- Sin `event_id` válido no hay PUT.
- Re-ejecución: `VERIFIED`→no-op, `WRITE_AMBIGUOUS`→bloqueo, `ERROR_RETRYABLE`→reutiliza `event_id`.
- Índice único `UX_horometer_updates_idempotency_key` + `attempt_count` por intento.
- Implementación: `database.py:create_horometer_write_intent`, `mark_horometer_write_in_progress`, `update_horometer_write_result`.

---

## 9. Persistencia SQL (`database.py`)

| Grupo | Funciones |
|---|---|
| Conexión/init | `get_connection`, `initialize_database`, `verify_table_has_identity` |
| Maquinaria | `get_machinery_by_serial`, `get_machinery_by_id`, `upsert_machinery`, `get_telemetry_sync_config` |
| P1.1 | `create_horometer_write_intent`, `mark_horometer_write_in_progress`, `update_horometer_write_result`, `get_horometer_update_by_idempotency_key`, `list_horometer_write_intents`, `_recover_intent_id_by_key` |
| Auditoría/lectura | `save_horometer_update`, `get_latest_horometer_update`, `get_latest_horometer_update_by_serial`, `get_horometer_history` |
| Meters | `save_machine_meter`, `get_machine_meter` (0 callers — reservado, NO VERIFICADO en flujo) |

Migraciones: `migrate_p1_1_idempotency.sql`, `migrate_horometer_status.sql` (intocables).

---

## 10. Observabilidad

- `operational/health.py`: 5 checks read-only (Fracttal/SQL críticos; MyDevelon/Komtrax/Config warn). Exit 2 si crítico falla. (Fase 4: solo Task 4.1 implementada.)
- `reconcile.py`: dry-run real (`written: False`) vs aplicado.
- Runners: conteos por estado + exit codes; `--report` consolidado solo en `run_all_sync.py`.
- Semántica `dry_run` (proyecto): **Fracttal intocable + SQL auditable** (`WOULD_UPDATE`/revisión). Excepción: `reconcile` dry-run = cero writes.

---

## 11. Drift conocido

| # | Drift | Estado |
|---|---|---|
| 1 | MH46 runbook (creación manual horómetro) | Pendiente, diferido al final |
| 2 | MH07 multi-horómetro (política) | Pendiente, diferido al final |
| 3 | Dependencia `tests → borrador/tools` vía `conftest.py` sys.path | Activa; `test_import_safety` la fija. No remover sin migrar tests |
| 4 | Rama `fix/komtrax-report-arg` sin mergear | Sin cambios funcionales pendientes (auditado); candidata a eliminación tras commit consolidado |

---

## 12. Reglas para futuras modificaciones

- No dividir `api.py` salvo necesidad funcional demostrada.
- No mover `_compare_hours.py` sin reemplazo funcional (tabla 13 Komtrax vive ahí).
- No eliminar `borrador/tools` sin verificar dependencias (`test_import_safety`, `test_aux_config`, `test_r10`).
- No modificar P1.1 sin actualizar tests/evidencia.
- No cambiar contratos OEM sin tests de parser.
- No introducir lógica de negocio en los runners.
- Mantener separación adapters / común-OEM / core / persistence / orchestration.
- Los cambios arquitectónicos deben estar justificados por una necesidad real, no por estética.
- Actualizar este documento cuando cambie una responsabilidad o flujo.

---

## Procedencia de la información

- **Código**: capas, funciones, imports, gates, P1.1 (`api.py`, `database.py`, `oem_common.py`, `komtrax.py`, `mydevelon.py`, runners, `operational/health.py`, `reconcile.py`).
- **Tests**: suite 217 passed (incluye corrida con `SQL_CONNECTION_STRING=''`); nombres de archivos citados.
- **Spec**: `PROJECT_SPEC.md` (reglas, fases, criterios) y `SPEC_PHASE4_OPERATIONAL_LAYER.md` (solo Task 4.1 implementada).
- **Evidencia viva**: conteos SQL R0/H1/R14, E2E 55267 VERIFIED, dry-run 38 máquinas, logs 23/09.
- `NO VERIFICADO` en flujo: `save/get_machine_meter` (0 callers).

## Related Skills

- **spec-driven-qa** — validar cambios contra este mapa
- **audit-project** — detectar drift nuevo
- **project-architecture** — mantener este documento
- **telemetry-audit**, **data-quality**, **fracttal-integration**, **aemp-integration** — por capa
