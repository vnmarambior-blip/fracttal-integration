from mydevelon import (
    get_access_token,
    get_equipment_snapshot_xml,
    parse_equipment_snapshot_xml
)


def main():

    print("=" * 70)
    print("TEST MYDEVELON - SINGLE EQUIPMENT")
    print("=" * 70)

    # --------------------------------------------------------
    # DATOS MH22
    # --------------------------------------------------------

    make_code = "DEVELON"
    model = "DX225LCA"
    serial_number = "CEBDX-001085"

    print()
    print("Equipo de prueba:")
    print("OEM:", make_code)
    print("Modelo:", model)
    print("Serial MyDevelon:", serial_number)

    # --------------------------------------------------------
    # TOKEN
    # --------------------------------------------------------

    print()
    print("1. Obteniendo token...")

    token = get_access_token()

    print("[OK] Token obtenido.")

    # --------------------------------------------------------
    # SINGLE EQUIPMENT
    # --------------------------------------------------------

    print()
    print("2. Consultando equipo...")

    xml = get_equipment_snapshot_xml(
        token=token,
        make_code=make_code,
        model=model,
        serial_number=serial_number
    )

    print()
    print("[OK] XML recibido.")

    # --------------------------------------------------------
    # PARSEAR
    # --------------------------------------------------------

    print()
    print("3. Parseando XML...")

    equipment = parse_equipment_snapshot_xml(
        xml
    )

    if equipment is None:
        raise RuntimeError(
            "MyDevelon no devolvió ningún Equipment."
        )

    print("[OK] Equipo parseado.")

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("RESULTADO")
    print("=" * 70)

    print()
    print("OEM:", equipment["oem"])
    print("Modelo:", equipment["model"])
    print("Equipment ID:", equipment["equipment_id"])
    print("SerialNumber:", equipment["serial_number"])
    print("PIN:", equipment["pin"])
    print(
        "Horómetro:",
        equipment["operating_hours"]
    )
    print(
        "Fecha horómetro:",
        equipment["operating_hours_datetime"]
    )
    print(
        "Hora consulta:",
        equipment["retrieved_at"]
    )

    print()
    print("=" * 70)

    # --------------------------------------------------------
    # VALIDACIONES
    # --------------------------------------------------------

    print("VALIDACIONES")
    print("=" * 70)

    expected_pin = "DHKCEBDXCK0001085"

    if equipment["pin"] == expected_pin:
        print("[OK] PIN coincide con MH22.")
    else:
        print(
            "[ERROR] PIN inesperado:",
            equipment["pin"]
        )

    if equipment["serial_number"] == serial_number:
        print(
            "[OK] SerialNumber coincide "
            "con el solicitado."
        )
    else:
        print(
            "[ERROR] SerialNumber inesperado:",
            equipment["serial_number"]
        )

    if equipment["operating_hours"] is not None:
        print("[OK] Horómetro recibido.")
    else:
        print("[ERROR] No se recibió horómetro.")


if __name__ == "__main__":
    main()