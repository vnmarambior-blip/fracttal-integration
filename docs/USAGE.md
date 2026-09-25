# fracttal-integration — Guía de Uso en Producción

> Hourmeter telemetry sync: **MyDevelon / Komtrax → SQL Server (audit + idempotency) → Fracttal**

---

## 1. Preparación

```bash
# Abrir en VS Code
File → Open Folder → C:\Users\vn246\Documents\Code\fracttal-integration

# Activar venv (terminal integrada Ctrl+ñ)
.\.venv\Scripts\Activate.ps1

# Verificar dependencias
pip install -r requirements.txt
```

### Archivo `.env` (obligatorio, local, gitignored)

```env
FRACTTAL_CLIENT_ID=xxx
FRACTTAL_CLIENT_SECRET=xxx
MYDEVELON_CLIENT_ID=xxx
MYDEVELON_CLIENT_SECRET=xxx
KOMTRAX_CLIENT_ID=xxx
KOMTRAX_CLIENT_SECRET=xxx
SQL_CONNECTION_STRING=Server=...;Database=FracttalIntegration;...
SYNC_DRY_RUN=false
```

> **Producción real** = `SYNC_DRY_RUN=false`. Por defecto es `true` (dry-run).

---

## 2. Comandos de Ejecución

### Comando único (recomendado) — **DRY-RUN por defecto (seguro)**
```bash
# DRY-RUN: fixtures, cero PUTs — DEFAULT
python run_all_sync.py

# PRODUCCIÓN (ambos en vivo) — requiere --live explícito
python run_all_sync.py --live [--report ejecucion_YYYYMMDD.md]

# Simulación explícita
python run_all_sync.py --dry-run
```

### Comandos individuales (alternativa)
```bash
# A) MyDevelon → Fracttal (cuota 15 min)
python run_mydevelon_sync.py --live [--report ejecucion_YYYYMMDD.md]

# B) Komtrax → Fracttal (cuota 5 min por URL)
python run_komtrax_sync.py --live [--report komtrax_YYYYMMDD.md]
```

> El comando único `run_all_sync.py` ejecuta **MyDevelon primero**, espera a que termine, luego **Komtrax**.
> **Por defecto es DRY-RUN** (fixtures, cero PUTs). Producción solo con `--live` explícito.

### Modo Dry-Run (seguro, por defecto)
```bash
python run_mydevelon_sync.py        # usa fixture local, 0 red
python run_komtrax_sync.py          # requiere --fleet-xml o --live
```

> **Semántica dry_run (proyecto):** `dry_run=True` = ningún PUT/POST/PATCH/DELETE a Fracttal; SQL solo recibe filas `WOULD_UPDATE`/revisión. `dry_run=False` = flujo P1.1 completo con PUT.

---

## 3. Qué Ejecuta Cada Comando

| Comando | Flujo |
|---------|-------|
| `run_mydevelon_sync.py --live` | MyDevelon Fleet → parser → SQL upsert maquinaria → `process_equipment(source="MyDevelon")` → P1.1 intent → PUT Fracttal → GET verificación → SQL audit |
| `run_komtrax_sync.py --live` | Komtrax Fleet (todas las páginas) → parser namespace-agnóstico → SQL upsert maquinaria → `process_equipment(source="Komtrax")` → P1.1 intent → PUT Fracttal → GET verificación → SQL audit |

**Ambos usan el MISMO path canónico:** `api.process_equipment(...)` con idempotencia P1.1.

---

## 4. Entregables / Resultados

| Entregable | Dónde |
|------------|-------|
| **Resumen en consola** | Tabla final con conteos por estado |
| **Auditoría SQL** | `dbo.horometer_updates` (una fila por intención) |
| **Fracttal** | Lecturas de horómetro actualizadas (si `VERIFIED`) |
| **Archivos de reporte** | `--report archivo.md` (opcional) |

---

## 5. Dónde Ver Cada Resultado

### Consola (stdout) — tiempo real
```
============================================================
PROCESANDO SERIAL: DHKCEBADLG0007790
============================================================
[OK] Equipo encontrado
[OK] Maquinaria actualizada por serial
[OK] Horómetro encontrado
Valor MyDevelon: 13468.52
Acción: UPDATE
[UPDATE] 13340 -> 13468.52
[OK] Horómetro actualizado correctamente.
[OK] Auditoría del horómetro guardada en SQL Server
[RESULTADO] DHKCEBADLG0007790: VERIFIED
...
============================================================
RESUMEN FINAL
============================================================
Procesados: 25
VERIFIED: 3
SKIP_EQUAL: 1
REVIEW_OLD_SOURCE: 18
WOULD_UPDATE: 0
ERROR: 0
PUT/POST/PATCH/DELETE productivos: 3
```

### SQL — `dbo.horometer_updates` (fuente de verdad)
```sql
SELECT TOP 20 id, serial, status, write_status, decision, 
       old_value, new_value, verification_value, verification_status,
       source, created_at
FROM dbo.horometer_updates
ORDER BY id DESC;
```
- **Una fila por intención** (no duplicados, P1.1).
- `event_id` = `id` de esta tabla.

### Fracttal — Consola web
- **Activos → Horómetros** → ver valor actualizado + timestamp.
- Coincide con `verification_value` en SQL si `VERIFIED`.

### Archivos de reporte (opcional)
```bash
python run_mydevelon_sync.py --live --report ejecucion_20260925.md
python run_komtrax_sync.py --live --report komtrax_20260925.md
```

---

## 6. Significado de Cada Estado

| Estado | Significado | Acción |
|--------|-------------|--------|
| **VERIFIED** | PUT ejecutado + GET confirmó valor en Fracttal ✅ | Nada; éxito total |
| **SKIP_EQUAL** | Valor origen = Fracttal (normalizado 2 dec) | Nada; no-op idempotente |
| **WOULD_UPDATE** | `dry_run=true` y origen > Fracttal | En dry-run; en prod → VERIFIED |
| **REVIEW_OLD_SOURCE** | Origen más antiguo que Fracttal | Revisar: lectura vieja no actualiza |
| **REVIEW_INCONSISTENCY** | Gap en datos origen (ej. sin horas) | Revisar fuente |
| **CONFIG_REVIEW** | Máquina sin config de telemetría o policy ≠ AUTO | Dar de alta config en SQL |
| **SYNC_DISABLED** | Telemetría deshabilitada para ese activo | Habilitar en SQL si corresponde |
| **NO_VALID_METER** | Activo sin horómetro válido en Fracttal | Crear horómetro en Fracttal (manual) |
| **ERROR / ERROR_UNEXPECTED** | Excepción no controlada | Ver log/consola; revisar máquina |
| **WRITE_AMBIGUOUS** | PUT enviado pero GET falló (no se sabe si aplicó) | Re-ejecutar; idempotencia reusa `event_id` |
| **ERROR_RETRYABLE** | 429/5xx/timeout con PUT ya enviado | Reintentar automático (backoff) |

---

## 7. Cómo Comprobar que Terminó Correctamente

**En consola:**
- Ver `RESUMEN FINAL` con conteos.
- `ERROR: 0` y `WRITE_AMBIGUOUS: 0` = limpio.
- `PUT/POST/PATCH/DELETE productivos: N` = N escrituras reales.

**En SQL:**
```sql
-- Verificar que no hay estados problemáticos pendientes
SELECT status, COUNT(*) 
FROM dbo.horometer_updates 
WHERE created_at >= DATEADD(hour, -1, GETUTCDATE())
GROUP BY status;

-- Confirmar VERIFIED con evidencia
SELECT id, serial, new_value, verification_value, verification_status
FROM dbo.horometer_updates
WHERE status = 'VERIFIED' AND verification_status = 'PASS'
ORDER BY id DESC;
```

**En Fracttal:**
- Spot-check 2-3 máquinas `VERIFIED`: valor en Fracttal = `verification_value`.

---

## 8. Qué Hacer si una Máquina Falla

| Situación | Qué Hacer |
|-----------|-----------|
| **CONFIG_REVIEW / CONFIG_MISSING** | `INSERT INTO telemetry_sync_config (machinery_id, telemetry_source, sync_enabled, action_policy, comparison_basis, reason) VALUES (<id>, 'MyDevelon'\|'Komtrax', 1, 'AUTO', 'LAST_DATA_VALUE', 'Producción');` |
| **NO_VALID_METER** | En Fracttal: Activos → <código> → Horómetros → Nuevo horómetro → serial = PIN/SerialNumber |
| **REVIEW_OLD_SOURCE** | Verificar si la lectura origen es correcta; si es dato histórico legítimo, decidir manualmente |
| **WRITE_AMBIGUOUS** | Re-ejecutar el mismo comando; idempotencia reusa `event_id` y reintenta |
| **ERROR_UNEXPECTED** | Ver traceback en consola → abrir issue / revisar logs |
| **Fleet 200/0 bytes (MyDevelon)** | Esperar >15 min (cuota) y reintentar; o usar fixture `--fleet-xml fixtures/...` |

---

## 9. Checklist Rápido Antes de Producción

- [ ] `.env` con credenciales reales + `SYNC_DRY_RUN=false`
- [ ] SQL Server accesible (local o remoto con VPN/tunnel)
- [ ] CF05 dado de alta en Fracttal (requisito previo Komtrax 13/13)
- [ ] Config KOMTRAX creada en SQL para las 6 máquinas bloqueadas
- [ ] Ejecutar **MyDevelon primero**, luego **Komtrax**
- [ ] Guardar reporte: `--report ejecucion_YYYYMMDD.md`

---

## 10. Estado del Proyecto

- ✅ Suite: **185 tests passed**
- ✅ Gates críticos: **R0, H1, R14 cerrados**
- ✅ Seguridad: **SEGURO PARA REPOSITORIO**
- ✅ Git: **privado en `https://github.com/vnmarambior-blip/fracttal-integration.git`**
- ✅ Docs vinculados a skills en markdowns clave

---

> **Proyecto completo, testeado, auditado y listo para producción.**