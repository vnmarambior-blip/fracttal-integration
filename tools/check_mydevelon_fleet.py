from mydevelon import (
    get_access_token,
    get_fleet_xml,
    parse_fleet_xml,
)


MYDEVELON_PIN = "DHKCEBDXCK0001085"


def main():
    print("=" * 70)
    print("TEST MYDEVELON FLEET")
    print("=" * 70)

    # ---------------------------------------------------------
    # 1. TOKEN
    # ---------------------------------------------------------
    print("\n1. MYDEVELON")
    print("-" * 70)

    print("Obteniendo token de MyDevelon...")

    token = get_access_token()

    print("[OK] Token MyDevelon obtenido.")

    # ---------------------------------------------------------
    # 2. FLEET
    # ---------------------------------------------------------
    print("\n2. CONSULTANDO FLEET")
    print("-" * 70)

    print("Consultando Fleet...")

    xml_text = get_fleet_xml(
        token=token,
    )

    print("[OK] Respuesta Fleet recibida.")

    # ---------------------------------------------------------
    # 3. PARSEAR
    # ---------------------------------------------------------
    print("\n3. PARSEANDO FLEET")
    print("-" * 70)

    fleet = parse_fleet_xml(xml_text)

    print(f"[OK] Equipos encontrados: {len(fleet)}")

    # ---------------------------------------------------------
    # 4. MOSTRAR PRIMEROS EQUIPOS
    # ---------------------------------------------------------
    print("\n4. PRIMEROS EQUIPOS")
    print("-" * 70)

    for index, equipment in enumerate(fleet[:10], start=1):
        print(f"\nEquipo #{index}")

        for key, value in equipment.items():
            print(f"  {key}: {value}")

    # ---------------------------------------------------------
    # 5. BUSCAR MH22 POR PIN
    # ---------------------------------------------------------
    print("\n5. BUSCANDO MH22")
    print("-" * 70)

    matches = []

    for equipment in fleet:
        pin = str(
            equipment.get("pin", "")
        ).strip().upper()

        if pin == MYDEVELON_PIN.upper():
            matches.append(equipment)

    if not matches:
        print("[NO ENCONTRADO]")
        print(
            f"No se encontró el PIN "
            f"{MYDEVELON_PIN} en la respuesta Fleet."
        )

        print()
        print("Esto puede significar:")
        print("1. El equipo no está incluido en esta respuesta.")
        print("2. El Fleet requiere paginación.")
        print("3. El parser no está leyendo el PIN.")
        print()
        print("Pins encontrados:")

        for equipment in fleet:
            pin = equipment.get("pin")

            if pin:
                print(f"  {pin}")

        return

    # ---------------------------------------------------------
    # 6. MOSTRAR MATCH
    # ---------------------------------------------------------
    print(f"[OK] Coincidencias encontradas: {len(matches)}")

    for equipment in matches:
        print("\n" + "=" * 70)
        print("EQUIPO ENCONTRADO")
        print("=" * 70)

        for key, value in equipment.items():
            print(f"{key}: {value}")

    print("\n" + "=" * 70)
    print("TEST FINALIZADO")
    print("=" * 70)


if __name__ == "__main__":
    main()