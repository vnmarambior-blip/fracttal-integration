from api import (
    get_access_token,
    get_all_equipment
)

from database import upsert_machinery


def main():

    print("=" * 60)
    print("SINCRONIZACIÓN DE MAQUINARIA")
    print("FRACTTAL → SQL SERVER")
    print("=" * 60)

    print()
    print("Obteniendo token...")

    token = get_access_token()

    print("[OK] Token obtenido correctamente.")

    print()
    print("Obteniendo equipos desde Fracttal...")

    equipment_list = get_all_equipment(token)

    print(
        f"[OK] Equipos encontrados en Fracttal: "
        f"{len(equipment_list)}"
    )

    created_or_updated = 0
    skipped = 0

    print()
    print("Procesando maquinaria...")
    print("-" * 60)

    for equipment in equipment_list:

        serial = str(
            equipment.get("field_4", "")
        ).strip().upper()

        code = equipment.get("code")
        name = equipment.get("field_1")
        manufacturer = equipment.get("field_2")
        model = equipment.get("field_3")

        # ----------------------------------------------------
        # Validar serial
        # ----------------------------------------------------

        if not serial:

            print(
                "[SKIP] Equipo sin número de serie."
            )

            print(
                f"       Código: {code}"
            )

            skipped += 1
            continue

        # ----------------------------------------------------
        # Guardar / actualizar
        # ----------------------------------------------------

        upsert_machinery(
            serial=serial,
            equipment_code=code,
            name=name,
            manufacturer=manufacturer,
            model=model
        )

        created_or_updated += 1

    print()
    print("=" * 60)
    print("RESUMEN DE SINCRONIZACIÓN")
    print("=" * 60)

    print(
        f"Equipos encontrados:      {len(equipment_list)}"
    )

    print(
        f"Procesados correctamente:  {created_or_updated}"
    )

    print(
        f"Saltados:                  {skipped}"
    )

    print()
    print("Sincronización finalizada.")


if __name__ == "__main__":
    main()