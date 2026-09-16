from datetime import datetime, timezone

from mydevelon import (
    get_access_token as get_mydevelon_access_token,
    get_fleet_xml,
    parse_fleet_xml,
)

from api import (
    get_access_token as get_fracttal_access_token,
    get_equipment_by_serial,
    get_valid_hourmeter,
)

from database import get_machinery_by_serial


# ============================================================
# CONFIGURACIÓN DE REGLAS
# ============================================================

TARGET_OEM = "DEVELON"

# DRY RUN:
# True  = no escribe en Fracttal
# False = permite escritura cuando corresponda
DRY_RUN = True

# Desfase temporal máximo permitido para una actualización
# automática.
#
# IMPORTANTE:
# Este valor NO corresponde a la diferencia de horas de
# funcionamiento.
#
# Corresponde al tiempo transcurrido entre:
#
#   fecha lectura MyDevelon
#   -
#   fecha último dato Fracttal
#
# Ejemplo:
#
# MyDevelon: 15/09 18:00
# Fracttal:  15/09 16:00
# Desfase:   2 h
# -> UPDATE si MyDevelon tiene más horas.
#
# Si el desfase temporal es mayor a 48 h:
# -> REVIEW
#
MAX_SOURCE_FRACTTAL_GAP_HOURS = 48.0


# ============================================================
# UTILIDADES
# ============================================================

def normalize_serial(value):
    """
    Normaliza un serial/PIN para comparación.
    """
    if value is None:
        return ""

    return str(value).strip().upper()


def parse_datetime(value):
    """
    Convierte ISO 8601 a datetime con timezone.
    """
    if not value:
        return None

    value = str(value).strip()

    try:

        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None or dt.utcoffset() is None:
            return None

        return dt

    except ValueError:
        return None


def format_hours(value):
    """
    Formato amigable para horas.
    """
    if value is None:
        return "N/D"

    return f"{float(value):,.2f}"


def format_datetime(value):
    """
    Devuelve fecha o N/D.
    """
    if not value:
        return "N/D"

    return str(value)


# ============================================================
# DECISIÓN AUTOMÁTICA
# ============================================================

def decide_action(
    source_hours,
    source_datetime,
    fracttal_hours,
    fracttal_datetime,
    active,
):
    """
    Determina automáticamente la acción.

    Reglas:

    1. Sin lectura de horas desde MyDevelon
       -> ERROR_SOURCE_HOURS

    2. Sin valor actual en Fracttal
       -> ERROR_FRACTTAL_HOURS

    3. Sin fecha de lectura MyDevelon
       -> REVIEW_SOURCE_DATE

    4. Fuente con más de 48 horas
       -> REVIEW_OLD_SOURCE

    5. MyDevelon tiene menos horas que Fracttal
       -> REVIEW_INCONSISTENCY

    6. MyDevelon tiene exactamente las mismas horas
       -> SKIP_EQUAL

    7. MyDevelon tiene más horas y la fuente es reciente
       -> UPDATE

    El límite de 48 h corresponde a la antigüedad de la lectura
    OEM respecto del momento actual.
    """

    # --------------------------------------------------------
    # 1. SIN HORAS FUENTE
    # --------------------------------------------------------

    if source_hours is None:
        return "ERROR_SOURCE_HOURS"

    # --------------------------------------------------------
    # 2. SIN HORAS FRACTTAL
    # --------------------------------------------------------

    if fracttal_hours is None:
        return "ERROR_FRACTTAL_HOURS"

    # --------------------------------------------------------
    # 3. SIN FECHA FUENTE
    # --------------------------------------------------------

    if source_datetime is None:
        return "REVIEW_SOURCE_DATE"

    source_age_hours = (
        datetime.now(timezone.utc)
        - source_datetime
    ).total_seconds() / 3600.0

    if source_age_hours > MAX_SOURCE_FRACTTAL_GAP_HOURS:
        return "REVIEW_OLD_SOURCE"

    if source_age_hours < -(5.0 / 60.0):
        return "REVIEW_SOURCE_DATE"

    # --------------------------------------------------------
    # 4. COMPARAR HORAS
    # --------------------------------------------------------

    source_hours = float(source_hours)
    fracttal_hours = float(fracttal_hours)

    difference = (
        source_hours
        - fracttal_hours
    )

    if difference < 0:
        return "REVIEW_INCONSISTENCY"

    if difference == 0:
        return "SKIP_EQUAL"

    return "UPDATE"


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 100)
    print("TEST MYDEVELON -> SQL SERVER -> FRACTTAL")
    print("REGLAS AUTOMÁTICAS - DRY RUN")
    print("=" * 100)

    print()
    print(
        f"Desfase temporal máximo para UPDATE automático: "
        f"{MAX_SOURCE_FRACTTAL_GAP_HOURS:.2f} h"
    )

    # ========================================================
    # 1. MYDEVELON TOKEN
    # ========================================================

    print()
    print("1. MYDEVELON")
    print("-" * 100)

    print("Obteniendo token...")

    mydevelon_token = get_mydevelon_access_token()

    print("[OK] Token MyDevelon obtenido.")

    # ========================================================
    # 2. MYDEVELON FLEET
    # ========================================================

    print()
    print("2. FLEET MYDEVELON")
    print("-" * 100)

    print("Consultando Fleet...")

    xml_text = get_fleet_xml(
        token=mydevelon_token,
    )

    fleet = parse_fleet_xml(
        xml_text
    )

    print(
        f"[OK] Equipos recibidos: "
        f"{len(fleet)}"
    )

    fleet_develon = [
        equipment
        for equipment in fleet
        if str(
            equipment.get("oem_name", "")
        ).strip().upper() == TARGET_OEM
    ]

    print(
        f"[OK] Equipos {TARGET_OEM}: "
        f"{len(fleet_develon)}"
    )

    # ========================================================
    # 3. FRACTTAL TOKEN
    # ========================================================

    print()
    print("3. FRACTTAL")
    print("-" * 100)

    print("Obteniendo token...")

    fracttal_token = get_fracttal_access_token()

    print("[OK] Token Fracttal obtenido.")

    # ========================================================
    # 4. PROCESAMIENTO
    # ========================================================

    print()
    print("4. PROCESAMIENTO")
    print("-" * 100)

    results = []

    for index, source in enumerate(
        fleet_develon,
        start=1,
    ):

        print()
        print("=" * 100)
        print(
            f"EQUIPO {index}/{len(fleet_develon)}"
        )
        print("=" * 100)

        # ----------------------------------------------------
        # DATOS MYDEVELON
        # ----------------------------------------------------

        source_oem = source.get(
            "oem_name"
        )

        source_model = source.get(
            "model"
        )

        source_equipment_id = source.get(
            "equipment_id"
        )

        source_serial_number = source.get(
            "serial_number"
        )

        source_pin = normalize_serial(
            source.get("pin")
        )

        source_hours = source.get(
            "operating_hours"
        )

        source_datetime_raw = source.get(
            "operating_hours_datetime"
        )

        source_datetime = parse_datetime(
            source_datetime_raw
        )

        print()
        print("MYDEVELON")

        print(
            f"OEM:             "
            f"{source_oem}"
        )

        print(
            f"Modelo:          "
            f"{source_model}"
        )

        print(
            f"Equipment ID:    "
            f"{source_equipment_id}"
        )

        print(
            f"Serial Number:   "
            f"{source_serial_number}"
        )

        print(
            f"PIN:             "
            f"{source_pin}"
        )

        print(
            f"Horómetro:       "
            f"{format_hours(source_hours)} h"
        )

        print(
            f"Fecha lectura:   "
            f"{format_datetime(source_datetime_raw)}"
        )

        # ----------------------------------------------------
        # VALIDAR PIN
        # ----------------------------------------------------

        if not source_pin:

            print()
            print(
                "[ERROR] MyDevelon no entregó PIN."
            )

            results.append({
                "action": "ERROR_NO_PIN",
                "pin": "",
                "source_hours": source_hours,
                "fracttal_hours": None,
                "difference": None,
            })

            continue

        # ----------------------------------------------------
        # SQL SERVER
        # ----------------------------------------------------

        print()
        print("SQL SERVER")

        machinery = get_machinery_by_serial(
            source_pin
        )

        if not machinery:

            print(
                "[NO_MATCH_SQL] No existe maquinaria "
                f"con serial/PIN {source_pin}"
            )

            results.append({
                "action": "NO_MATCH_SQL",
                "pin": source_pin,
                "source_hours": source_hours,
                "fracttal_hours": None,
                "difference": None,
            })

            continue

        machinery_id = machinery.get(
            "id"
        )

        machinery_serial = machinery.get(
            "serial"
        )

        machinery_code = machinery.get(
            "equipment_code"
        )

        machinery_name = machinery.get(
            "name"
        )

        machinery_manufacturer = machinery.get(
            "manufacturer"
        )

        machinery_model = machinery.get(
            "model"
        )

        machinery_active = machinery.get(
            "active"
        )

        print(
            f"SQL ID:           "
            f"{machinery_id}"
        )

        print(
            f"Código:           "
            f"{machinery_code}"
        )

        print(
            f"Serial:           "
            f"{machinery_serial}"
        )

        print(
            f"Nombre:           "
            f"{machinery_name}"
        )

        print(
            f"Fabricante:       "
            f"{machinery_manufacturer}"
        )

        print(
            f"Modelo:           "
            f"{machinery_model}"
        )

        print(
            f"Activo:           "
            f"{machinery_active}"
        )

        # ----------------------------------------------------
        # VALIDAR SERIAL
        # ----------------------------------------------------

        if (
            normalize_serial(machinery_serial)
            != source_pin
        ):

            print()
            print(
                "[ERROR] PIN MyDevelon != serial SQL"
            )

            results.append({
                "action": "SERIAL_MISMATCH_SQL",
                "pin": source_pin,
                "source_hours": source_hours,
                "fracttal_hours": None,
                "difference": None,
            })

            continue

        print(
            "[OK] PIN MyDevelon = serial SQL"
        )

        # ----------------------------------------------------
        # FRACTTAL
        # ----------------------------------------------------

        print()
        print("FRACTTAL")

        fracttal_equipment = get_equipment_by_serial(
            fracttal_token,
            normalize_serial(machinery_serial),
        )

        if not fracttal_equipment:

            print(
                "[NO_MATCH_FRACTTAL] No se encontró "
                "el activo por serial."
            )

            results.append({
                "action": "NO_MATCH_FRACTTAL",
                "pin": source_pin,
                "sql_code": machinery_code,
                "source_hours": source_hours,
                "fracttal_hours": None,
                "difference": None,
            })

            continue

        fracttal_code = fracttal_equipment.get(
            "code"
        )

        fracttal_name = fracttal_equipment.get(
            "field_1"
        )

        fracttal_manufacturer = fracttal_equipment.get(
            "field_2"
        )

        fracttal_model = fracttal_equipment.get(
            "field_3"
        )

        fracttal_serial = fracttal_equipment.get(
            "field_4"
        )

        print(
            f"Código:           "
            f"{fracttal_code}"
        )

        print(
            f"Nombre:           "
            f"{fracttal_name}"
        )

        print(
            f"Fabricante:       "
            f"{fracttal_manufacturer}"
        )

        print(
            f"Modelo:           "
            f"{fracttal_model}"
        )

        print(
            f"Serial:           "
            f"{fracttal_serial}"
        )

        # ----------------------------------------------------
        # VALIDAR SERIAL FRACTTAL
        # ----------------------------------------------------

        if (
            normalize_serial(fracttal_serial)
            != normalize_serial(machinery_serial)
        ):

            print()
            print(
                "[ERROR] Serial SQL != serial Fracttal"
            )

            results.append({
                "action": "SERIAL_MISMATCH_FRACTTAL",
                "pin": source_pin,
                "sql_code": machinery_code,
                "fracttal_code": fracttal_code,
                "source_hours": source_hours,
                "fracttal_hours": None,
                "difference": None,
            })

            continue

        print(
            "[OK] Serial SQL = serial Fracttal"
        )

        # ----------------------------------------------------
        # HORÓMETRO FRACTTAL
        # ----------------------------------------------------

        print()
        print("HORÓMETRO FRACTTAL")

        try:

            meter = get_valid_hourmeter(
                fracttal_token,
                fracttal_equipment,
            )

        except Exception as exc:

            print(
                "[REVIEW] No fue posible determinar "
                "automáticamente el horómetro."
            )

            print(
                f"Detalle: {exc}"
            )

            results.append({
                "action": "REVIEW",
                "pin": source_pin,
                "sql_code": machinery_code,
                "fracttal_code": fracttal_code,
                "source_hours": source_hours,
                "fracttal_hours": None,
                "difference": None,
                "reason": str(exc),
            })

            continue

        if not meter:

            print(
                "[NO_HOROMETER] No existe horómetro "
                "válido."
            )

            results.append({
                "action": "NO_HOROMETER",
                "pin": source_pin,
                "sql_code": machinery_code,
                "fracttal_code": fracttal_code,
                "source_hours": source_hours,
                "fracttal_hours": None,
                "difference": None,
            })

            continue

        meter_id = meter.get(
            "id"
        )

        meter_description = meter.get(
            "description"
        )

        meter_serial = meter.get(
            "serial"
        )

        meter_units = meter.get(
            "units_code"
        )

        meter_is_counter = meter.get(
            "is_counter"
        )

        last_data = meter.get(
            "last_data"
        ) or {}

        fracttal_last_value = last_data.get(
            "value"
        )
        fracttal_counter_value = fracttal_last_value

        fracttal_last_datetime_raw = last_data.get(
            "date"
        )

        fracttal_last_datetime = parse_datetime(
            fracttal_last_datetime_raw
        )

        print(
            f"ID:               "
            f"{meter_id}"
        )

        print(
            f"Descripción:      "
            f"{meter_description}"
        )

        print(
            f"Serial:           "
            f"{meter_serial}"
        )

        print(
            f"Unidad:           "
            f"{meter_units}"
        )

        print(
            f"Contador:         "
            f"{meter_is_counter}"
        )

        print(
            f"Counter value:    "
            f"{format_hours(fracttal_counter_value)}"
        )

        print(
            f"Último valor:     "
            f"{format_hours(fracttal_last_value)}"
        )

        print(
            f"Fecha último dato: "
            f"{format_datetime(fracttal_last_datetime_raw)}"
        )

        # ----------------------------------------------------
        # VALIDACIONES DEL METER
        # ----------------------------------------------------

        if meter_units != "HRS":

            print(
                "[REVIEW] El meter no tiene unidad HRS."
            )

            results.append({
                "action": "REVIEW",
                "pin": source_pin,
                "sql_code": machinery_code,
                "fracttal_code": fracttal_code,
                "source_hours": source_hours,
                "fracttal_hours": fracttal_counter_value,
                "difference": None,
                "reason": "Meter sin unidad HRS",
            })

            continue

        if meter_is_counter is not True:

            print(
                "[REVIEW] El meter no es contador."
            )

            results.append({
                "action": "REVIEW",
                "pin": source_pin,
                "sql_code": machinery_code,
                "fracttal_code": fracttal_code,
                "source_hours": source_hours,
                "fracttal_hours": fracttal_counter_value,
                "difference": None,
                "reason": "Meter no es contador",
            })

            continue

        if "NO UTILIZAR" in str(
            meter_description or ""
        ).upper():

            print(
                "[REVIEW] Meter marcado como "
                "'NO UTILIZAR'."
            )

            results.append({
                "action": "REVIEW",
                "pin": source_pin,
                "sql_code": machinery_code,
                "fracttal_code": fracttal_code,
                "source_hours": source_hours,
                "fracttal_hours": fracttal_counter_value,
                "difference": None,
                "reason": "Meter NO UTILIZAR",
            })

            continue

        # ----------------------------------------------------
        # DECISIÓN
        # ----------------------------------------------------

        action = decide_action(
            source_hours=source_hours,
            source_datetime=source_datetime,
            fracttal_hours=fracttal_counter_value,
            fracttal_datetime=fracttal_last_datetime,
            active=machinery_active,
        )

        # ----------------------------------------------------
        # DIFERENCIA DE HORAS
        # ----------------------------------------------------

        difference = None

        if (
            source_hours is not None
            and fracttal_counter_value is not None
        ):

            difference = (
                float(source_hours)
                - float(fracttal_counter_value)
            )

        # ----------------------------------------------------
        # DESFASE TEMPORAL
        # ----------------------------------------------------

        gap_hours = None

        if (
            source_datetime is not None
            and fracttal_last_datetime is not None
        ):

            gap_hours = (
                source_datetime
                - fracttal_last_datetime
            ).total_seconds() / 3600.0

        # ----------------------------------------------------
        # COMPARACIÓN
        # ----------------------------------------------------

        print()
        print("COMPARACIÓN")
        print("-" * 100)

        print(
            f"MyDevelon:        "
            f"{format_hours(source_hours)} h"
        )

        print(
            f"Fracttal:         "
            f"{format_hours(fracttal_counter_value)} h"
        )

        print(
            f"Diferencia:       "
            f"{format_hours(difference)} h"
        )

        print(
            f"Fecha MyDevelon:   "
            f"{format_datetime(source_datetime_raw)}"
        )

        print(
            f"Fecha Fracttal:    "
            f"{format_datetime(fracttal_last_datetime_raw)}"
        )

        if gap_hours is not None:

            print(
                f"Desfase temporal:  "
                f"{gap_hours:.2f} h"
            )

            print(
                f"Límite automático: "
                f"{MAX_SOURCE_FRACTTAL_GAP_HOURS:.2f} h"
            )

        else:

            print(
                "Desfase temporal:  N/D"
            )

        print()
        print(
            f"DECISIÓN:          {action}"
        )

        # ----------------------------------------------------
        # MENSAJES SEGÚN RESULTADO
        # ----------------------------------------------------

        if action == "UPDATE":

            if DRY_RUN:

                print(
                    "[DRY RUN] SE ACTUALIZARÍA FRACTTAL"
                )

            else:

                print(
                    "[UPDATE] Se actualizaría FRACTTAL."
                )

        elif action == "REVIEW_OLD_SOURCE":

            print(
                "[REVIEW] El equipo requiere "
                "revisión manual."
            )

            if gap_hours is not None:

                print(
                    f"[REVIEW] Desfase temporal: "
                    f"{gap_hours:.2f} h"
                )

                print(
                    f"[REVIEW] Límite automático: "
                    f"{MAX_SOURCE_FRACTTAL_GAP_HOURS:.2f} h"
                )

        elif action == "SKIP_EQUAL":

            print(
                "[SKIP] El valor ya está actualizado."
            )

        elif action == "REVIEW_INCONSISTENCY":

            print(
                "[REVIEW_INCONSISTENCY] La fuente tiene menos "
                "horas que Fracttal."
            )

        # ----------------------------------------------------
        # RESULTADO
        # ----------------------------------------------------

        results.append({
            "action": action,
            "pin": source_pin,
            "sql_code": machinery_code,
            "fracttal_code": fracttal_code,
            "source_hours": source_hours,
            "fracttal_hours": fracttal_counter_value,
            "difference": difference,
            "gap_hours": gap_hours,
            "source_datetime": source_datetime_raw,
            "fracttal_datetime": fracttal_last_datetime_raw,
        })

    # ========================================================
    # RESUMEN
    # ========================================================

    print()
    print()
    print("=" * 100)
    print("RESUMEN GENERAL")
    print("=" * 100)

    counts = {}

    for result in results:

        action = result.get(
            "action",
            "UNKNOWN",
        )

        counts[action] = (
            counts.get(action, 0) + 1
        )

    for action, count in sorted(
        counts.items()
    ):

        print(
            f"{action:<30} {count}"
        )

    # ========================================================
    # DETALLE
    # ========================================================

    print()
    print("=" * 100)
    print("DETALLE FINAL")
    print("=" * 100)

    print(
        f"{'ACCIÓN':<25}"
        f"{'PIN':<25}"
        f"{'FRACTTAL':<10}"
        f"{'MYDEV':>12}"
        f"{'FRACTTAL':>12}"
        f"{'DIF.':>12}"
    )

    print("-" * 100)

    for result in results:

        action = str(
            result.get("action", "")
        )

        pin = str(
            result.get("pin", "")
        )

        fracttal_code = str(
            result.get("fracttal_code", "")
        )

        source_hours = result.get(
            "source_hours"
        )

        fracttal_hours = result.get(
            "fracttal_hours"
        )

        difference = result.get(
            "difference"
        )

        print(
            f"{action:<25}"
            f"{pin:<25}"
            f"{fracttal_code:<10}"
            f"{format_hours(source_hours):>12}"
            f"{format_hours(fracttal_hours):>12}"
            f"{format_hours(difference):>12}"
        )

    # ========================================================
    # SEGURIDAD
    # ========================================================

    print()
    print("=" * 100)

    if DRY_RUN:

        print(
            "DRY RUN = TRUE"
        )

        print(
            "NO SE REALIZARON ESCRITURAS EN FRACTTAL."
        )

    else:

        print(
            "DRY RUN = FALSE"
        )

        print(
            "ATENCIÓN: el modo de escritura aún no "
            "está implementado en este script."
        )

    print("=" * 100)
    print("TEST FINALIZADO")
    print("=" * 100)


if __name__ == "__main__":
    main()