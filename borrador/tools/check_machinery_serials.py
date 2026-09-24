from database import get_connection


SERIALS = [
    "DHKCEBADJK0008232",
    "DHKCEBEFEN0001189",
    "DHKCEWCKAR5001236",
    "DHKCEWCKLR5001237",
]


def main():

    connection = get_connection()
    cursor = connection.cursor()


    print("=" * 70)
    print("VERIFICACION DE SERIALes EN SQL - MACHINERY")
    print("=" * 70)


    for serial in SERIALS:

        cursor.execute("""
            SELECT
                id,
                serial,
                equipment_code,
                name,
                manufacturer,
                model,
                active
            FROM machinery
            WHERE serial = ?
        """, (serial,))

        rows = cursor.fetchall()

        print(f"\nSerial: {serial}")

        if not rows:
            print("  [NO ENCONTRADO]")

        else:
            for row in rows:
                print(f"  ID:           {row[0]}")
                print(f"  Serial:       {row[1]}")
                print(f"  Codigo:       {row[2]}")
                print(f"  Nombre:       {row[3]}")
                print(f"  Fabricante:   {row[4]}")
                print(f"  Modelo:       {row[5]}")
                print(f"  Activo:       {row[6]}")


    print("\n" + "=" * 70)

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()
