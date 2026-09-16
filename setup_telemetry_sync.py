import mssql_python


CONNECTION_STRING = (
    "Server=localhost;"
    "Database=FracttalIntegration;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


connection = mssql_python.connect(CONNECTION_STRING)
cursor = connection.cursor()


print("=" * 70)
print("CONFIGURACIÓN TELEMETRÍA")
print("=" * 70)


# ============================================================
# 1. VERIFICAR TABLA MACHINERY
# ============================================================

print("\n1. VERIFICANDO TABLA MACHINERY")
print("-" * 70)

cursor.execute("""
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = ?
""", ("machinery",))

machinery_exists = cursor.fetchone()[0]

if not machinery_exists:
    print("[ERROR] Tabla machinery no encontrada.")

    cursor.close()
    connection.close()

    raise SystemExit(1)

print("[OK] Tabla machinery encontrada.")


# ============================================================
# 2. VERIFICAR TABLA TELEMETRY_SYNC_CONFIG
# ============================================================

print("\n2. VERIFICANDO TABLA TELEMETRY_SYNC_CONFIG")
print("-" * 70)

cursor.execute("""
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = ?
""", ("telemetry_sync_config",))

config_exists = cursor.fetchone()[0]

if not config_exists:

    print(
        "[INFO] Tabla no existe. Creándola..."
    )

    cursor.execute("""
        CREATE TABLE telemetry_sync_config
        (
            id INT IDENTITY(1,1) PRIMARY KEY,

            machinery_id INT NOT NULL,

            telemetry_source VARCHAR(50) NOT NULL,

            sync_enabled BIT NOT NULL DEFAULT 1,

            action_policy VARCHAR(20) NOT NULL DEFAULT 'AUTO',

            comparison_basis VARCHAR(30) NOT NULL DEFAULT 'COUNTER_VALUE',

            reason VARCHAR(500) NULL,

            notes VARCHAR(1000) NULL,

            created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),

            updated_at DATETIME2 NULL
        )
    """)

    connection.commit()

    print(
        "[OK] Tabla telemetry_sync_config creada."
    )

else:
    print(
        "[OK] Tabla telemetry_sync_config encontrada."
    )


# ============================================================
# 3. VERIFICAR MH14
# ============================================================

print("\n3. CONFIGURANDO MH14")
print("-" * 70)

cursor.execute("""
    SELECT
        id,
        equipment_code,
        serial,
        name,
        active
    FROM machinery
    WHERE equipment_code = ?
""", ("MH14",))

mh14 = cursor.fetchone()

if not mh14:

    print(
        "[WARNING] MH14 no existe en machinery."
    )

else:

    mh14_id = mh14[0]

    print(
        f"Encontrado: {mh14[1]} - {mh14[3]}"
    )

    print(
        f"Estado actual active = {mh14[4]}"
    )

    # Marcar como fuera de la flota
    cursor.execute("""
        UPDATE machinery
        SET active = 0,
            updated_at = SYSDATETIME()
        WHERE id = ?
    """, (mh14_id,))

    connection.commit()

    print(
        "[OK] MH14 marcado como inactivo."
    )

    # Crear configuración si no existe
    cursor.execute("""
        SELECT COUNT(*)
        FROM telemetry_sync_config
        WHERE machinery_id = ?
          AND telemetry_source = ?
    """, (
        mh14_id,
        "MYDEVELON",
    ))

    exists = cursor.fetchone()[0]

    if not exists:

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
                'MYDEVELON',
                0,
                'DISABLED',
                'COUNTER_VALUE',
                'Activo fuera de la flota',
                'No sincronizar aunque continúe existiendo en Fracttal.'
            )
        """, (mh14_id,))

        connection.commit()

        print(
            "[OK] Configuración MYDEVELON/MH14 creada."
        )

    else:

        print(
            "[OK] Configuración MYDEVELON/MH14 ya existe."
        )


# ============================================================
# 4. VERIFICAR MH35
# ============================================================

print("\n4. CONFIGURANDO MH35")
print("-" * 70)

cursor.execute("""
    SELECT
        id,
        equipment_code,
        serial,
        name,
        active
    FROM machinery
    WHERE equipment_code = ?
""", ("MH35",))

mh35 = cursor.fetchone()

if not mh35:

    print(
        "[WARNING] MH35 no existe en machinery."
    )

else:

    mh35_id = mh35[0]

    print(
        f"Encontrado: {mh35[1]} - {mh35[3]}"
    )

    cursor.execute("""
        SELECT COUNT(*)
        FROM telemetry_sync_config
        WHERE machinery_id = ?
          AND telemetry_source = ?
    """, (
        mh35_id,
        "MYDEVELON",
    ))

    exists = cursor.fetchone()[0]

    if not exists:

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
                'MYDEVELON',
                1,
                'REVIEW',
                'LAST_DATA_VALUE',
                'Horómetro reiniciado previamente',
                'Validar comportamiento del contador Fracttal antes de automatizar.'
            )
        """, (mh35_id,))

        connection.commit()

        print(
            "[OK] Configuración MYDEVELON/MH35 creada."
        )

    else:

        print(
            "[OK] Configuración MYDEVELON/MH35 ya existe."
        )


# ============================================================
# 5. CONFIGURAR AUTO PARA ACTIVOS ACTIVOS
# ============================================================

print("\n5. CONFIGURANDO ACTIVOS AUTO")
print("-" * 70)

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
    SELECT
        m.id,
        'MYDEVELON',
        1,
        'AUTO',
        'COUNTER_VALUE',
        NULL,
        NULL
    FROM machinery m
    WHERE m.active = 1
      AND NOT EXISTS
      (
          SELECT 1
          FROM telemetry_sync_config c
          WHERE c.machinery_id = m.id
            AND c.telemetry_source = 'MYDEVELON'
      )
""")

inserted_auto = cursor.rowcount

connection.commit()

print(
    f"[OK] Configuraciones AUTO creadas: "
    f"{inserted_auto}"
)


# ============================================================
# 6. MOSTRAR CONFIGURACIÓN
# ============================================================

print("\n6. CONFIGURACIÓN RESULTANTE")
print("-" * 70)

cursor.execute("""
    SELECT
        m.equipment_code,
        m.name,
        m.serial,
        m.active,
        c.telemetry_source,
        c.sync_enabled,
        c.action_policy,
        c.comparison_basis,
        c.reason
    FROM telemetry_sync_config c
    INNER JOIN machinery m
        ON m.id = c.machinery_id
    WHERE c.telemetry_source = ?
    ORDER BY m.equipment_code
""", ("MYDEVELON",))

rows = cursor.fetchall()

print(
    f"{'Código':<10}"
    f"{'Activo':<8}"
    f"{'Fuente':<15}"
    f"{'Sync':<8}"
    f"{'Política':<12}"
    f"{'Base':<18}"
)

print("-" * 75)

for row in rows:

    (
        equipment_code,
        name,
        serial,
        active,
        telemetry_source,
        sync_enabled,
        action_policy,
        comparison_basis,
        reason,
    ) = row

    print(
        f"{str(equipment_code):<10}"
        f"{str(active):<8}"
        f"{str(telemetry_source):<15}"
        f"{str(sync_enabled):<8}"
        f"{str(action_policy):<12}"
        f"{str(comparison_basis):<18}"
    )


# ============================================================
# 7. RESUMEN
# ============================================================

print("\n7. RESUMEN")
print("-" * 70)

cursor.execute("""
    SELECT
        action_policy,
        COUNT(*)
    FROM telemetry_sync_config
    WHERE telemetry_source = ?
    GROUP BY action_policy
    ORDER BY action_policy
""", ("MYDEVELON",))

summary = cursor.fetchall()

for action_policy, count in summary:

    print(
        f"{action_policy:<20} {count}"
    )


print("\n" + "=" * 70)
print("CONFIGURACIÓN FINALIZADA")
print("=" * 70)


cursor.close()
connection.close()