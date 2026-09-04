from database import (
    upsert_machinery,
    get_machinery_by_serial,
    save_horometer_update,
    get_latest_horometer_update,
    get_latest_horometer_update_by_serial,
    get_horometer_history
)


SERIAL = "DHKCEBDXCK0001085"


def main():

    print("=" * 60)
    print("PRUEBA DATABASE.PY")
    print("=" * 60)

    # ========================================================
    # 1. CREAR MAQUINARIA
    # ========================================================

    print()
    print("1. CREANDO / ACTUALIZANDO MAQUINARIA")
    print("-" * 60)

    machinery = upsert_machinery(
        serial=SERIAL,
        equipment_code="MH22",
        name="EXCAVADORA MH22",
        manufacturer="DOOSAN",
        model="DX225LC-MH"
    )

    print()
    print("Maquinaria:")
    print(machinery)

    # ========================================================
    # 2. BUSCAR MAQUINARIA
    # ========================================================

    print()
    print("2. BUSCANDO MAQUINARIA")
    print("-" * 60)

    machinery = get_machinery_by_serial(SERIAL)

    print()
    print(machinery)

    # ========================================================
    # 3. GUARDAR ACTUALIZACIÓN
    # ========================================================

    print()
    print("3. GUARDANDO ACTUALIZACIÓN")
    print("-" * 60)

    save_horometer_update(
        machinery_id=machinery["id"],
        meter_id="117229",
        meter_serial=SERIAL,
        old_value=6286,
        new_value=6314,
        source="MyDevelon",
        status="WOULD_UPDATE",
        message="Prueba de integración SQL"
    )

    # ========================================================
    # 4. OBTENER ÚLTIMA ACTUALIZACIÓN
    # ========================================================

    print()
    print("4. ÚLTIMA ACTUALIZACIÓN")
    print("-" * 60)

    latest = get_latest_horometer_update(
        machinery["id"]
    )

    print()
    print(latest)

    # ========================================================
    # 5. OBTENER POR SERIAL
    # ========================================================

    print()
    print("5. ÚLTIMA ACTUALIZACIÓN POR SERIAL")
    print("-" * 60)

    latest_by_serial = get_latest_horometer_update_by_serial(
        SERIAL
    )

    print()
    print(latest_by_serial)

    # ========================================================
    # 6. HISTORIAL
    # ========================================================

    print()
    print("6. HISTORIAL")
    print("-" * 60)

    history = get_horometer_history(
        SERIAL
    )

    for record in history:
        print(record)

    # ========================================================
    # FIN
    # ========================================================

    print()
    print("=" * 60)
    print("PRUEBA FINALIZADA")
    print("=" * 60)


if __name__ == "__main__":
    main()