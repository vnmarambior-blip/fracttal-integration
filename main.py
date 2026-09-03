from api import get_access_token, process_equipment


def main():

    print("=" * 60)
    print("PRUEBAS DE SEGURIDAD - HORÓMETROS FRACTTAL")
    print("=" * 60)

    print()
    print("Obteniendo token...")

    token = get_access_token()

    print("[OK] Token obtenido correctamente.")

    serial = "DHKCEBDXCK0001085"

    # ========================================================
    # PRUEBA 1 - ACTUALIZACIÓN
    # ========================================================

    print()
    print()
    print("############################################################")
    print("# PRUEBA 1 - NUEVO VALOR MAYOR")
    print("############################################################")

    result_1 = process_equipment(
        token=token,
        serial=serial,
        new_value=6314,
        dry_run=True
    )

    print()
    print("RESULTADO PRUEBA 1:")
    print(result_1)

    # ========================================================
    # PRUEBA 2 - MISMO VALOR
    # ========================================================

    print()
    print()
    print("############################################################")
    print("# PRUEBA 2 - MISMO VALOR")
    print("############################################################")

    result_2 = process_equipment(
        token=token,
        serial=serial,
        new_value=6286,
        dry_run=True
    )

    print()
    print("RESULTADO PRUEBA 2:")
    print(result_2)

    # ========================================================
    # PRUEBA 3 - VALOR MENOR
    # ========================================================

    print()
    print()
    print("############################################################")
    print("# PRUEBA 3 - NUEVO VALOR MENOR")
    print("############################################################")

    result_3 = process_equipment(
        token=token,
        serial=serial,
        new_value=6200,
        dry_run=True
    )

    print()
    print("RESULTADO PRUEBA 3:")
    print(result_3)

    # ========================================================
    # RESUMEN
    # ========================================================

    print()
    print()
    print("=" * 60)
    print("RESUMEN DE PRUEBAS")
    print("=" * 60)

    print(f"Prueba 1: {result_1['status']}")
    print(f"Prueba 2: {result_2['status']}")
    print(f"Prueba 3: {result_3['status']}")

    print()
    print("Todas las pruebas fueron ejecutadas en DRY RUN.")
    print("No se modificó ningún dato en Fracttal.")


if __name__ == "__main__":
    main()