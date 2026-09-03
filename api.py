import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv


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
    Obtiene un Access Token desde Fracttal.
    """

    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError(
            "Faltan FRACTTAL_CLIENT_ID o FRACTTAL_CLIENT_SECRET en el archivo .env"
        )

    response = requests.post(
        TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        data={
            "grant_type": "client_credentials"
        },
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

    Fracttal:
        item_type = 2 -> Equipos

    Campo utilizado:
        field_4 -> Número de serie
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
            f"Se encontraron {len(matches)} equipos con el serial {serial}"
        )

    return matches[0]


# ============================================================
# MEDIDORES
# ============================================================

def get_meters_by_code(token, code):
    """
    Obtiene los medidores asociados a un activo.
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

    return response.json().get("data", [])


def get_valid_hourmeter(token, equipment):
    """
    Busca el horómetro válido de un equipo.

    Reglas:

    1. units_code debe ser HRS
    2. is_counter debe ser True
    3. No debe contener "NO UTILIZAR"
    4. Si existe un serial de equipo, se intenta
       priorizar un medidor cuyo serial coincida.
    """

    code = equipment.get("code")
    equipment_serial = str(
        equipment.get("field_4", "")
    ).strip().upper()

    meters = get_meters_by_code(token, code)

    valid_meters = []

    for meter in meters:

        description = str(
            meter.get("description", "")
        ).upper()

        units = meter.get("units_code")
        is_counter = meter.get("is_counter")

        # Nunca utilizar medidores históricos marcados
        # como "NO UTILIZAR".
        if "NO UTILIZAR" in description:
            continue

        # Debe ser un medidor de horas y contador.
        if units != "HRS":
            continue

        if is_counter is not True:
            continue

        valid_meters.append(meter)

    if len(valid_meters) == 0:
        return None

    # --------------------------------------------------------
    # PRIORIDAD 1:
    # Buscar medidor cuyo serial coincida con el equipo.
    # --------------------------------------------------------

    for meter in valid_meters:

        meter_serial = str(
            meter.get("serial", "")
        ).strip().upper()

        if meter_serial and meter_serial == equipment_serial:
            return meter

    # --------------------------------------------------------
    # PRIORIDAD 2:
    # Si existe exactamente un medidor válido,
    # utilizarlo.
    # --------------------------------------------------------

    if len(valid_meters) == 1:
        return valid_meters[0]

    # --------------------------------------------------------
    # Si existen varios medidores válidos y ninguno
    # coincide por serial, no elegir arbitrariamente.
    # --------------------------------------------------------

    raise ValueError(
        f"El activo {code} tiene {len(valid_meters)} "
        "horómetros válidos y no fue posible determinar "
        "cuál utilizar por número de serie."
    )


# ============================================================
# LECTURA ACTUAL
# ============================================================

def get_current_hourmeter(token, equipment):
    """
    Obtiene el horómetro válido y su valor actual.
    """

    meter = get_valid_hourmeter(token, equipment)

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
    Determina qué hacer con una nueva lectura.

    Retorna:

        UPDATE
        SKIP
        REJECT
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
# ACTUALIZAR HORÓMETRO
# ============================================================

def insert_meter_reading(token, code, value, serial):
    """
    Inserta una nueva lectura de horómetro en Fracttal.

    Endpoint:
        PUT /api/meter_reading/{code}
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    date = datetime.now(timezone.utc).isoformat()

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

def process_equipment(token, serial, new_value, dry_run=True):
    """
    Procesa una actualización de horómetro.

    Flujo:

        Serial
           ↓
        Buscar equipo
           ↓
        Buscar horómetro
           ↓
        Comparar valores
           ↓
        UPDATE / SKIP / REJECT

    dry_run=True:
        NO modifica Fracttal.

    dry_run=False:
        Puede modificar Fracttal.
    """

    print()
    print("=" * 60)
    print(f"PROCESANDO SERIAL: {serial}")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Buscar equipo
    # --------------------------------------------------------

    equipment = get_equipment_by_serial(
        token,
        serial
    )

    if equipment is None:

        print("[ERROR] Equipo no encontrado en Fracttal.")
        print(f"        Serial: {serial}")

        return {
            "status": "NOT_FOUND",
            "serial": serial
        }

    code = equipment.get("code")
    description = equipment.get("description")
    equipment_name = equipment.get("field_1")

    print(f"[OK] Equipo encontrado")
    print(f"     Código: {code}")
    print(f"     Nombre: {equipment_name}")
    print(f"     Serial: {equipment.get('field_4')}")

    # --------------------------------------------------------
    # 2. Buscar horómetro
    # --------------------------------------------------------

    result = get_current_hourmeter(
        token,
        equipment
    )

    if result is None:

        print("[ERROR] No se encontró un horómetro válido.")

        return {
            "status": "METER_NOT_FOUND",
            "serial": serial,
            "code": code
        }

    meter = result["meter"]
    current_value = result["value"]

    meter_serial = meter.get("serial")
    meter_description = meter.get("description")

    print()
    print("[OK] Horómetro encontrado")
    print(f"     Descripción: {meter_description}")
    print(f"     Serial: {meter_serial}")
    print(f"     Valor Fracttal: {current_value}")

    # --------------------------------------------------------
    # 3. Validar nuevo valor
    # --------------------------------------------------------

    action = validate_hourmeter_update(
        current_value,
        new_value
    )

    print()
    print(f"Valor MyDevelon: {new_value}")
    print(f"Acción: {action}")

    # --------------------------------------------------------
    # 4. SKIP
    # --------------------------------------------------------

    if action == "SKIP":

        print()
        print("[SKIP] El horómetro ya tiene el mismo valor.")
        print("       No se realizará ninguna modificación.")

        return {
            "status": "SKIPPED",
            "serial": serial,
            "code": code,
            "old_value": current_value,
            "new_value": new_value
        }

    # --------------------------------------------------------
    # 5. REJECT
    # --------------------------------------------------------

    if action == "REJECT":

        print()
        print("[REJECT] El nuevo valor es menor que el valor")
        print("         registrado actualmente en Fracttal.")
        print("         NO se realizará ninguna modificación.")

        return {
            "status": "REJECTED",
            "serial": serial,
            "code": code,
            "old_value": current_value,
            "new_value": new_value
        }

    # --------------------------------------------------------
    # 6. UPDATE
    # --------------------------------------------------------

    print()
    print(
        f"[UPDATE] {current_value} -> {new_value}"
    )

    # Modo simulación
    if dry_run:

        print()
        print("[DRY RUN] Simulación solamente.")
        print("          No se modificó Fracttal.")

        return {
            "status": "WOULD_UPDATE",
            "serial": serial,
            "code": code,
            "old_value": current_value,
            "new_value": new_value
        }

    # --------------------------------------------------------
    # 7. Escritura real
    # --------------------------------------------------------

    response = insert_meter_reading(
        token,
        code,
        new_value,
        meter_serial
    )

    print()
    print("[OK] Horómetro actualizado correctamente.")

    return {
        "status": "UPDATED",
        "serial": serial,
        "code": code,
        "old_value": current_value,
        "new_value": new_value,
        "response": response
    }