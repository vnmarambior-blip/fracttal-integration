from database import get_connection


# ============================================================
# PINs REALES ENTREGADOS POR MYDEVELON FLEET
# ============================================================

MYDEVELON_PINS = [
    "DHKCEBACPJ0021470",  # MH12
    "DHKCEBACHJ0021673",  # MH13
    "DHKCEBACEJ0021674",  # MH14
    "DHKCEBACEK0022860",  # MH15
    "DHKCEBADLG0007790",  # MH07
    "DHKCEBADJK0008232",  # sin SQL
    "DHKCEBDPHR0002339",  # MH38
    "DHKCEBDPCT0002715",  # MH46
    "DHKCEBDXCK0001085",  # MH22
    "DHKCEBEFLM0001009",  # MH26
    "DHKCEBEFKN0001103",  # MH28
    "DHKCEBEFKN0001148",  # MH27
    "DHKCEBEFHN0001188",  # MH30
    "DHKCEBEFEN0001189",  # sin SQL
    "DHKCEBEFLP0001404",  # MH34
    "DHKCECFKCN0001283",  # MH32
    "DWGCECFWJN1010341",  # MH39
    "DHKCEWAACP5009518",  # MH35
    "DHKCEWADJP5005963",  # MH37
    "DHKCEWADCP5005964",  # MH36
    "DHKCEWCKAR5001236",  # sin SQL
    "DHKCEWCKLR5001237",  # sin SQL
    "DHKCEWCKHR5001238",  # MH42
    "DHKCEWCLLS5001771",  # MH43
    "DHKCEWEETS5031051",  # MH45
]


TARGET_SOURCE = "MYDEVELON"


def normalize(value):
    if value is None:
        return ""

    return str(value).strip().upper()


# ============================================================
# CONEXIÓN
# ============================================================



def main():

    connection = get_connection()
    cursor = connection.cursor()


    print("=" * 80)
    print("LIMPIEZA CONFIGURACIÓN MYDEVELON")
    print("=" * 80)


    # ============================================================
    # 1. OBTENER ACTIVOS DE MYDEVELON QUE EXISTEN EN SQL
    # ============================================================

    print("\n1. BUSCANDO ACTIVOS MYDEVELON EN SQL")
    print("-" * 80)

    cursor.execute("""
        SELECT
            id,
            serial,
            equipment_code,
            name,
            active
        FROM machinery
    """)

    machinery_rows = cursor.fetchall()


    machinery_by_serial = {}

    for row in machinery_rows:
        machinery_id = row[0]
        serial = normalize(row[1])
        equipment_code = row[2]
        name = row[3]
        active = row[4]

        if serial:
            machinery_by_serial[serial] = {
                "id": machinery_id,
                "serial": serial,
                "equipment_code": equipment_code,
                "name": name,
                "active": active,
            }


    matched = []
    not_in_sql = []

    for pin in MYDEVELON_PINS:

        normalized_pin = normalize(pin)

        machinery = machinery_by_serial.get(
            normalized_pin
        )

        if machinery:
            matched.append(machinery)
        else:
            not_in_sql.append(normalized_pin)


    print(
        f"[OK] PINs recibidos desde MyDevelon: "
        f"{len(MYDEVELON_PINS)}"
    )

    print(
        f"[OK] Encontrados en SQL: "
        f"{len(matched)}"
    )

    print(
        f"[INFO] No encontrados en SQL: "
        f"{len(not_in_sql)}"
    )


    # ============================================================
    # 2. MOSTRAR NO MATCH
    # ============================================================

    if not_in_sql:

        print("\nPINs MYDEVELON SIN REGISTRO EN SQL:")
        print("-" * 80)

        for pin in not_in_sql:
            print(f"  {pin}")


    # ============================================================
    # 3. IDENTIFICAR IDs VÁLIDOS PARA MYDEVELON
    # ============================================================

    valid_machinery_ids = [
        item["id"]
        for item in matched
    ]


    # ============================================================
    # 4. ELIMINAR CONFIGURACIONES MYDEVELON QUE NO CORRESPONDEN
    # ============================================================

    print(
        "\n2. LIMPIANDO CONFIGURACIONES ANTIGUAS"
    )
    print("-" * 80)

    # Obtener todas las configuraciones actuales
    cursor.execute("""
        SELECT
            id,
            machinery_id
        FROM telemetry_sync_config
        WHERE telemetry_source = ?
    """, (TARGET_SOURCE,))

    config_rows = cursor.fetchall()

    configs_to_delete = []

    for config_id, machinery_id in config_rows:

        if machinery_id not in valid_machinery_ids:
            configs_to_delete.append(config_id)


    for config_id in configs_to_delete:

        cursor.execute("""
            DELETE FROM telemetry_sync_config
            WHERE id = ?
        """, (config_id,))


    print(
        f"[OK] Configuraciones eliminadas: "
        f"{len(configs_to_delete)}"
    )


    # ============================================================
    # 5. MH14 = DISABLED
    # ============================================================

    print("\n3. CONFIGURANDO MH14")
    print("-" * 80)

    mh14 = None

    for item in matched:
        if item["equipment_code"] == "MH14":
            mh14 = item
            break


    if mh14:

        # Fuera de la flota
        cursor.execute("""
            UPDATE machinery
            SET active = 0,
                updated_at = SYSDATETIME()
            WHERE id = ?
        """, (mh14["id"],))

        # Verificar configuración
        cursor.execute("""
            SELECT COUNT(*)
            FROM telemetry_sync_config
            WHERE machinery_id = ?
              AND telemetry_source = ?
        """, (
            mh14["id"],
            TARGET_SOURCE,
        ))

        exists = cursor.fetchone()[0]

        if exists:

            cursor.execute("""
                UPDATE telemetry_sync_config
                SET
                    sync_enabled = 0,
                    action_policy = 'DISABLED',
                    comparison_basis = 'COUNTER_VALUE',
                    reason = 'Activo fuera de la flota',
                    notes = 'No sincronizar aunque continúe existiendo en Fracttal.',
                    updated_at = SYSDATETIME()
                WHERE machinery_id = ?
                  AND telemetry_source = ?
            """, (
                mh14["id"],
                TARGET_SOURCE,
            ))

        else:

            cursor.execute("""
                INSERT INTO telemetry_sync_config
                (
                    machinery_id,
                    telemetry_source,
                    sync_enabled,
                    action_policy,
                    comparison_basis,
                    reason,
                    notes
                )
                VALUES
                (
                    ?,
                    ?,
                    0,
                    'DISABLED',
                    'COUNTER_VALUE',
                    'Activo fuera de la flota',
                    'No sincronizar aunque continúe existiendo en Fracttal.'
                )
            """, (
                mh14["id"],
                TARGET_SOURCE,
            ))

        print(
            "[OK] MH14 -> DISABLED"
        )


    # ============================================================
    # 6. MH35 = REVIEW
    # ============================================================

    print("\n4. CONFIGURANDO MH35")
    print("-" * 80)

    mh35 = None

    for item in matched:
        if item["equipment_code"] == "MH35":
            mh35 = item
            break


    if mh35:

        cursor.execute("""
            UPDATE machinery
            SET active = 1,
                updated_at = SYSDATETIME()
            WHERE id = ?
        """, (mh35["id"],))

        cursor.execute("""
            SELECT COUNT(*)
            FROM telemetry_sync_config
            WHERE machinery_id = ?
              AND telemetry_source = ?
        """, (
            mh35["id"],
            TARGET_SOURCE,
        ))

        exists = cursor.fetchone()[0]

        if exists:

            cursor.execute("""
                UPDATE telemetry_sync_config
                SET
                    sync_enabled = 1,
                    action_policy = 'REVIEW',
                    comparison_basis = 'LAST_DATA_VALUE',
                    reason = 'Horómetro reiniciado previamente',
                    notes = 'Validar comportamiento del contador Fracttal antes de automatizar.',
                    updated_at = SYSDATETIME()
                WHERE machinery_id = ?
                  AND telemetry_source = ?
            """, (
                mh35["id"],
                TARGET_SOURCE,
            ))

        else:

            cursor.execute("""
                INSERT INTO telemetry_sync_config
                (
                    machinery_id,
                    telemetry_source,
                    sync_enabled,
                    action_policy,
                    comparison_basis,
                    reason,
                    notes
                )
                VALUES
                (
                    ?,
                    ?,
                    1,
                    'REVIEW',
                    'LAST_DATA_VALUE',
                    'Horómetro reiniciado previamente',
                    'Validar comportamiento del contador Fracttal antes de automatizar.'
                )
            """, (
                mh35["id"],
                TARGET_SOURCE,
            ))

        print(
            "[OK] MH35 -> REVIEW"
        )


    # ============================================================
    # 7. RESTO DE ACTIVOS MYDEVELON = AUTO
    # ============================================================

    print("\n5. CONFIGURANDO RESTO DE ACTIVOS")
    print("-" * 80)

    auto_count = 0

    for item in matched:

        code = item["equipment_code"]

        # MH14 y MH35 tienen política especial
        if code in ("MH14", "MH35"):
            continue

        cursor.execute("""
            SELECT COUNT(*)
            FROM telemetry_sync_config
            WHERE machinery_id = ?
              AND telemetry_source = ?
        """, (
            item["id"],
            TARGET_SOURCE,
        ))

        exists = cursor.fetchone()[0]

        if exists:

            cursor.execute("""
                UPDATE telemetry_sync_config
                SET
                    sync_enabled = 1,
                    action_policy = 'AUTO',
                    comparison_basis = 'COUNTER_VALUE',
                    reason = NULL,
                    notes = NULL,
                    updated_at = SYSDATETIME()
                WHERE machinery_id = ?
                  AND telemetry_source = ?
            """, (
                item["id"],
                TARGET_SOURCE,
            ))

        else:

            cursor.execute("""
                INSERT INTO telemetry_sync_config
                (
                    machinery_id,
                    telemetry_source,
                    sync_enabled,
                    action_policy,
                    comparison_basis,
                    reason,
                    notes
                )
                VALUES
                (
                    ?,
                    ?,
                    1,
                    'AUTO',
                    'COUNTER_VALUE',
                    NULL,
                    NULL
                )
            """, (
                item["id"],
                TARGET_SOURCE,
            ))

        auto_count += 1


    print(
        f"[OK] Activos configurados como AUTO: "
        f"{auto_count}"
    )


    # ============================================================
    # 8. GUARDAR CAMBIOS
    # ============================================================

    connection.commit()


    # ============================================================
    # 9. MOSTRAR RESULTADO FINAL
    # ============================================================

    print("\n6. CONFIGURACIÓN FINAL")
    print("-" * 80)

    cursor.execute("""
        SELECT
            m.equipment_code,
            m.name,
            m.serial,
            m.active,
            c.sync_enabled,
            c.action_policy,
            c.comparison_basis
        FROM telemetry_sync_config c
        INNER JOIN machinery m
            ON m.id = c.machinery_id
        WHERE c.telemetry_source = ?
        ORDER BY m.equipment_code
    """, (TARGET_SOURCE,))

    rows = cursor.fetchall()


    print(
        f"{'Código':<10}"
        f"{'Activo':<8}"
        f"{'Sync':<8}"
        f"{'Política':<12}"
        f"{'Base':<18}"
    )

    print("-" * 60)

    for row in rows:

        (
            equipment_code,
            name,
            serial,
            active,
            sync_enabled,
            action_policy,
            comparison_basis,
        ) = row

        print(
            f"{str(equipment_code):<10}"
            f"{str(active):<8}"
            f"{str(sync_enabled):<8}"
            f"{str(action_policy):<12}"
            f"{str(comparison_basis):<18}"
        )


    # ============================================================
    # 10. RESUMEN
    # ============================================================

    print("\n7. RESUMEN")
    print("-" * 80)

    cursor.execute("""
        SELECT
            action_policy,
            COUNT(*)
        FROM telemetry_sync_config
        WHERE telemetry_source = ?
        GROUP BY action_policy
        ORDER BY action_policy
    """, (TARGET_SOURCE,))

    summary = cursor.fetchall()

    for policy, count in summary:

        print(
            f"{policy:<15} {count}"
        )


    print()
    print(
        f"MYDEVELON FLEET:       {len(MYDEVELON_PINS)}"
    )

    print(
        f"EN SQL:                {len(matched)}"
    )

    print(
        f"SIN SQL:               {len(not_in_sql)}"
    )

    print(
        f"CONFIGURACIONES:       {len(rows)}"
    )


    print("\n" + "=" * 80)
    print("LIMPIEZA FINALIZADA")
    print("=" * 80)


    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()
