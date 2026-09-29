# Runbook MH07 — manejo de multi-horómetro (excepción serial)

> Caso: equipo con **múltiples horómetros válidos** pero excepción de serial permitida.
> El flujo estándar exige **exactamente 1** horómetro válido; MH07 es la **única excepción** documentada.

## 1. Equipo / serial

| Campo | Valor |
|---|---|
| Código Fracttal | `MH07` |
| Serial (PIN) | `DHKCEBADLG0007790` |
| Modelo | DX225LC |

## 2. Estado actual en Fracttal (3 horómetros)

| # | Descripción | units_code | is_counter | active | serial |
|---|---|---|---|---|---|
| 1 | HOROMETRO MH07 | HRS | True | False | (vacío) |
| 2 | HOROMETRO MH07 | HRS | True | **False** | `DHKCEBADLG0007790` |
| 3 | HOROMETRO MH07 | HRS | True | **True** | (vacío) |

> Solo el #2 cumple **todas** las reglas: `units_code=HRS`, `is_counter=True`, `active=True`, **serial = equipo**. Los otros dos fallan en `active` o `serial`.

## 3. Excepción documentada en código

En `api.py` (líneas ~40, 417-419, 479) existe una **allowlist explícita**:

```python
_MISSING_METER_SERIAL_ALLOWLIST = {
    ("MH07", "1028944"),
}
```

Si el equipo es `MH07` y el meter ID es `1028944`, se permite **serial vacío** en el horómetro válido. Es la **única excepción** en todo el código base.

## 3. Verificación antes de actuar

1. En Fracttal: Activos → buscar `MH07` → pestaña horómetros/meters.
2. Confirmar que **exactamente uno** tiene:
   - `units_code = HRS`
   - `is_counter = True`
   - `active = True`
   - `serial = DHKCEBADLG0007790` (match exacto con `field_4` del equipo)
   - Sin texto `NO UTILIZAR`
   - `units_code = HRS`, `is_counter = True`, `active = True`

3. Confirmar que los otros dos están en estado `active = False` o sin serial.

## 4. Qué NO hacer

- **No crear** un nuevo horómetro: ya existe el correcto (#2).
- **No desactivar** el #2 ni el #3 a menos que operaciones lo solicite por escrito.
- No intentar "limpiar" duplicados: el código ya maneja la excepción vía `_MISSING_METER_SERIAL_ALLOWLIST`.

## 5. Verificación posterior (si se tocó algo)

```sql
SELECT id, status, decision, verification_value
FROM dbo.horometer_updates
WHERE meter_serial = 'DHKCEBADLG0007790'
ORDER BY id DESC;
```

Si MH07 procesa sin `NO_VALID_METER` ni `METER_SERIAL_MISMATCH` → OK.

## 6. Excepción en código (solo lectura)

Archivo: `api.py` líneas ~40, 417-419, 479

```python
_MISSING_METER_SERIAL_ALLOWLIST = {
    ("MH07", "1028944"),  # única entrada
}
```

En `get_valid_hourmeter` (líneas ~479, ~999):

```python
if not meter_serial:
    if (str(code).strip().upper(), str(meter.get("id")).strip()) in _MISSING_METER_SERIAL_ALLOWLIST:
        return meter
```

## Related Skills

- **telemetry-audit** — validar meter/identidad post-cambio
- **data-quality** — clasificar si reaparece `NO_VALID_METER`
- **fracttal-integration** — reglas de meters en API Fracttal

---

> **Nota**: Este runbook es **solo lectura/documentación**. No hay acción correctiva pendiente: MH07 funciona correctamente con su excepción documentada.