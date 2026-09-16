import mssql_python


CONNECTION_STRING = (
    "Server=localhost;"
    "Database=FracttalIntegration;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


SERIALS = [
    "DHKCEBADJK0008232",
    "DHKCEBEFEN0001189",
    "DHKCEWCKAR5001236",
    "DHKCEWCKLR5001237",
]


connection = mssql_python.connect(CONNECTION_STRING)
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