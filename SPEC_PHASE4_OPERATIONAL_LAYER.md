# SPEC_PHASE4_OPERATIONAL_LAYER.md — Capa Operacional (Fase 4)

> **Objetivo:** Poner una "cabina de piloto" sobre el motor existente (MyDevelon/Komtrax → P1.1 → Fracttal → SQL) sin tocar el motor.

---

## 1. Arquitectura

```text
                    ┌── MyDevelon ──┐
                    │               │
run_sync.py ────────┤  Motor (intocable)  ├──→ Fracttal
                    │               │
                    └── Komtrax ────┘
                            │
                            ▼
                       SQL / P1.1
                            │
                            ▼
                  ┌───────────────────┐
                  │ Capa Operacional  │
                  ├───────────────────┤
                  │ Health Check      │
                  │ Orquestación      │
                  │ Consola Rica      │
                  │ Alertas           │
                  │ Reporte MD        │
                  │ Histórico         │
                  └───────────────────┘
```

**Motor intocable:**
- `api.py` / `process_equipment` / P1.1 / `database.py`
- `run_mydevelon_sync.py` / `run_komtrax_sync.py` → *workers internos*

**Capa operacional (nueva):**
- `run_sync.py` — único entry point CLI
- `operational/` — módulos: health, console, report, alerts, history

---

## 2. CLI Spec — `run_sync.py`

```bash
# PRODUCCIÓN (default)
python run_sync.py --live [--report path.md] [--verbose]

# DRY-RUN (simulación)
python run_sync.py --dry-run [--report path.md]

# Ayuda
python run_sync.py --help
```

| Flag | Tipo | Default | Descripción |
|------|------|---------|-------------|
| `--live` | flag | **true** | Modo producción (APIs reales) |
| `--dry-run` | flag | false | Simulación (fixtures, sin red) |
| `--report <path>` | str | `reports/sync_<timestamp>.md` | Path reporte markdown |
| `--verbose` | flag | false | Log detallado por equipo |
| `--skip-health` | flag | false | Saltar health checks (solo emergencia) |

**Exit codes:**
| Code | Significado |
|------|-------------|
| 0 | OK completo |
| 1 | Error genérico |
| 2 | Health check crítico falló |
| 3 | Sync parcial (algunas fuentes fallaron) |
| 4 | Config faltante (alertas bloqueantes) |

**Env vars relevantes:**
- `SYNC_DRY_RUN` (sobrescrito por `--live`/`--dry-run`)
- `SYNC_VERBOSE` (sobrescrito por `--verbose`)

---

## 3. Health Check Matrix

| Componente | Check | Crítico | Acción si falla |
|------------|-------|---------|-----------------|
| **Fracttal** | `GET /api/items/` (auth + 1 item) | **SÍ** | Abortar (exit 2) |
| **SQL Server** | `SELECT 1` + `horometer_updates` existe | **SÍ** | Abortar (exit 2) |
| **MyDevelon** | Auth token + Fleet 1 página | WARN | Continuar, marcar como degradado |
| **Komtrax** | Auth token + Fleet 1 página | WARN | Continuar, marcar como degradado |
| **Config** | `telemetry_sync_config` tiene filas | WARN | Continuar, alerta en reporte |

**Regla:** Si **cualquier crítico falla** → exit 2, no ejecutar sync.
**WARN** → log visible, continuar, incluir en alertas finales.

---

## 4. Consola Spec — Fases 1-5

### Formato General
- Ancho fijo: 80 chars
- Separadores: `=` × 80, `-` × 80
- Prefijos: `✓` OK, `⚠` WARN, `✗` ERROR, `▶` PROGRESO, `ℹ` INFO
- Colores ANSI (sin deps): Verde=32, Amarillo=33, Rojo=31, Cian=36, Reset=0

### Fase 1/5 — HEALTH CHECK
```text
================================================================================
       FRACTTAL TELEMETRY SYNC — 2026-09-25 09:42:13
================================================================================

[1/5] HEALTH CHECK
────────────────────────────────────────────────────────────────────────────────
▶ Fracttal          ✓ OK (12ms)
▶ SQL Server        ✓ OK (3ms)
▶ MyDevelon         ⚠ DEGRADADO (cuota 12min restantes)
▶ Komtrax           ✓ OK (45ms)
▶ Configuración     ⚠ 6 equipos sin config KOMTRAX
```

### Fase 2/5 — MYDEVELON
```text
[2/5] MYDEVELON
────────────────────────────────────────────────────────────────────────────────
▶ Equipos totales:     25
▶ Procesados:          25
▶ VERIFIED:            3
▶ SKIP_EQUAL:          1
▶ REVIEW:              20
▶ WOULD_UPDATE:        1
▶ NO_VALID_METER:      1
▶ ERROR:               0
```

### Fase 3/5 — KOMTRAX
```text
[3/5] KOMTRAX
────────────────────────────────────────────────────────────────────────────────
▶ Equipos totales:     13
▶ Procesados:          10
▶ VERIFIED:            0
▶ SKIP_EQUAL:          3
▶ REVIEW_OLD_SOURCE:   2
▶ GAP:NO_HOURS:        3
▶ CONFIG_MISSING:      6
▶ ERROR:               1 (CF05 sin horómetro)
```

### Fase 4/5 — RESULTADO CONSOLIDADO
```text
[4/5] RESULTADO
────────────────────────────────────────────────────────────────────────────────
Estado              MyDevelon   Komtrax   TOTAL
────────────────────────────────────────────────────────
VERIFIED            3           0         3
SKIP_EQUAL          1           3         4
REVIEW              20          2         22
REVIEW_OLD_SOURCE   0           2         2
WOULD_UPDATE        1           0         1
NO_VALID_METER      1           1         2
CONFIG_MISSING      0           6         6
GAP:NO_HOURS        0           3         3
ERROR               0           1         1
────────────────────────────────────────────────────────
Equipos procesados  25          13        38
PUT productivos     3           0         3
```

### Fase 5/5 — ALERTAS ACCIONABLES
```text
[5/5] ALERTAS
────────────────────────────────────────────────────────────────────────────────
⚠ CONFIG_MISSING (6): 354483/MH02, 600578/MH20, 600730/MH21, 68181/CF02, 600958/MH23, 601076/MH24
   Acción: INSERT telemetry_sync_config (source=KOMTRAX, action_policy=AUTO)

⚠ GAP:NO_HOURS (3): 400293/MH04, 73180/CF01, 400726/MH05
   Razón: Komtrax no entregó CumulativeOperatingHours (retención)
   Acción: Verificar en CFM / esperar próxima ventana

⚠ NO_VALID_METER (2): DHKCEBDPCT0002715/MH46 (MyDevelon), 19144/CF05 (Komtrax)
   Acción: Crear horómetro en Fracttal (manual)

⚠ CUOTA MyDevelon: 12 min restantes
   Acción: Próximo fetch disponible ~09:55

Reporte generado: reports/sync_2026-09-25_09-42.md

✓ EJECUCIÓN COMPLETADA (exit 0)
```

---

## 5. Reporte Markdown Spec

### Naming
```
reports/sync_YYYY-MM-DD_HH-MM.md
# ej: reports/sync_2026-09-25_09-42.md
```

### Estructura
```markdown
# Fracttal Telemetry Sync — 2026-09-25 09:42:13

## Resumen Ejecutivo

| Métrica | Valor |
|---------|-------|
| Fecha/Hora | 2026-09-25 09:42:13 |
| Modo | PRODUCCIÓN (--live) |
| Duración | 42.3s |
| Exit code | 0 |
| Equipos totales | 38 |
| PUT productivos | 3 |

### Consolidado

| Estado | MyDevelon | Komtrax | Total |
|--------|-----------|---------|-------|
| VERIFIED | 3 | 0 | 3 |
| SKIP_EQUAL | 1 | 3 | 4 |
| REVIEW | 20 | 2 | 22 |
| ... | ... | ... | ... |

## Health Check

| Componente | Estado | Latencia | Detalle |
|------------|--------|----------|---------|
| Fracttal | ✓ OK | 12ms | - |
| SQL Server | ✓ OK | 3ms | - |
| MyDevelon | ⚠ DEGRADADO | - | Cuota 12min |
| Komtrax | ✓ OK | 45ms | - |
| Config | ⚠ PARCIAL | - | 6 sin config KOMTRAX |

## Detalle por Equipo

### MyDevelon

#### DHKCEBADLG0007790 / MH07
- **Fuente:** MyDevelon
- **Horómetro anterior:** 13340
- **Horómetro nuevo:** 13468.52
- **Decisión:** VERIFIED
- **Auditoría SQL:** #381
- **Fracttal confirmado:** ✓ 13468.52 @ 2026-09-25 09:42:15

#### DHKCEBADJK0008232 / MH18
- **Fuente:** MyDevelon
- **Horómetro anterior:** 4318
- **Horómetro origen:** 1437.67 (2022-11-30)
- **Decisión:** REVIEW_OLD_SOURCE
- **Razón:** Lectura origen más antigua que Fracttal
- **Acción:** No modificar Fracttal

### Komtrax

#### 354483 / MH02
- **Fuente:** Komtrax
- **Horómetro anterior:** 11594
- **Horómetro nuevo:** 11623.5
- **Decisión:** CONFIG_MISSING
- **Razón:** Sin telemetry_sync_config para KOMTRAX
- **Acción requerida:** INSERT telemetry_sync_config (source=KOMTRAX, action_policy=AUTO)

#### 400293 / MH04
- **Fuente:** Komtrax
- **Decisión:** GAP:NO_HOURS
- **Razón:** Sin CumulativeOperatingHours en respuesta (retención)
- **Acción:** Verificar en CFM / esperar próxima ventana

## Alertas Resumidas

| Tipo | Cuenta | Equipos | Acción Requerida |
|------|--------|---------|------------------|
| CONFIG_MISSING | 6 | MH02, MH20, MH21, CF02, MH23, MH24 | INSERT config KOMTRAX AUTO |
| GAP:NO_HOURS | 3 | MH04, CF01, MH05 | Verificar CFM |
| NO_VALID_METER | 2 | MH46, CF05 | Crear horómetro manual |
| CUOTA | 1 | MyDevelon | Esperar 12 min |

## Metadata

- **Modo:** PRODUCCIÓN (--live)
- **Duración total:** 42.3s
- **Exit code:** 0
- **Generado:** 2026-09-25 09:42:55
```

---

## 6. Alertas Spec — Reglas

| Alerta | Trigger | Umbral | Formato Consola | Formato Reporte |
|--------|---------|--------|-----------------|-----------------|
| **CONFIG_MISSING** | Equipo sin `telemetry_sync_config` para su source | count > 0 | `⚠ CONFIG_MISSING (N): lista` | Tabla + SQL INSERT sugerido |
| **GAP:NO_HOURS** | `classify_komtrax_gap` = `NO_HOURS` | count > 0 | `⚠ GAP:NO_HOURS (N): lista` | Tabla + razón |
| **NO_VALID_METER** | `NO_VALID_METER` en SQL | count > 0 | `⚠ NO_VALID_METER (N): lista` | Tabla + acción manual |
| **CUOTA_MYDEVELON** | `QuotaExceededError` o < 15 min | < 900s | `⚠ CUOTA MyDevelon: X min` | Timestamp próximo fetch |
| **WRITE_AMBIGUOUS** | Estado `WRITE_AMBIGUOUS` en SQL | count > 0 | `✗ WRITE_AMBIGUOUS (N)` | Tabla + reintentar |
| **HEALTH_DEGRADED** | Health check WARN | any | `⚠ DEGRADADO: componente` | En health check table |

---

## 7. Histórico Spec

### Directorio
```
reports/
├── sync_2026-09-25_09-42.md
├── sync_2026-09-24_15-30.md
├── index.json          # opcional
```

### Naming
```
sync_YYYY-MM-DD_HH-MM.md
# UTC timestamp de inicio de ejecución
```

### Retención
- **Default:** mantener últimos 90 días
- **Configurable:** `SYNC_REPORT_RETENTION_DAYS` env var

### Index.json (opcional, para futura UI)
```json
{
  "runs": [
    {
      "file": "sync_2026-09-25_09-42.md",
      "started_at": "2026-09-25T09:42:13Z",
      "finished_at": "2026-09-25T09:42:55Z",
      "mode": "LIVE",
      "exit_code": 0,
      "summary": {"total": 38, "verified": 3, "put": 3}
    }
  ]
}
```

---

## 8. Estructura de Código

```
fracttal-integration/
├── run_sync.py                    # Entry point único
├── operational/
│   ├── __init__.py
│   ├── health.py                  # Health checks
│   ├── console.py                 # Formateo consola (ANSI)
│   ├── report.py                  # Generación Markdown
│   ├── alerts.py                  # Reglas de alertas
│   ├── history.py                 # Guardado reports/ + index
│   └── orchestrator.py            # Secuencia: health → mydevelon → komtrax → report
├── run_mydevelon_sync.py          # Worker (sin cambios)
├── run_komtrax_sync.py            # Worker (sin cambios)
├── run_all_sync.py                # DEPRECADO → alias a run_sync.py
└── reports/
    ├── sync_2026-09-25_09-42.md
    ├── index.json
    └── ...
```

---

## 9. Tasks TDD (Orden de Implementación)

| Task | Qué | Test | Archivos |
|------|-----|------|----------|
| **4.1** | Health Check module | `test_health.py` | `operational/health.py` |
| **4.2** | Console formatter (ANSI, tablas) | `test_console.py` | `operational/console.py` |
| **4.3** | Alert engine | `test_alerts.py` | `operational/alerts.py` |
| **4.4** | Report generator (Markdown) | `test_report.py` | `operational/report.py` |
| **4.5** | History / reports storage | `test_history.py` | `operational/history.py` |
| **4.6** | Orchestrator (secuencia completa) | `test_orchestrator.py` | `operational/orchestrator.py` |
| **4.7** | CLI `run_sync.py` | `test_cli.py` | `run_sync.py` |
| **4.8** | Integración E2E (dry-run + live mock) | `test_integration.py` | todos |

**Regla TDD:** Cada task = test rojo → implementación mínima → verde → commit.

---

## 10. Compatibilidad y Migración

| Archivo actual | Acción |
|----------------|--------|
| `run_all_sync.py` | **Deprecado** → mantiene compatibilidad, llama a `run_sync.py` internamente |
| `run_mydevelon_sync.py` | Sin cambios (worker) |
| `run_komtrax_sync.py` | Sin cambios (worker) |
| `run_sync.py` | **Nuevo entry point único** |

**Alias de compatibilidad:**
```python
# run_all_sync.py (mantenido por compat)
from run_sync import main
if __name__ == "__main__":
    main()
```

---

## 11. Criterio de Aceptación Fase 4

- [ ] `python run_sync.py --live` ejecuta health → mydevelon → komtrax → reporte
- [ ] Consola muestra fases 1-5 con formato exacto especificado
- [ ] Health check aborta en crítico (exit 2), warn en no crítico
- [ ] Reporte Markdown generado en `reports/sync_<timestamp>.md` con estructura exacta
- [ ] Alertas accionables aparecen en consola Y reporte
- [ ] `--dry-run` usa fixtures, no hace red, genera reporte
- [ ] Exit codes: 0/2/3/4 según spec
- [ ] Suite completa (185 + nuevos) en verde
- [ ] `run_all_sync.py` sigue funcionando (compatibilidad)

---

## 12. Fuera de Alcance (Fase 5+)

- Persistencia de `sync_runs` en SQL
- Dashboard/UI para histórico
- Alertas por email/Slack/webhook
- Paralelismo async
- Configuración de umbrales via SQL
- API REST para consultar histórico

---

> **Principio rector:** *El motor no se toca. La capa operacional solo observa, orquesta, informa y diagnostica.*

## Related Skills

- **spec-driven-qa** — ciclo TDD task-by-task contra este spec
- **audit-project** — validar que el motor sigue intacto
- **telemetry-audit** — health checks read-only
- **data-quality** — motor de alertas
- **fracttal-integration** — checks Fracttal API + SQL
- **aemp-integration** — checks parsers OEM
- **python-clean-code** / **clean-*** — calidad en `operational/`
