from database import get_connection


def main():
    print("=" * 70)
    print("INSPECCIÓN TELEMETRY SYNC CONFIG")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    # ---------------------------------------------------------
    # 1. Estructura de telemetry_sync_config
    # ---------------------------------------------------------
    print("\n[1] COLUMNAS DE telemetry_sync_config")
    print("-" * 70)

    cursor.execute("""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH,
            IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'telemetry_sync_config'
        ORDER BY ORDINAL_POSITION
    """)

    columns = cursor.fetchall()

    for row in columns:
        print(
            f"{row[0]:30} "
            f"{row[1]:15} "
            f"max={str(row[2]):8} "
            f"nullable={row[3]}"
        )

    # ---------------------------------------------------------
    # 2. Contenido actual
    # ---------------------------------------------------------
    print("\n[2] CONFIGURACIÓN ACTUAL")
    print("-" * 70)

    cursor.execute("""
        SELECT *
        FROM telemetry_sync_config
        ORDER BY machinery_id
    """)

    rows = cursor.fetchall()

    column_names = [column[0] for column in cursor.description]

    print(" | ".join(column_names))
    print("-" * 70)

    for row in rows:
        print(" | ".join(str(value) for value in row))

    # ---------------------------------------------------------
    # 3. Máquinas DEVELON / DOOSAN
    # ---------------------------------------------------------
    print("\n[3] ACTIVOS DEVELON / DOOSAN")
    print("-" * 70)

    cursor.execute("""
        SELECT
            m.id,
            m.equipment_code,
            m.serial,
            m.name,
            m.manufacturer,
            m.model,
            m.active
        FROM machinery m
        WHERE
            UPPER(ISNULL(m.manufacturer, '')) LIKE '%DEVELON%'
            OR UPPER(ISNULL(m.manufacturer, '')) LIKE '%DOOSAN%'
        ORDER BY m.equipment_code
    """)

    machines = cursor.fetchall()

    headers = [
        "id",
        "equipment_code",
        "serial",
        "name",
        "manufacturer",
        "model",
        "active",
    ]

    print(" | ".join(headers))
    print("-" * 100)

    for row in machines:
        print(" | ".join(str(value) for value in row))

    # ---------------------------------------------------------
    # 4. Configuración + maquinaria
    # ---------------------------------------------------------
    print("\n[4] DEVELON / DOOSAN + TELEMETRY CONFIG")
    print("-" * 70)

    cursor.execute("""
        SELECT
            m.id,
            m.equipment_code,
            m.serial,
            m.name,
            m.manufacturer,
            m.model,
            m.active,
            t.*
        FROM machinery m
        LEFT JOIN telemetry_sync_config t
            ON t.machinery_id = m.id
        WHERE
            UPPER(ISNULL(m.manufacturer, '')) LIKE '%DEVELON%'
            OR UPPER(ISNULL(m.manufacturer, '')) LIKE '%DOOSAN%'
        ORDER BY m.equipment_code
    """)

    rows = cursor.fetchall()

    column_names = [column[0] for column in cursor.description]

    print(" | ".join(column_names))
    print("-" * 70)

    for row in rows:
        print(" | ".join(str(value) for value in row))

    cursor.close()
    conn.close()

    print("\n" + "=" * 70)
    print("INSPECCIÓN TERMINADA")
    print("=" * 70)


if __name__ == "__main__":
    main()