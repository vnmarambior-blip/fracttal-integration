import mssql_python


connection = mssql_python.connect(
    "Server=localhost;Database=FracttalIntegration;Trusted_Connection=yes;TrustServerCertificate=yes;"
)

cursor = connection.cursor()

# Verificar tabla
cursor.execute("""
    SELECT
        TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'horometer_readings'
""")

table = cursor.fetchone()

if table:
    print("TABLA ENCONTRADA: horometer_readings")
else:
    print("ERROR: tabla no encontrada")


# Contar registros
cursor.execute("""
    SELECT COUNT(*)
    FROM horometer_readings
""")

count = cursor.fetchone()[0]

print(f"REGISTROS ACTUALES: {count}")


cursor.close()
connection.close()