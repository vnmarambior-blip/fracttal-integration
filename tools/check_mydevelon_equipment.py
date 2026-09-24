from mydevelon import (
    get_access_token,
    get_equipment_snapshot_xml,
)


OEM = "DEVELON"
MODEL = "DX225LCA"
EQUIPMENT_SERIAL = "CEBDX-001085"


def main():
    print("=" * 70)
    print("TEST MYDEVELON EQUIPMENT")
    print("=" * 70)

    # ---------------------------------------------------------
    # 1. TOKEN
    # ---------------------------------------------------------
    print("\n1. MYDEVELON")
    print("-" * 70)

    print("Obteniendo token...")

    token = get_access_token()

    print("[OK] Token obtenido.")

    # ---------------------------------------------------------
    # 2. EQUIPMENT
    # ---------------------------------------------------------
    print("\n2. CONSULTANDO EQUIPO")
    print("-" * 70)

    print(f"OEM:       {OEM}")
    print(f"Modelo:    {MODEL}")
    print(f"Serial:    {EQUIPMENT_SERIAL}")

    print("\nConsultando endpoint individual...")

    xml_text = get_equipment_snapshot_xml(
        token=token,
        make_code=OEM,
        model=MODEL,
        serial_number=EQUIPMENT_SERIAL,
    )

    # ---------------------------------------------------------
    # 3. RESULTADO
    # ---------------------------------------------------------
    print("\n3. RESULTADO")
    print("-" * 70)

    print("[OK] Respuesta recibida.")
    print(f"Longitud: {len(xml_text)} caracteres")

    print("\nPrimeros 2.000 caracteres:")
    print("-" * 70)
    print(xml_text[:2000])
    print("-" * 70)

    print("\n" + "=" * 70)
    print("TEST FINALIZADO")
    print("=" * 70)


if __name__ == "__main__":
    main()