import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

from database import (
    upsert_machinery,
    save_horometer_update
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

CLIENT_ID = os.getenv("FRACTTAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRACTTAL_CLIENT_SECRET")

TOKEN_URL = "https://one.fracttal.com/oauth/token"

EQUIPMENT_URL = "https://app.fracttal.com/api/items/"
METERS_URL = "https://app.fracttal.com/api/meters/"
METER_READING_URL = "https://app.fracttal.com/api/meter_reading/"


# ============================================================
# AUTENTICACIÓN
# ============================================================

def get_access_token():
    """
    Obtiene un access token mediante OAuth 2.0.
    """

    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError(
            "Faltan FRACTTAL_CLIENT_ID o FRACTTAL_CLIENT_SECRET "
            "en el archivo .env"
        )

    response = requests.post(
        TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return data["access_token"]


# ============================================================
# EQUIPOS
# ============================================================

def get_equipment_by_serial(token, serial):
    """
    Busca un equipo en Fracttal utilizando su número de serie.

    Retorna:
        Diccionario con el equipo encontrado.

    Si no existe:
        None

    Si existen múltiples equipos con el mismo serial:
        ValueError
    """

    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(
        EQUIPMENT_URL,
        headers=headers,
        params={
            "item_type": 2,
            "limit": 100
        },
        timeout=30
    )

    response.raise_for_status()

    equipment_list = response.json().get("data", [])

    serial = str(serial).strip().upper()

    matches = []

    for equipment in equipment_list:

        equipment_serial = str(
            equipment.get("field_4", "")
        ).strip().upper()

        if equipment_serial == serial:
            matches.append(equipment)

    if len(matches) == 0:
        return None

    if len(matches) > 1:
        raise ValueError(
            f"Se encontraron {len(matches)} equipos "
            f"con el serial {serial}"
        )

    return matches[0]


def get_all_equipment(token):
    """
    Obtiene todos los equipos registrados en Fracttal.

    Utiliza la paginación mediante el parámetro 'start'.

    Fracttal entrega como máximo 'limit' registros por página.

    Retorna:
        Lista completa de equipos.
    """

    headers = {
        "Authorization": f"Bearer {token}"
    }

    all_equipment = []

    start = 0
    limit = 100

    # Protección contra respuestas repetidas.
    previous_first_code = None

    while True:

        response = requests.get(
            EQUIPMENT_URL,
            headers=headers,
            params={
                "item_type": 2,
                "limit": limit,
                "start": start
            },
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        equipment_page = data.get("data", [])

        # ----------------------------------------------------
        # Si no hay registros, terminamos.
        # ----------------------------------------------------

        if not equipment_page:
            break

        # ----------------------------------------------------
        # Protección contra páginas repetidas.
        # ----------------------------------------------------

        current_first_code = equipment_page[0].get("code")

        if (
            previous_first_code is not None
            and current_first_code == previous_first_code
        ):
            raise RuntimeError(
                "Fracttal devolvió nuevamente la misma página. "
                "Se detuvo la paginación para evitar un loop infinito."
            )

        previous_first_code = current_first_code

        # ----------------------------------------------------
        # Agregar registros.
        # ----------------------------------------------------

        all_equipment.extend(equipment_page)

        print(
            f"[OK] Página recibida: "
            f"{len(equipment_page)} equipos "
            f"(start={start}, "
            f"total acumulado={len(all_equipment)})"
        )

        # ----------------------------------------------------
        # Si llegaron menos de 100, es la última página.
        # ----------------------------------------------------

        if len(equipment_page) < limit:
            break

        # ----------------------------------------------------
        # Avanzar a la siguiente página.
        # ----------------------------------------------------

        start += len(equipment_page)

    return all_equipment


# ============================================================
# MEDIDORES
# ============================================================

def get_meters_by_code(token, code):
    """
    Obtiene los medidores asociados a un equipo.

    Retorna siempre una lista.
    Si Fracttal responde sin datos, retorna [].
    """

    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(
        METERS_URL,
        headers=headers,
        params={
            "code": code,
            "limit": 100
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    meters = data.get("data")

    if meters is None:
        return []

    if not isinstance(meters, list):
        raise RuntimeError(
            f"Respuesta inesperada de Fracttal para {code}: "
            f"'data' no es una lista."
        )

    return meters


def get_valid_hourmeter(token, equipment):
    """
    Identifica el horómetro válido de un equipo.

    Reglas:

    1. units_code debe ser HRS.
    2. is_counter debe ser True.
    3. No puede contener "NO UTILIZAR".
    4. Si existe un horómetro cuyo serial coincide
       con el serial del equipo, se prefiere ese.
    5. Si solamente existe un horómetro válido,
       se utiliza ese.
    6. Si existen varios y no se puede determinar
       cuál utilizar, se genera un error.
    """

    code = equipment.get("code")

    equipment_serial = str(
        equipment.get("field_4", "")
    ).strip().upper()

    meters = get_meters_by_code(
        token,
        code
    )

    valid_meters = []

    for meter in meters:

        description = str(
            meter.get("description", "")
        ).upper()

        units = meter.get("units_code")
        is_counter = meter.get("is_counter")

        # Nunca utilizar medidores marcados como
        # "NO UTILIZAR".
        if "NO UTILIZAR" in description:
            continue

        # Debe ser un medidor de horas.
        if units != "HRS":
            continue

        # Debe ser contador.
        if is_counter is not True:
            continue

        valid_meters.append(meter)

    if len(valid_meters) == 0:
        return None

    # --------------------------------------------------------
    # Buscar coincidencia por serial
    # --------------------------------------------------------

    for meter in valid_meters:

        meter_serial = str(
            meter.get("serial", "")
        ).strip().upper()

        if meter_serial and meter_serial == equipment_serial:
            return meter

    # --------------------------------------------------------
    # Si existe solamente uno, utilizarlo
    # --------------------------------------------------------

    if len(valid_meters) == 1:
        return valid_meters[0]

    # --------------------------------------------------------
    # Ambigüedad
    # --------------------------------------------------------

    raise ValueError(
        f"El activo {code} tiene "
        f"{len(valid_meters)} horómetros válidos y "
        "no fue posible determinar cuál utilizar "
        "por número de serie."
    )


# ============================================================
# LECTURA ACTUAL
# ============================================================

def get_current_hourmeter(token, equipment):
    """
    Obtiene el horómetro válido y su valor actual.
    """

    meter = get_valid_hourmeter(
        token,
        equipment
    )

    if meter is None:
        return None

    return {
        "meter": meter,
        "value": meter.get("counter_value")
    }


# ============================================================
# VALIDACIÓN DEL NUEVO HORÓMETRO
# ============================================================

def validate_hourmeter_update(current_value, new_value):
    """
    Determina qué acción corresponde realizar.

    Reglas:

        current = None → UPDATE

        new == current → SKIP

        new > current → UPDATE

        new < current → REJECT
    """

    if current_value is None:
        return "UPDATE"

    if new_value == current_value:
        return "SKIP"

    if new_value > current_value:
        return "UPDATE"

    if new_value < current_value:
        return "REJECT"

    return "REJECT"


# ============================================================
# ACTUALIZAR HORÓMETRO EN FRACTTAL
# ============================================================

def insert_meter_reading(
    token,
    code,
    value,
    serial
):
    """
    Registra una nueva lectura de horómetro en Fracttal.
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    date = datetime.now(
        timezone.utc
    ).isoformat()

    body = {
        "date": date,
        "value": value,
        "serial": serial,
        "is_historical": False
    }

    response = requests.put(
        f"{METER_READING_URL}{code}",
        headers=headers,
        json=body,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# PROCESAR UN EQUIPO
# ============================================================

def process_equipment(
    token,
    serial,
    new_value,
    dry_run=True
):
    """
    Procesa una lectura de horómetro.

    Flujo:

        1. Buscar equipo en Fracttal.
        2. Crear/actualizar maquinaria en SQL.
        3. Buscar horómetro válido.
        4. Comparar valores.
        5. Determinar UPDATE / SKIP / REJECT.
        6. Registrar resultado en SQL.
        7. Si corresponde y dry_run=False,
           actualizar Fracttal.

    IMPORTANTE:

        dry_run=True
        nunca modifica Fracttal.
    """

    serial = str(serial).strip().upper()

    print()
    print("=" * 60)
    print(f"PROCESANDO SERIAL: {serial}")
    print("=" * 60)

    # ========================================================
    # 1. BUSCAR EQUIPO EN FRACTTAL
    # ========================================================

    equipment = get_equipment_by_serial(
        token,
        serial
    )

    if equipment is None:

        print(
            "[ERROR] Equipo no encontrado en Fracttal."
        )

        print(
            f"        Serial: {serial}"
        )

        save_horometer_update(
            machinery_id=None,
            meter_id=None,
            meter_serial=None,
            old_value=None,
            new_value=new_value,
            source="MyDevelon",
            reading_date=datetime.now(),
            status="NOT_FOUND",
            message=(
                f"Equipo no encontrado en Fracttal. "
                f"Serial: {serial}"
            )
        )

        return {
            "status": "NOT_FOUND",
            "serial": serial
        }

    # ========================================================
    # 2. DATOS DEL EQUIPO
    # ========================================================

    code = equipment.get("code")
    name = equipment.get("field_1")
    manufacturer = equipment.get("field_2")
    model = equipment.get("field_3")
    fracttal_serial = equipment.get("field_4")

    print()
    print("[OK] Equipo encontrado")
    print(f"     Código: {code}")
    print(f"     Nombre: {name}")
    print(f"     Fabricante: {manufacturer}")
    print(f"     Modelo: {model}")
    print(f"     Serial: {fracttal_serial}")

    # ========================================================
    # 3. GUARDAR / ACTUALIZAR MAQUINARIA EN SQL
    # ========================================================

    machinery = upsert_machinery(
        serial=serial,
        equipment_code=code,
        name=name,
        manufacturer=manufacturer,
        model=model
    )

    machinery_id = machinery["id"]

    print()
    print(
        f"[OK] Machinery ID: {machinery_id}"
    )

    # ========================================================
    # 4. OBTENER HORÓMETRO
    # ========================================================

    try:

        result = get_current_hourmeter(
            token,
            equipment
        )

    except Exception as error:

        print()
        print(
            "[ERROR] Error identificando el horómetro."
        )
        print(
            f"        {error}"
        )

        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=None,
            meter_serial=None,
            old_value=None,
            new_value=new_value,
            source="MyDevelon",
            reading_date=datetime.now(),
            status="ERROR",
            message=str(error)
        )

        return {
            "status": "ERROR",
            "serial": serial,
            "code": code,
            "error": str(error)
        }

    if result is None:

        print()
        print(
            "[ERROR] No se encontró un horómetro válido."
        )

        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=None,
            meter_serial=None,
            old_value=None,
            new_value=new_value,
            source="MyDevelon",
            reading_date=datetime.now(),
            status="METER_NOT_FOUND",
            message=(
                f"No se encontró horómetro válido "
                f"para el activo {code}"
            )
        )

        return {
            "status": "METER_NOT_FOUND",
            "serial": serial,
            "code": code
        }

    # ========================================================
    # 5. DATOS DEL HORÓMETRO
    # ========================================================

    meter = result["meter"]
    current_value = result["value"]

    meter_id = meter.get("id")
    meter_serial = meter.get("serial")
    meter_description = meter.get("description")

    print()
    print("[OK] Horómetro encontrado")
    print(f"     ID: {meter_id}")
    print(f"     Descripción: {meter_description}")
    print(f"     Serial: {meter_serial}")
    print(f"     Valor Fracttal: {current_value}")

    # ========================================================
    # 6. VALIDAR ACTUALIZACIÓN
    # ========================================================

    action = validate_hourmeter_update(
        current_value,
        new_value
    )

    print()
    print(f"Valor MyDevelon: {new_value}")
    print(f"Acción: {action}")

    # ========================================================
    # 7. SKIP
    # ========================================================

    if action == "SKIP":

        print()
        print(
            "[SKIP] El horómetro ya tiene el mismo valor."
        )

        print(
            "       No se realizará ninguna modificación."
        )

        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=meter_id,
            meter_serial=meter_serial,
            old_value=current_value,
            new_value=new_value,
            source="MyDevelon",
            reading_date=datetime.now(),
            status="SKIPPED",
            message=(
                "El valor recibido es igual "
                "al valor actual de Fracttal."
            )
        )

        return {
            "status": "SKIPPED",
            "serial": serial,
            "code": code,
            "old_value": current_value,
            "new_value": new_value
        }

    # ========================================================
    # 8. REJECT
    # ========================================================

    if action == "REJECT":

        print()
        print(
            "[REJECT] El nuevo valor es menor que "
            "el valor registrado actualmente."
        )

        print(
            "         NO se realizará ninguna modificación."
        )

        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=meter_id,
            meter_serial=meter_serial,
            old_value=current_value,
            new_value=new_value,
            source="MyDevelon",
            reading_date=datetime.now(),
            status="REJECTED",
            message=(
                "El valor recibido es menor "
                "que el valor actual de Fracttal."
            )
        )

        return {
            "status": "REJECTED",
            "serial": serial,
            "code": code,
            "old_value": current_value,
            "new_value": new_value
        }

    # ========================================================
    # 9. UPDATE
    # ========================================================

    print()
    print(
        f"[UPDATE] {current_value} -> {new_value}"
    )

    # ========================================================
    # 10. DRY RUN
    # ========================================================

    if dry_run:

        print()
        print(
            "[DRY RUN] Simulación solamente."
        )

        print(
            "          No se modificó Fracttal."
        )

        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=meter_id,
            meter_serial=meter_serial,
            old_value=current_value,
            new_value=new_value,
            source="MyDevelon",
            reading_date=datetime.now(),
            status="WOULD_UPDATE",
            message=(
                "Simulación DRY RUN. "
                "Fracttal no fue modificado."
            )
        )

        return {
            "status": "WOULD_UPDATE",
            "serial": serial,
            "code": code,
            "old_value": current_value,
            "new_value": new_value
        }

    # ========================================================
    # 11. ESCRIBIR EN FRACTTAL
    # ========================================================

    try:

        response = insert_meter_reading(
            token,
            code,
            new_value,
            meter_serial
        )

    except Exception as error:

        print()
        print(
            "[ERROR] No fue posible actualizar "
            "el horómetro en Fracttal."
        )

        print(
            f"        {error}"
        )

        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=meter_id,
            meter_serial=meter_serial,
            old_value=current_value,
            new_value=new_value,
            source="MyDevelon",
            reading_date=datetime.now(),
            status="ERROR",
            message=str(error)
        )

        return {
            "status": "ERROR",
            "serial": serial,
            "code": code,
            "old_value": current_value,
            "new_value": new_value,
            "error": str(error)
        }

    # ========================================================
    # 12. REGISTRAR ACTUALIZACIÓN EXITOSA
    # ========================================================

    print()
    print(
        "[OK] Horómetro actualizado correctamente."
    )

    save_horometer_update(
        machinery_id=machinery_id,
        meter_id=meter_id,
        meter_serial=meter_serial,
        old_value=current_value,
        new_value=new_value,
        source="MyDevelon",
        reading_date=datetime.now(),
        status="UPDATED",
        message="Horómetro actualizado correctamente en Fracttal."
    )

    return {
        "status": "UPDATED",
        "serial": serial,
        "code": code,
        "old_value": current_value,
        "new_value": new_value,
        "response": response
    }