from mydevelon import (
    get_access_token,
    get_fleet_xml,
    parse_fleet_xml
)


def main():

    print("=" * 70)
    print("TEST MY DEVELON - FLEET SNAPSHOT")
    print("=" * 70)

    # ========================================================
    # 1. TOKEN
    # ========================================================

    print()
    print("1. Obteniendo token...")

    token = get_access_token()

    print("[OK] Token obtenido.")

    # ========================================================
    # 2. FLEET
    # ========================================================

    print()
    print("2. Consultando Fleet Snapshot...")

    xml = get_fleet_xml(token)

    print("[OK] Fleet Snapshot obtenido.")

    # ========================================================
    # 3. PARSEAR XML
    # ========================================================

    print()
    print("3. Parseando XML...")

    equipment = parse_fleet_xml(xml)

    print(
        f"[OK] Equipos encontrados: "
        f"{len(equipment)}"
    )

    # ========================================================
    # 4. MOSTRAR RESULTADOS
    # ========================================================

    print()
    print("=" * 70)
    print("EQUIPOS MYDEVELON")
    print("=" * 70)

    for item in equipment:

        print()
        print(
            f"PIN: {item['pin']}"
        )

        print(
            f"OEM: {item['oem']}"
        )

        print(
            f"Modelo: {item['model']}"
        )

        print(
            f"Equipment ID: "
            f"{item['equipment_id']}"
        )

        print(
            f"Horómetro: "
            f"{item['operating_hours']}"
        )

        print(
            f"Fecha horómetro: "
            f"{item['operating_hours_datetime']}"
        )

    # ========================================================
    # 5. EJEMPLO MH22
    # ========================================================

    print()
    print("=" * 70)
    print("BUSCANDO MH22")
    print("=" * 70)

    mh22 = None

    for item in equipment:

        if item["pin"] == "DHKCEBDXCK0001085":
            mh22 = item
            break

    if mh22 is None:

        print(
            "[WARN] MH22 no encontrado."
        )

    else:

        print()
        print("MH22 encontrado:")
        print(
            f"PIN: {mh22['pin']}"
        )
        print(
            f"Modelo: {mh22['model']}"
        )
        print(
            f"Horómetro: "
            f"{mh22['operating_hours']}"
        )
        print(
            f"Fecha lectura: "
            f"{mh22['operating_hours_datetime']}"
        )


if __name__ == "__main__":
    main()