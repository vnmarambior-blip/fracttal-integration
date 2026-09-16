import os

import mssql_python
from dotenv import load_dotenv
from datetime import datetime


class IdempotencyConflictError(RuntimeError):
    """La lectura ya fue reservada por otra ejecución."""


# ============================================================
# CONFIGURACIÓN SQL SERVER
# ============================================================

load_dotenv()

# En producción se configura como secreto (SQL_CONNECTION_STRING). Mantener
# este valor por defecto permite seguir usando el entorno local de desarrollo.
CONNECTION_STRING = os.getenv(
    "SQL_CONNECTION_STRING",
    (
        "Server=localhost;"
        "Database=FracttalIntegration;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    ),
)


# ============================================================
# CONEXIÓN
# ============================================================

def get_connection():
    """
    Crea una conexión con SQL Server.
    """

    return mssql_python.connect(
        CONNECTION_STRING
    )


# ============================================================
# INICIALIZACIÓN / MIGRACIONES
# ============================================================

def initialize_database():
    """
    Verifica que la estructura necesaria de la base de datos
    exista y agrega las columnas nuevas cuando corresponda.

    Esta función NO elimina datos.

    Columnas verificadas:

        machinery.asset_type
        machinery.asset_group_1
        machinery.asset_group_2
        machine_meters.telemetry_source
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ====================================================
        # MACHINERY - ASSET TYPE
        # ====================================================

        machinery_columns = [
            (
                "asset_type",
                "VARCHAR(100) NULL"
            ),
            (
                "asset_group_1",
                "VARCHAR(100) NULL"
            ),
            (
                "asset_group_2",
                "VARCHAR(100) NULL"
            )
        ]

        for column_name, column_definition in machinery_columns:

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'machinery'
                  AND COLUMN_NAME = ?
                """,
                (column_name,)
            )

            exists = cursor.fetchone()[0]

            if exists == 0:

                print(
                    f"[DB] Agregando columna "
                    f"machinery.{column_name}..."
                )

                cursor.execute(
                    f"""
                    ALTER TABLE machinery
                    ADD {column_name} {column_definition}
                    """
                )

                connection.commit()

                print(
                    f"[OK] Columna "
                    f"machinery.{column_name} creada."
                )

            else:

                print(
                    f"[OK] Columna "
                    f"machinery.{column_name} ya existe."
                )

        # ====================================================
        # MACHINE METERS - TELEMETRY SOURCE
        # ====================================================

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'machine_meters'
              AND COLUMN_NAME = 'telemetry_source'
            """
        )

        exists = cursor.fetchone()[0]

        if exists == 0:

            print(
                "[DB] Agregando columna "
                "machine_meters.telemetry_source..."
            )

            cursor.execute(
                """
                ALTER TABLE machine_meters
                ADD telemetry_source VARCHAR(50) NULL
                """
            )

            connection.commit()

            print(
                "[OK] Columna telemetry_source creada."
            )

        else:

            print(
                "[OK] Columna telemetry_source ya existe."
            )

    finally:

        cursor.close()
        connection.close()


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
                asset_type,
                asset_group_1,
                asset_group_2,
                active,
                created_at,
                updated_at
            FROM machinery
            WHERE serial = ?
            """,
            (serial,)
        )

        rows = cursor.fetchall()

        if not rows:
            return None

        if len(rows) > 1:
            raise ValueError(
                f"DUPLICATE_IDENTITY: se encontraron {len(rows)} "
                f"maquinarias con el serial {serial}."
            )

        row = rows[0]

        return {
            "id": row[0],
            "serial": row[1],
            "equipment_code": row[2],
            "name": row[3],
            "manufacturer": row[4],
            "model": row[5],
            "asset_type": row[6],
            "asset_group_1": row[7],
            "asset_group_2": row[8],
            "active": row[9],
            "created_at": row[10],
            "updated_at": row[11]
        }

    finally:

        cursor.close()
        connection.close()


def get_machinery_by_id(machinery_id):
    """
    Busca una maquinaria por ID y exige una identidad única.

    Retorna None si no existe y lanza ValueError si el ID no es único.
    """

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
                asset_type,
                asset_group_1,
                asset_group_2,
                active,
                created_at,
                updated_at
            FROM machinery
            WHERE id = ?
            """,
            (machinery_id,)
        )

        rows = cursor.fetchall()

        if not rows:
            return None

        if len(rows) > 1:
            raise ValueError(
                "DUPLICATE_IDENTITY: se encontraron "
                f"{len(rows)} maquinarias con id={machinery_id}."
            )

        row = rows[0]

        return {
            "id": row[0],
            "serial": row[1],
            "equipment_code": row[2],
            "name": row[3],
            "manufacturer": row[4],
            "model": row[5],
            "asset_type": row[6],
            "asset_group_1": row[7],
            "asset_group_2": row[8],
            "active": row[9],
            "created_at": row[10],
            "updated_at": row[11]
        }

    finally:

        cursor.close()
        connection.close()


# ============================================================
# CONFIGURACIÓN DE TELEMETRÍA
# ============================================================

def get_telemetry_sync_config(machinery_id, telemetry_source):
    """
    Obtiene la única configuración aplicable a una maquinaria y fuente.

    Retorna None si no existe configuración.
    Genera un error si existe más de una configuración aplicable.
    """

    telemetry_source = str(
        telemetry_source
    ).strip().upper()

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                machinery_id,
                telemetry_source,
                sync_enabled,
                action_policy,
                comparison_basis,
                reason,
                notes,
                created_at,
                updated_at
            FROM telemetry_sync_config
            WHERE machinery_id = ?
              AND telemetry_source = ?
            ORDER BY id
            """,
            (
                machinery_id,
                telemetry_source
            )
        )

        rows = cursor.fetchall()

        if len(rows) > 1:
            raise ValueError(
                "Existe más de una configuración de telemetría "
                f"para machinery_id={machinery_id} y "
                f"telemetry_source={telemetry_source}."
            )

        if not rows:
            return None

        row = rows[0]

        return {
            "id": row[0],
            "machinery_id": row[1],
            "telemetry_source": row[2],
            "sync_enabled": row[3],
            "action_policy": row[4],
            "comparison_basis": row[5],
            "reason": row[6],
            "notes": row[7],
            "created_at": row[8],
            "updated_at": row[9]
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
    asset_type=None,
    asset_group_1=None,
    asset_group_2=None,
    active=True
):
    """
    Sincroniza una maquinaria proveniente de Fracttal.

    Orden de identificación:

        1. Buscar por serial.
        2. Si no existe, buscar por equipment_code.
        3. Si existe el equipment_code, actualizar ese registro
           con el nuevo serial.
        4. Si no existe ninguno, crear un nuevo registro.

    Fracttal actúa como fuente maestra para la identificación
    actual del activo.

    La clasificación proviene directamente de Fracttal:

        asset_type     -> groups_description
        asset_group_1  -> groups_1_description
        asset_group_2  -> groups_2_description

    Retorna:
        Diccionario con los datos actuales de la maquinaria.
    """

    serial = str(serial).strip().upper()

    if equipment_code is not None:

        equipment_code = str(
            equipment_code
        ).strip().upper()

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ====================================================
        # 1. BUSCAR POR SERIAL
        # ====================================================

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
        # SERIAL ENCONTRADO
        # ----------------------------------------------------

        if row is not None:

            machinery_id = row[0]

            cursor.execute(
                """
                UPDATE machinery
                SET
                    equipment_code = ?,
                    name = ?,
                    manufacturer = ?,
                    model = ?,
                    asset_type = ?,
                    asset_group_1 = ?,
                    asset_group_2 = ?,
                    active = ?,
                    updated_at = SYSDATETIME()
                WHERE id = ?
                """,
                (
                    equipment_code,
                    name,
                    manufacturer,
                    model,
                    asset_type,
                    asset_group_1,
                    asset_group_2,
                    active,
                    machinery_id
                )
            )

            connection.commit()

            print(
                f"[OK] Maquinaria actualizada por serial: "
                f"{serial}"
            )

            return get_machinery_by_serial(serial)

        # ====================================================
        # 2. BUSCAR POR EQUIPMENT CODE
        # ====================================================

        if equipment_code:

            cursor.execute(
                """
                SELECT
                    id,
                    serial
                FROM machinery
                WHERE equipment_code = ?
                """,
                (equipment_code,)
            )

            row = cursor.fetchone()

            # ------------------------------------------------
            # CÓDIGO ENCONTRADO
            # ------------------------------------------------

            if row is not None:

                machinery_id = row[0]
                old_serial = row[1]

                cursor.execute(
                    """
                    UPDATE machinery
                    SET
                        serial = ?,
                        name = ?,
                        manufacturer = ?,
                        model = ?,
                        asset_type = ?,
                        asset_group_1 = ?,
                        asset_group_2 = ?,
                        active = ?,
                        updated_at = SYSDATETIME()
                    WHERE id = ?
                    """,
                    (
                        serial,
                        name,
                        manufacturer,
                        model,
                        asset_type,
                        asset_group_1,
                        asset_group_2,
                        active,
                        machinery_id
                    )
                )

                connection.commit()

                print(
                    f"[OK] Maquinaria actualizada por código: "
                    f"{equipment_code}"
                )

                print(
                    f"     Serial anterior: {old_serial}"
                )

                print(
                    f"     Serial nuevo:    {serial}"
                )

                return get_machinery_by_serial(serial)

        # ====================================================
        # 3. CREAR NUEVA MAQUINARIA
        # ====================================================

        cursor.execute(
            """
            INSERT INTO machinery
            (
                serial,
                equipment_code,
                name,
                manufacturer,
                model,
                asset_type,
                asset_group_1,
                asset_group_2,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                serial,
                equipment_code,
                name,
                manufacturer,
                model,
                asset_type,
                asset_group_1,
                asset_group_2,
                active
            )
        )

        connection.commit()

        print(
            f"[OK] Maquinaria creada en SQL Server: "
            f"{serial}"
        )

        return get_machinery_by_serial(serial)

    finally:

        cursor.close()
        connection.close()


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
    message=None,
    idempotency_key=None,
    source_reading_datetime=None,
    source_value=None,
    decision=None,
    write_status=None,
    http_status=None,
    fracttal_reading_id=None,
    fracttal_is_duplicate=None,
    verification_value=None,
    verification_status=None,
    error_code=None,
    attempt_count=0,
    last_attempt_at=None
):
    """
    Registra un evento de horómetro en horometer_updates.

    source representa el origen de la lectura.

    Ejemplos:

        MyDevelon
        KOMTRAX
        SENNEBOGEN
    """

    if reading_date is None:
        reading_date = datetime.now()

    connection = get_connection()

    try:

        cursor = connection.cursor()

        if idempotency_key is not None:
            cursor.execute(
                """
                SELECT TOP 1 id
                FROM horometer_updates
                WHERE idempotency_key = ?
                ORDER BY id DESC
                """,
                (idempotency_key,)
            )
            existing = cursor.fetchone()
            if existing is not None:
                return existing[0]

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
                message,
                idempotency_key,
                source_reading_datetime,
                source_value,
                decision,
                write_status,
                http_status,
                fracttal_reading_id,
                fracttal_is_duplicate,
                verification_value,
                verification_status,
                error_code,
                attempt_count,
                last_attempt_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                message,
                idempotency_key,
                source_reading_datetime,
                source_value,
                decision,
                write_status,
                http_status,
                fracttal_reading_id,
                fracttal_is_duplicate,
                verification_value,
                verification_status,
                error_code,
                attempt_count,
                last_attempt_at
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


def get_horometer_update_by_idempotency_key(idempotency_key):
    """Obtiene el evento de horómetro asociado a una lectura exacta."""

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
                source,
                reading_date,
                status,
                message,
                idempotency_key,
                source_reading_datetime,
                source_value,
                decision,
                write_status,
                http_status,
                fracttal_reading_id,
                fracttal_is_duplicate,
                verification_value,
                verification_status,
                error_code,
                attempt_count,
                last_attempt_at
            FROM horometer_updates
            WHERE idempotency_key = ?
            ORDER BY id DESC
            """,
            (idempotency_key,)
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
            "source": row[6],
            "reading_date": row[7],
            "status": row[8],
            "message": row[9],
            "idempotency_key": row[10],
            "source_reading_datetime": row[11],
            "source_value": row[12],
            "decision": row[13],
            "write_status": row[14],
            "http_status": row[15],
            "fracttal_reading_id": row[16],
            "fracttal_is_duplicate": row[17],
            "verification_value": row[18],
            "verification_status": row[19],
            "error_code": row[20],
            "attempt_count": row[21],
            "last_attempt_at": row[22]
        }
    finally:
        cursor.close()
        connection.close()


def create_horometer_write_intent(
    machinery_id,
    meter_id,
    meter_serial,
    old_value,
    new_value,
    source,
    reading_date,
    idempotency_key,
    source_reading_datetime,
    source_value,
    decision,
    message=None
):
    """Reserva una lectura antes del PUT y devuelve su ID."""

    connection = get_connection()

    try:
        cursor = connection.cursor()
        try:
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
                message,
                idempotency_key,
                source_reading_datetime,
                source_value,
                decision,
                write_status,
                attempt_count,
                last_attempt_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                machinery_id,
                meter_id,
                meter_serial,
                old_value,
                new_value,
                source,
                reading_date,
                "INTENT_RECORDED",
                message,
                idempotency_key,
                source_reading_datetime,
                source_value,
                decision,
                "INTENT_RECORDED",
                1,
                reading_date
                )
            )
        except Exception as error:
            connection.rollback()
            error_text = str(error).lower()
            if (
                "ux_horometer_updates_idempotency_key" in error_text
                or "duplicate key" in error_text
                or "unique index" in error_text
            ):
                raise IdempotencyConflictError(
                    "La idempotency_key ya fue reservada."
                ) from error
            raise
        cursor.execute(
            "SELECT CAST(SCOPE_IDENTITY() AS BIGINT)"
        )
        event_id = cursor.fetchone()[0]
        connection.commit()
        return event_id
    finally:
        cursor.close()
        connection.close()


def mark_horometer_write_in_progress(event_id):
    """Marca la intención justo antes de invocar el único PUT."""

    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE horometer_updates
            SET
                status = 'WRITE_IN_PROGRESS',
                write_status = 'WRITE_IN_PROGRESS',
                last_attempt_at = SYSDATETIME(),
                processed_at = NULL
            WHERE id = ?
            """,
            (event_id,)
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def update_horometer_write_result(
    event_id,
    *,
    status,
    write_status,
    http_status=None,
    fracttal_reading_id=None,
    fracttal_is_duplicate=None,
    verification_value=None,
    verification_status=None,
    error_code=None,
    message=None,
    attempt_count=1,
    last_attempt_at=None
):
    """Actualiza el resultado del PUT y de su GET de verificación."""

    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE horometer_updates
            SET
                status = ?,
                write_status = ?,
                http_status = ?,
                fracttal_reading_id = ?,
                fracttal_is_duplicate = ?,
                verification_value = ?,
                verification_status = ?,
                error_code = ?,
                message = ?,
                attempt_count = ?,
                last_attempt_at = COALESCE(?, SYSDATETIME()),
                processed_at = SYSDATETIME()
            WHERE id = ?
            """,
            (
                status,
                write_status,
                http_status,
                fracttal_reading_id,
                fracttal_is_duplicate,
                verification_value,
                verification_status,
                error_code,
                message,
                attempt_count,
                last_attempt_at,
                event_id
            )
        )
        connection.commit()
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
    """

    serial = str(serial).strip().upper()

    limit = int(limit)

    if limit <= 0:
        limit = 50

    connection = get_connection()

    try:

        cursor = connection.cursor()

        query = f"""
            SELECT TOP {limit}
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
        """

        cursor.execute(
            query,
            (serial,)
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


# ============================================================
# GUARDAR / ACTUALIZAR HORÓMETRO DE MÁQUINA
# ============================================================

def save_machine_meter(
    machinery_id,
    meter_id=None,
    meter_serial=None,
    meter_description=None,
    units_code=None,
    is_counter=None,
    current_value=None,
    status=None,
    telemetry_source=None
):
    """
    Guarda o actualiza la relación entre una máquina
    y su horómetro.

    telemetry_source:
        Fuente desde la cual se obtiene la telemetría.

    Ejemplos:

        MyDevelon
        KOMTRAX
        SENNEBOGEN

    El valor puede quedar NULL mientras la integración
    todavía no esté definida.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Buscar relación existente
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM machine_meters
            WHERE machinery_id = ?
            """,
            (machinery_id,)
        )

        row = cursor.fetchone()

        # ----------------------------------------------------
        # CREAR
        # ----------------------------------------------------

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
                    telemetry_source,
                    last_verified_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, SYSDATETIME())
                """,
                (
                    machinery_id,
                    meter_id,
                    meter_serial,
                    meter_description,
                    units_code,
                    is_counter,
                    current_value,
                    status,
                    telemetry_source
                )
            )

        # ----------------------------------------------------
        # ACTUALIZAR
        # ----------------------------------------------------

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
                    telemetry_source = ?,
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
                    telemetry_source,
                    machinery_id
                )
            )

        connection.commit()

        print(
            "[OK] Relación máquina-horómetro guardada."
        )

    finally:

        cursor.close()
        connection.close()


# ============================================================
# OBTENER HORÓMETRO DE UNA MÁQUINA
# ============================================================

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
                telemetry_source,
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
            "telemetry_source": row[9],
            "last_verified_at": row[10],
            "created_at": row[11],
            "updated_at": row[12]
        }

    finally:

        cursor.close()
        connection.close()
