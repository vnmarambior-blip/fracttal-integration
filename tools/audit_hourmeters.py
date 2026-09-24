from api import get_access_token, get_meters_by_code
from database import get_connection, save_machine_meter


def get_machinery():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                id,
                serial,
                equipment_code,
                name,
                manufacturer,
                model
            FROM machinery
            WHERE active = 1
            ORDER BY equipment_code
        """)

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def classify_meters(machine_serial, meters):
    valid_meters = []
    no_utilizar = []

    for meter in meters:

        description = str(
            meter.get("description") or ""
        ).strip().upper()

        units_code = str(
            meter.get("units_code") or ""
        ).strip().upper()

        is_counter = meter.get("is_counter") is True

        meter_serial = str(
            meter.get("serial") or ""
        ).strip().upper()

        # Nunca utilizar estos medidores
        if "NO UTILIZAR" in description:
            no_utilizar.append(meter)
            continue

        # Debe estar expresado en horas
        if units_code != "HRS":
            continue

        # Debe ser contador
        if not is_counter:
            continue

        valid_meters.append(meter)

    # No hay horómetros válidos
    if not valid_meters:

        if no_utilizar:
            return "SOLO_NO_UTILIZAR", None, no_utilizar

        return "NO_HOROMETRO", None, []

    machine_serial = str(
        machine_serial or ""
    ).strip().upper()

    # Buscar coincidencia exacta de serial
    serial_matches = [
        meter
        for meter in valid_meters
        if str(
            meter.get("serial") or ""
        ).strip().upper() == machine_serial
    ]

    if len(serial_matches) == 1:
        return "OK", serial_matches[0], valid_meters

    if len(serial_matches) > 1:
        return (
            "MULTIPLES_VALIDOS",
            serial_matches[0],
            serial_matches
        )

    # Existe un único horómetro válido,
    # pero su serial no coincide
    if len(valid_meters) == 1:
        return (
            "SERIAL_NO_COINCIDE",
            valid_meters[0],
            valid_meters
        )

    # Hay varios horómetros válidos y ninguno coincide
    return (
        "MULTIPLES_VALIDOS",
        valid_meters[0],
        valid_meters
    )


def save_audit_result(
    machinery_id,
    status,
    meter
):
    """
    Guarda el resultado de la auditoría en machine_meters.
    """

    if meter is None:

        save_machine_meter(
            machinery_id=machinery_id,
            meter_id=None,
            meter_serial=None,
            meter_description=None,
            units_code=None,
            is_counter=None,
            current_value=None,
            status=status
        )

        return

    meter_id = meter.get("id")

    meter_serial = str(
        meter.get("serial") or ""
    ).strip()

    meter_description = str(
        meter.get("description") or ""
    ).strip()

    units_code = str(
        meter.get("units_code") or ""
    ).strip()

    is_counter = meter.get("is_counter")

    last_data = meter.get("last_data") or {}
    current_value = last_data.get("value")

    save_machine_meter(
        machinery_id=machinery_id,
        meter_id=meter_id,
        meter_serial=meter_serial,
        meter_description=meter_description,
        units_code=units_code,
        is_counter=is_counter,
        current_value=current_value,
        status=status
    )


def main():

    print("=" * 80)
    print("AUDITORÍA MASIVA DE HORÓMETROS")
    print("FRACTTAL → SQL SERVER")
    print("=" * 80)

    print()
    print("Obteniendo token...")

    token = get_access_token()

    print("[OK] Token obtenido.")

    print()
    print("Obteniendo maquinaria desde SQL...")

    machinery = get_machinery()

    print(
        f"[OK] Máquinas encontradas: {len(machinery)}"
    )

    results = []

    print()
    print("Consultando medidores en Fracttal...")
    print("-" * 80)

    for row in machinery:

        (
            machinery_id,
            machine_serial,
            equipment_code,
            name,
            manufacturer,
            model
        ) = row

        try:

            meters = get_meters_by_code(
                token,
                equipment_code
            )

            status, meter, valid_meters = classify_meters(
                machine_serial,
                meters
            )

            meter_id = (
                meter.get("id")
                if meter
                else None
            )

            meter_serial = (
                str(
                    meter.get("serial") or ""
                ).strip()
                if meter
                else None
            )

            current_value = (
                (meter.get("last_data") or {}).get("value")
                if meter
                else None
            )

            # Guardar auditoría en SQL Server
            save_audit_result(
                machinery_id=machinery_id,
                status=status,
                meter=meter
            )

            result = {
                "machinery_id": machinery_id,
                "equipment_code": equipment_code,
                "machine_serial": machine_serial,
                "name": name,
                "manufacturer": manufacturer,
                "model": model,
                "status": status,
                "meter_id": meter_id,
                "meter_serial": meter_serial,
                "current_value": current_value,
                "total_meters": len(meters),
                "valid_meters": len(valid_meters),
            }

            results.append(result)

            print(
                f"{equipment_code:<8} | "
                f"{status:<20} | "
                f"Serial: {str(machine_serial):<25} | "
                f"Valor: {str(current_value):>10}"
            )

        except Exception as e:

            results.append({
                "machinery_id": machinery_id,
                "equipment_code": equipment_code,
                "machine_serial": machine_serial,
                "name": name,
                "manufacturer": manufacturer,
                "model": model,
                "status": "ERROR",
                "meter_id": None,
                "meter_serial": None,
                "current_value": None,
                "total_meters": 0,
                "valid_meters": 0,
            })

            print(
                f"{equipment_code:<8} | "
                f"{'ERROR':<20} | "
                f"{str(e)}"
            )

    print()
    print("=" * 80)
    print("RESUMEN")
    print("=" * 80)

    statuses = {}

    for result in results:

        status = result["status"]

        statuses[status] = (
            statuses.get(status, 0) + 1
        )

    for status, count in sorted(statuses.items()):

        print(
            f"{status:<25}: {count}"
        )

    print()
    print(
        f"Total máquinas auditadas: {len(results)}"
    )

    print()
    print("=" * 80)
    print("MÁQUINAS CON HORÓMETRO VÁLIDO")
    print("=" * 80)

    for result in results:

        if result["status"] == "OK":

            print(
                f"{result['equipment_code']:<8} | "
                f"{result['machine_serial']:<25} | "
                f"Meter ID: "
                f"{str(result['meter_id']):<10} | "
                f"Horómetro: "
                f"{result['current_value']}"
            )

    print()
    print("=" * 80)
    print("AUDITORÍA GUARDADA EN SQL SERVER")
    print("=" * 80)

    print()
    print("Tabla: machine_meters")

    print()
    print("Auditoría finalizada.")


if __name__ == "__main__":
    main()