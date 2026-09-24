from database import get_connection


def table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = ?
        """,
        (table_name,)
    )

    return cursor.fetchone()[0] > 0


def create_machine_meters_table(cursor):
    if table_exists(cursor, "machine_meters"):
        print("[OK] Tabla machine_meters ya existe.")
        return

    print("[INFO] Creando tabla machine_meters...")

    cursor.execute(
        """
        CREATE TABLE machine_meters
        (
            id INT IDENTITY(1,1) PRIMARY KEY,

            machinery_id INT NOT NULL,

            meter_id INT NULL,

            meter_serial VARCHAR(255) NULL,

            meter_description VARCHAR(255) NULL,

            units_code VARCHAR(50) NULL,

            is_counter BIT NULL,

            current_value DECIMAL(18,2) NULL,

            status VARCHAR(50) NOT NULL,

            last_verified_at DATETIME2 NULL,

            created_at DATETIME2 NOT NULL
                DEFAULT SYSDATETIME(),

            updated_at DATETIME2 NULL
        )
        """
    )

    print("[OK] Tabla machine_meters creada.")


def main():

    print("=" * 70)
    print("INICIALIZACIÓN DE BASE DE DATOS")
    print("FRACTTAL INTEGRATION")
    print("=" * 70)

    connection = get_connection()

    try:
        cursor = connection.cursor()

        print()
        print("[OK] Conexión a SQL Server establecida.")

        create_machine_meters_table(cursor)

        connection.commit()

        print()
        print("=" * 70)
        print("BASE DE DATOS LISTA")
        print("=" * 70)

    except Exception as e:

        connection.rollback()

        print()
        print("[ERROR] No se pudo inicializar la base de datos.")
        print()
        print(str(e))

        raise

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()