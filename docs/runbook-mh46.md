# Runbook MH46 — creación manual del horómetro en Fracttal

> Caso: `NO_VALID_METER` — el activo existe pero no tiene horómetro válido.
> No crear horómetros por código ni por la integración: solo manual en consola.

## 1. Equipo / serial

| Campo | Valor |
|---|---|
| Código Fracttal | `MH46` |
| Serial (PIN) | `DHKCEBDPCT0002715` |
| Modelo | DX225-7 |

## 2. Qué verificar antes de crear

1. En Fracttal: Activos → buscar `MH46` → pestaña horómetros/meters.
2. Confirmar que **no existe** un meter con `units_code=HRS`, `is_counter=true`, `active=true` y descripción sin `NO UTILIZAR`.
3. Si existe uno pero inactivo o con otra unidad: NO duplicar — revisar con el responsable del activo (la integración exige **exactamente un** horómetro válido; con 0 o con 2+ queda en `NO_VALID_METER`).
4. Anotar el valor inicial real del horómetro físico (preguntar a operaciones si no es visible).

## 3. Creación manual

En consola Fracttal, sobre el activo `MH46`, crear meter con:

| Campo | Valor exigido | Por qué |
|---|---|---|
| Descripción | `HOROMETRO MH46` | convención del resto de la flota |
| `units_code` | `HRS` | regla 1 de `get_valid_hourmeter` (`api.py`) |
| `is_counter` | `true` | regla 2 |
| `active` | `true` | regla 3 |
| `serial` del meter | `DHKCEBDPCT0002715` (= serial del equipo) | regla 6: debe coincidir con `field_4` del equipo |
| Valor inicial | lectura física real | base de comparaciones futuras |
| Sin texto `NO UTILIZAR` | — | regla 4 |

## 4. Asociación correcta

- El meter debe colgar del equipo cuyo `code` es `MH46` y cuyo `field_4` es `DHKCEBDPCT0002715`.
- Verificar que sea el **único** meter HRS activo del equipo (regla 5).

## 5. Verificación posterior

1. Releer el activo: debe mostrar 1 horómetro con el valor cargado.
2. Correr dry-run de esa máquina y esperar que **desaparezca** `NO_VALID_METER` (pasará a `REVIEW_OLD_SOURCE`, `SKIP_EQUAL` o `WOULD_UPDATE` según datos).

## 6. Cómo comprobar que deja de aparecer como `NO_VALID_METER`

```sql
SELECT TOP 5 id, status, decision, new_value
FROM dbo.horometer_updates
WHERE meter_serial = 'DHKCEBDPCT0002715'
ORDER BY id DESC;
```

Si las filas nuevas ya no dicen `NO_VALID_METER`, el caso está cerrado. No se requiere ningún cambio de código ni de configuración SQL: con el meter creado, el flujo existente lo toma solo.

## Related Skills

- **telemetry-audit** — validar meter/identidad post-alta
- **data-quality** — clasificar si reaparece `NO_VALID_METER`
- **fracttal-integration** — reglas de meters en API Fracttal
