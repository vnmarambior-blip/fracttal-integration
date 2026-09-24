import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from api import (
    get_access_token as get_fracttal_token,
    get_equipment_by_serial,
    get_current_hourmeter,
)
from database import (
    get_machinery_by_serial,
    get_telemetry_sync_config
)
from mydevelon import AEMP_NAMESPACE


XML_FILE = "mydevelon_fleet_minutes.xml"
TARGET_OEM = "DEVELON"

# La antigüedad de la lectura sí limita la automatización.
# El delta entre MyDevelon y Fracttal NO la limita.
MAX_SOURCE_AGE_HOURS = 48.0
ALLOW_OLD_SOURCE_UPDATES = (
    os.getenv("ALLOW_OLD_SOURCE_UPDATES", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)


def normalize_serial(value):
    if value is None:
        return None

    value = str(value).strip().upper()

    return value if value else None


def parse_datetime(value):
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


def format_datetime(dt):
    if dt is None:
        return "-"

    return dt.astimezone(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def format_hours(value):
    if value is None:
        return "-"

    try:
        return f"{float(value):,.2f}"

    except (TypeError, ValueError):
        return str(value)


def safe_float(value):
    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def calculate_source_age_hours(source_datetime):
    if source_datetime is None:
        return None

    now = datetime.now(timezone.utc)

    return (
        now - source_datetime
    ).total_seconds() / 3600.0


def parse_mydevelon_fleet(xml_file):

    print(f"Leyendo XML: {xml_file}")

    if not os.path.exists(xml_file):
        raise FileNotFoundError(
            f"No se encontró el archivo: {xml_file}"
        )

    tree = ET.parse(xml_file)
    root = tree.getroot()

    snapshot_time = parse_datetime(
        root.attrib.get("snapshotTime")
    )
    retrieved_at = datetime.now(timezone.utc)

    equipment_list = []

    for equipment in root.findall(
        "aemp:Equipment",
        AEMP_NAMESPACE
    ):

        header = equipment.find(
            "aemp:EquipmentHeader",
            AEMP_NAMESPACE
        )

        if header is None:
            continue

        def header_text(tag):

            element = header.find(
                f"aemp:{tag}",
                AEMP_NAMESPACE
            )

            if element is None:
                return None

            if element.text is None:
                return None

            return element.text.strip()

        oem = header_text("OEMName")
        model = header_text("Model")
        equipment_id = header_text("EquipmentID")
        serial_number = header_text("SerialNumber")
        pin = header_text("PIN")

        operating_hours = None
        operating_hours_datetime = None

        element = equipment.find(
            "aemp:CumulativeOperatingHours",
            AEMP_NAMESPACE
        )

        if element is not None:

            operating_hours_datetime = parse_datetime(
                element.attrib.get("datetime")
            )

            hour_element = element.find(
                "aemp:Hour",
                AEMP_NAMESPACE
            )

            if hour_element is not None:
                operating_hours = safe_float(
                    hour_element.text
                )

        equipment_list.append({
            "oem": oem,
            "model": model,
            "equipment_id": equipment_id,
            "serial_number": serial_number,
            "pin": pin,
            "operating_hours": operating_hours,
            "operating_hours_datetime":
                operating_hours_datetime,
            "snapshot_time": snapshot_time,
            "retrieved_at": retrieved_at,
        })

    return equipment_list


def decide_action(
    source_hours,
    source_datetime,
    fracttal_hours,
):

    # MyDevelon no entregó horómetro.
    if source_hours is None:
        return "ERROR_SOURCE_HOURS"

    # No podemos validar la antigüedad de la lectura.
    if source_datetime is None:
        return "REVIEW_SOURCE_DATE"

    source_age_hours = calculate_source_age_hours(
        source_datetime
    )

    if source_age_hours is None:
        return "REVIEW_SOURCE_DATE"

    if source_age_hours < -(5.0 / 60.0):
        return "REVIEW_SOURCE_DATE"

    # La fuente debe ser suficientemente reciente.
    if (
        source_age_hours > MAX_SOURCE_AGE_HOURS
        and not ALLOW_OLD_SOURCE_UPDATES
    ):
        return "REVIEW_OLD_SOURCE"

    # No existe un valor válido en Fracttal.
    if fracttal_hours is None:
        return "REVIEW_FRACTTAL_HOURS"

    difference = (
        float(source_hours)
        - float(fracttal_hours)
    )

    # Ambos sistemas tienen el mismo valor.
    if difference == 0:
        return "SKIP_EQUAL"

    # MyDevelon tiene más horas que Fracttal.
    #
    # MyDevelon es la fuente de verdad.
    # Si la lectura es fresca, se actualiza aunque
    # exista un delta grande.
    if difference > 0:
        return "UPDATE"

    # Una reducción automática queda bloqueada para revisión.
    return "REVIEW_INCONSISTENCY"


def main():

    print("=" * 80)
    print("AUDITORÍA MYDEVELON → FRACTTAL")
    print("=" * 80)

    print(f"XML: {XML_FILE}")
    print(f"OEM objetivo: {TARGET_OEM}")

    print(
        f"Antigüedad máxima fuente: "
        f"{MAX_SOURCE_AGE_HOURS:.2f} h"
    )

    print("FUENTE DE VERDAD: MYDEVELON")
    print("MODO: SOLO LECTURA")

    print("=" * 80)

    fleet = parse_mydevelon_fleet(XML_FILE)

    print(
        f"\n[MYDEVELON] Equipos encontrados: "
        f"{len(fleet)}"
    )

    fleet = [
        item
        for item in fleet
        if str(item["oem"] or "").upper()
        == TARGET_OEM
    ]

    print(
        f"[MYDEVELON] Equipos {TARGET_OEM}: "
        f"{len(fleet)}"
    )

    print("\nObteniendo token Fracttal...")

    fracttal_token = get_fracttal_token()

    print("[OK] Token Fracttal obtenido.")

    counters = {
        "MYDEVELON_TOTAL": len(fleet),
        "MATCH_SERIAL": 0,
        "NO_MATCH_SERIAL": 0,
        "NO_FRACTTAL_EQUIPMENT": 0,
        "NO_VALID_METER": 0,
        "UPDATE": 0,
        "REVIEW_INCONSISTENCY": 0,
        "REVIEW_OLD_SOURCE": 0,
        "REVIEW_SOURCE_DATE": 0,
        "REVIEW_FRACTTAL_HOURS": 0,
        "SKIP_EQUAL": 0,
        "ERROR": 0,
    }

    for source in fleet:

        pin = normalize_serial(source["pin"])

        source_hours = source["operating_hours"]

        source_datetime = source[
            "operating_hours_datetime"
        ]

        source_age_hours = calculate_source_age_hours(
            source_datetime
        )

        print("\n")
        print("-" * 80)

        print(
            f"MyDevelon EquipmentID: "
            f"{source['equipment_id'] or '-'}"
        )

        print(
            f"PIN:                   "
            f"{pin or '-'}"
        )

        print(
            f"Modelo MyDevelon:      "
            f"{source['model'] or '-'}"
        )

        print(
            f"Horas MyDevelon:       "
            f"{format_hours(source_hours)}"
        )

        print(
            f"Fecha lectura:         "
            f"{format_datetime(source_datetime)}"
        )

        if source_age_hours is not None:

            print(
                f"Antigüedad lectura:    "
                f"{source_age_hours:,.1f} h"
            )

        else:

            print(
                "Antigüedad lectura:    -"
            )

        if not pin:

            print(
                "[ERROR] MyDevelon no entrega PIN."
            )

            counters["NO_MATCH_SERIAL"] += 1
            counters["ERROR"] += 1

            continue

        machinery = get_machinery_by_serial(pin)

        if not machinery:

            print(
                "[NO MATCH] PIN no encontrado "
                "en SQL machinery.serial."
            )

            counters["NO_MATCH_SERIAL"] += 1

            continue

        counters["MATCH_SERIAL"] += 1

        machinery_id = machinery.get("id")
        equipment_code = machinery.get("equipment_code")
        print(
            f"Transmaco:             "
            f"{equipment_code or '-'}"
        )

        print(
            f"Machinery ID:          "
            f"{machinery_id}"
        )

        print(
            "La autorización de telemetría se consulta "
            "en telemetry_sync_config."
        )

        try:
            telemetry_config = get_telemetry_sync_config(
                machinery_id=machinery_id,
                telemetry_source="MYDEVELON"
            )

        except ValueError as error:

            print(
                "[CONFIG_MULTIPLE] "
                "Configuración de telemetría ambigua."
            )

            print(f"        {error}")
            counters["ERROR"] += 1

            continue

        if telemetry_config is None:

            print(
                "[CONFIG_MISSING] No existe configuración "
                "MYDEVELON para el activo."
            )

            counters["ERROR"] += 1
            continue

        sync_enabled = telemetry_config.get("sync_enabled")
        action_policy = str(
            telemetry_config.get("action_policy") or ""
        ).strip().upper()

        print(
            f"Configuración:         sync_enabled={sync_enabled}, "
            f"action_policy={action_policy or '-'}"
        )

        if not sync_enabled:

            print(
                "[SYNC_DISABLED] La telemetría está deshabilitada."
            )

            counters["ERROR"] += 1
            continue

        if action_policy != "AUTO":

            print(
                "[CONFIG_REVIEW] La política no autoriza "
                "sincronización automática."
            )

            counters["ERROR"] += 1
            continue

        try:

            equipment = get_equipment_by_serial(
                fracttal_token,
                pin
            )

        except Exception as error:

            print(
                "[ERROR] Buscando equipo en Fracttal:"
            )

            print(f"        {error}")

            if str(error).startswith(
                (
                    "METER_SERIAL_MISMATCH",
                    "METER_SERIAL_MISSING",
                    "METER_SERIAL_DUPLICATE",
                    "NO_VALID_METER"
                )
            ):
                counters["NO_VALID_METER"] += 1
            else:
                counters["ERROR"] += 1

            continue

        if equipment is None:

            print(
                "[ERROR] El equipo no existe en Fracttal."
            )

            counters[
                "NO_FRACTTAL_EQUIPMENT"
            ] += 1

            continue

        print()
        print(
            "[OK] Equipo Fracttal encontrado"
        )

        print(
            f"     Código:       "
            f"{equipment.get('code')}"
        )

        print(
            f"     Nombre:       "
            f"{equipment.get('field_1')}"
        )

        print(
            f"     Fabricante:   "
            f"{equipment.get('field_2')}"
        )

        print(
            f"     Modelo:       "
            f"{equipment.get('field_3')}"
        )

        print(
            f"     Serial:       "
            f"{equipment.get('field_4')}"
        )

        try:

            result = get_current_hourmeter(
                fracttal_token,
                equipment
            )

        except Exception as error:

            print(
                "[ERROR] Identificando horómetro:"
            )

            print(f"        {error}")

            counters["ERROR"] += 1

            continue

        if result is None:

            print(
                "[NO HORÓMETRO] "
                "No existe un horómetro válido."
            )

            counters["NO_VALID_METER"] += 1

            continue

        meter = result["meter"]

        fracttal_hours = safe_float(
            result["value"]
        )

        print()
        print(
            "[OK] Horómetro Fracttal"
        )

        print(
            f"     ID:            "
            f"{meter.get('id')}"
        )

        print(
            f"     Descripción:   "
            f"{meter.get('description')}"
        )

        print(
            f"     Serial:        "
            f"{meter.get('serial') or '-'}"
        )

        print(
            f"     Valor:         "
            f"{format_hours(fracttal_hours)}"
        )

        difference = None

        if (
            source_hours is not None
            and fracttal_hours is not None
        ):

            difference = (
                source_hours
                - fracttal_hours
            )

        print()

        if difference is not None:

            print(
                f"Diferencia "
                f"(MyDevelon - Fracttal): "
                f"{difference:+,.2f} h"
            )

        action = decide_action(
            source_hours=source_hours,
            source_datetime=source_datetime,
            fracttal_hours=fracttal_hours,
        )

        print(
            f"DECISIÓN: {action}"
        )

        if action == "UPDATE":

            print(
                f"     -> ACTUALIZAR: "
                f"{format_hours(fracttal_hours)} "
                f"-> "
                f"{format_hours(source_hours)}"
            )

            counters["UPDATE"] += 1

        elif action == "REVIEW_INCONSISTENCY":

            print(
                "     -> MyDevelon tiene menos horas. "
                "Revisión manual requerida."
            )

            counters["REVIEW_INCONSISTENCY"] += 1

        elif action == "REVIEW_OLD_SOURCE":

            print(
                "     -> Fuente demasiado antigua."
            )

            counters["REVIEW_OLD_SOURCE"] += 1

        elif action == "REVIEW_SOURCE_DATE":

            print(
                "     -> Fecha de fuente inválida."
            )

            counters["REVIEW_SOURCE_DATE"] += 1

        elif action == "REVIEW_FRACTTAL_HOURS":

            print(
                "     -> Horómetro Fracttal "
                "sin valor válido."
            )

            counters["REVIEW_FRACTTAL_HOURS"] += 1

        elif action == "SKIP_EQUAL":

            counters["SKIP_EQUAL"] += 1

        elif action.startswith("ERROR"):

            counters["ERROR"] += 1

    print()
    print("=" * 80)
    print("RESUMEN AUDITORÍA")
    print("=" * 80)

    for key, value in counters.items():
        print(f"{key:<30} {value}")

    print("=" * 80)

    print()
    print(
        "[IMPORTANTE] "
        "No se realizaron escrituras en Fracttal."
    )

    print(
        "[IMPORTANTE] "
        "MyDevelon es la fuente de verdad."
    )

    print(
        "[IMPORTANTE] "
        "El XML utilizado fue local."
    )

    print(
        "[IMPORTANTE] "
        "No se realizó ninguna llamada a MyDevelon."
    )


if __name__ == "__main__":
    main()