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
print("COLUMNAS TABLA MACHINERY")
print("=" * 70)

cursor.execute("""
    SELECT
        COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = ?
    ORDER BY ORDINAL_POSITION
""", ("machinery",))


rows = cursor.fetchall()

for row in rows:
    print(row[0])


cursor.close()
connection.close()
