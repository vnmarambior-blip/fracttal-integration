from mydevelon import get_access_token, get_fleet_xml


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
    # 2. FLEET - UNA SOLA LLAMADA
    # ---------------------------------------------------------
    print("\n2. CONSULTANDO FLEET")
    print("-" * 70)

    print("Consultando Fleet...")
    print("Esta prueba realiza UNA sola llamada al endpoint Fleet.")

    xml_text = get_fleet_xml(
        token=token,
    )

    # ---------------------------------------------------------
    # 3. RESULTADO
    # ---------------------------------------------------------
    print("\n3. RESULTADO")
    print("-" * 70)

    print("[OK] Respuesta Fleet recibida.")
    print(f"Longitud respuesta: {len(xml_text)} caracteres")

    print("\nPrimeros 2.000 caracteres:")
    print("-" * 70)
    print(xml_text[:2000])
    print("-" * 70)

    print("\n" + "=" * 70)
    print("TEST FINALIZADO")
    print("=" * 70)


if __name__ == "__main__":
    main()