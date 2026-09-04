import mssql_python
from datetime import datetime


# ============================================================
# CONFIGURACIÓN SQL SERVER
# ============================================================

CONNECTION_STRING = (
    "Server=localhost;"
    "Database=FracttalIntegration;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


# ============================================================
# CONEXIÓN
# ============================================================

def get_connection():
    """
    Crea una conexión con SQL Server.
    """

    return mssql_python.connect(CONNECTION_STRING)


# ============================================================
# MAQUINARIA
# ============================================================

def get_machinery_by_serial(serial):
    """
    Busca una maquinaria por número de serie.

    Retorna:
        Diccionario con los datos de la maquinaria.

    Si no existe:
        None
    """

    serial = str(serial).strip().upper()

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                serial,
                equipment_code,
                name,
                manufacturer,
                model,
                active,
                created_at,
                updated_at
            FROM machinery
            WHERE serial = ?
            """,
            (serial,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "serial": row[1],
            "equipment_code": row[2],
            "name": row[3],
            "manufacturer": row[4],
            "model": row[5],
            "active": row[6],
            "created_at": row[7],
            "updated_at": row[8]
        }

    finally:

        cursor.close()
        connection.close()


# ============================================================
# CREAR / ACTUALIZAR MAQUINARIA
# ============================================================

def upsert_machinery(
    serial,
    equipment_code=None,
    name=None,
    manufacturer=None,
    model=None,
    active=True
):
    """
    Crea una maquinaria si no existe.

    Si ya existe por serial, actualiza sus datos.

    Retorna:
        Diccionario con los datos actuales de la maquinaria.
    """

    serial = str(serial).strip().upper()

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Buscar maquinaria existente
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM machinery
            WHERE serial = ?
            """,
            (serial,)
        )

        row = cursor.fetchone()

        # ----------------------------------------------------
        # CREAR
        # ----------------------------------------------------

        if row is None:

            cursor.execute(
                """
                INSERT INTO machinery
                (
                    serial,
                    equipment_code,
                    name,
                    manufacturer,
                    model,
                    active
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    serial,
                    equipment_code,
                    name,
                    manufacturer,
                    model,
                    active
                )
            )

            connection.commit()

            print(
                f"[OK] Maquinaria creada en SQL Server: {serial}"
            )

        # ----------------------------------------------------
        # ACTUALIZAR
        # ----------------------------------------------------

        else:

            cursor.execute(
                """
                UPDATE machinery
                SET
                    equipment_code = ?,
                    name = ?,
                    manufacturer = ?,
                    model = ?,
                    active = ?,
                    updated_at = SYSDATETIME()
                WHERE serial = ?
                """,
                (
                    equipment_code,
                    name,
                    manufacturer,
                    model,
                    active,
                    serial
                )
            )

            connection.commit()

            print(
                f"[OK] Maquinaria actualizada en SQL Server: {serial}"
            )

    finally:

        cursor.close()
        connection.close()

    return get_machinery_by_serial(serial)


# ============================================================
# GUARDAR ACTUALIZACIÓN DE HORÓMETRO
# ============================================================

def save_horometer_update(
    machinery_id,
    meter_id,
    meter_serial,
    old_value,
    new_value,
    source="MyDevelon",
    reading_date=None,
    status="RECEIVED",
    message=None
):
    """
    Registra un evento de horómetro en horometer_updates.

    Parámetros:

        machinery_id:
            ID de la maquinaria en la tabla machinery.
            Puede ser None cuando el equipo no fue encontrado.

        meter_id:
            ID del medidor en Fracttal.

        meter_serial:
            Serial del medidor.

        old_value:
            Valor que tenía el horómetro antes del proceso.

        new_value:
            Nuevo valor recibido.

        source:
            Origen del dato.
            Por defecto: MyDevelon.

        reading_date:
            Fecha/hora de la lectura.
            Si no se entrega, utiliza la fecha/hora actual.

        status:
            Estado del procesamiento.

        message:
            Mensaje adicional o detalle del resultado.

    La columna difference NO se inserta desde Python.
    SQL Server la calcula automáticamente.
    """

    if reading_date is None:
        reading_date = datetime.now()

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO horometer_updates
            (
                machinery_id,
                meter_id,
                meter_serial,
                old_value,
                new_value,
                source,
                reading_date,
                status,
                message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                machinery_id,
                meter_id,
                meter_serial,
                old_value,
                new_value,
                source,
                reading_date,
                status,
                message
            )
        )

        connection.commit()

        print(
            "[OK] Actualización de horómetro guardada "
            "en SQL Server."
        )

    finally:

        cursor.close()
        connection.close()


# ============================================================
# OBTENER ÚLTIMA ACTUALIZACIÓN DE HORÓMETRO
# ============================================================

def get_latest_horometer_update(machinery_id):
    """
    Obtiene la última actualización de horómetro
    registrada para una maquinaria.

    Retorna:
        Diccionario con el último registro.

    Si no existe:
        None
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT TOP 1
                id,
                machinery_id,
                meter_id,
                meter_serial,
                old_value,
                new_value,
                difference,
                source,
                reading_date,
                processed_at,
                status,
                message
            FROM horometer_updates
            WHERE machinery_id = ?
            ORDER BY reading_date DESC, id DESC
            """,
            (machinery_id,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "machinery_id": row[1],
            "meter_id": row[2],
            "meter_serial": row[3],
            "old_value": row[4],
            "new_value": row[5],
            "difference": row[6],
            "source": row[7],
            "reading_date": row[8],
            "processed_at": row[9],
            "status": row[10],
            "message": row[11]
        }

    finally:

        cursor.close()
        connection.close()


# ============================================================
# OBTENER ÚLTIMA ACTUALIZACIÓN POR SERIAL
# ============================================================

def get_latest_horometer_update_by_serial(serial):
    """
    Obtiene la última actualización de horómetro
    asociada a un número de serie.

    Utiliza JOIN entre:
        machinery
        horometer_updates

    Retorna:
        Diccionario con el último registro.

    Si no existe:
        None
    """

    serial = str(serial).strip().upper()

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT TOP 1
                hu.id,
                m.id,
                m.serial,
                m.equipment_code,
                hu.meter_id,
                hu.meter_serial,
                hu.old_value,
                hu.new_value,
                hu.difference,
                hu.source,
                hu.reading_date,
                hu.processed_at,
                hu.status,
                hu.message
            FROM horometer_updates hu
            INNER JOIN machinery m
                ON hu.machinery_id = m.id
            WHERE m.serial = ?
            ORDER BY hu.reading_date DESC, hu.id DESC
            """,
            (serial,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "machinery_id": row[1],
            "serial": row[2],
            "equipment_code": row[3],
            "meter_id": row[4],
            "meter_serial": row[5],
            "old_value": row[6],
            "new_value": row[7],
            "difference": row[8],
            "source": row[9],
            "reading_date": row[10],
            "processed_at": row[11],
            "status": row[12],
            "message": row[13]
        }

    finally:

        cursor.close()
        connection.close()


# ============================================================
# OBTENER HISTORIAL DE HORÓMETRO
# ============================================================

def get_horometer_history(serial, limit=50):
    """
    Obtiene el historial de actualizaciones de horómetro
    para una maquinaria.

    Retorna:
        Lista de diccionarios.
    """

    serial = str(serial).strip().upper()

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT TOP (?)
                hu.id,
                m.serial,
                m.equipment_code,
                hu.meter_id,
                hu.meter_serial,
                hu.old_value,
                hu.new_value,
                hu.difference,
                hu.source,
                hu.reading_date,
                hu.processed_at,
                hu.status,
                hu.message
            FROM horometer_updates hu
            INNER JOIN machinery m
                ON hu.machinery_id = m.id
            WHERE m.serial = ?
            ORDER BY hu.reading_date DESC, hu.id DESC
            """,
            (
                limit,
                serial
            )
        )

        rows = cursor.fetchall()

        history = []

        for row in rows:

            history.append(
                {
                    "id": row[0],
                    "serial": row[1],
                    "equipment_code": row[2],
                    "meter_id": row[3],
                    "meter_serial": row[4],
                    "old_value": row[5],
                    "new_value": row[6],
                    "difference": row[7],
                    "source": row[8],
                    "reading_date": row[9],
                    "processed_at": row[10],
                    "status": row[11],
                    "message": row[12]
                }
            )

        return history

    finally:

        cursor.close()
        connection.close()
def save_machine_meter(
    machinery_id,
    meter_id=None,
    meter_serial=None,
    meter_description=None,
    units_code=None,
    is_counter=None,
    current_value=None,
    status=None
):
    """
    Guarda o actualiza la relación entre una máquina y su horómetro.

    Si la máquina ya tiene un registro en machine_meters,
    lo actualiza.
    Si no existe, lo crea.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT id
            FROM machine_meters
            WHERE machinery_id = ?
            """,
            (machinery_id,)
        )

        row = cursor.fetchone()

        if row is None:

            cursor.execute(
                """
                INSERT INTO machine_meters
                (
                    machinery_id,
                    meter_id,
                    meter_serial,
                    meter_description,
                    units_code,
                    is_counter,
                    current_value,
                    status,
                    last_verified_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, SYSDATETIME())
                """,
                (
                    machinery_id,
                    meter_id,
                    meter_serial,
                    meter_description,
                    units_code,
                    is_counter,
                    current_value,
                    status
                )
            )

        else:

            cursor.execute(
                """
                UPDATE machine_meters
                SET
                    meter_id = ?,
                    meter_serial = ?,
                    meter_description = ?,
                    units_code = ?,
                    is_counter = ?,
                    current_value = ?,
                    status = ?,
                    last_verified_at = SYSDATETIME(),
                    updated_at = SYSDATETIME()
                WHERE machinery_id = ?
                """,
                (
                    meter_id,
                    meter_serial,
                    meter_description,
                    units_code,
                    is_counter,
                    current_value,
                    status,
                    machinery_id
                )
            )

        connection.commit()

    finally:
        cursor.close()
        connection.close()


def get_machine_meter(machinery_id):
    """
    Obtiene el horómetro asociado a una máquina.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                machinery_id,
                meter_id,
                meter_serial,
                meter_description,
                units_code,
                is_counter,
                current_value,
                status,
                last_verified_at,
                created_at,
                updated_at
            FROM machine_meters
            WHERE machinery_id = ?
            """,
            (machinery_id,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "machinery_id": row[1],
            "meter_id": row[2],
            "meter_serial": row[3],
            "meter_description": row[4],
            "units_code": row[5],
            "is_counter": row[6],
            "current_value": row[7],
            "status": row[8],
            "last_verified_at": row[9],
            "created_at": row[10],
            "updated_at": row[11]
        }

    finally:
        cursor.close()
        connection.close()