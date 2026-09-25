import os
import math
import hashlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

from database import (
    upsert_machinery,
    save_horometer_update,
    get_telemetry_sync_config,
    get_machinery_by_id,
    get_horometer_update_by_idempotency_key,
    create_horometer_write_intent,
    update_horometer_write_result,
    mark_horometer_write_in_progress,
    IdempotencyConflictError,
    PersistenceError
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

MAX_FUTURE_SKEW_MINUTES = 5.0

_APPLY_WRITE_CONTEXT = object()
_MISSING_METER_SERIAL_ALLOWLIST = {
    ("MH07", "1028944"),
}


class RetryableWriteError(RuntimeError):
    """Error demostrado antes de enviar una solicitud de escritura."""


class FracttalResponseError(RuntimeError):
    """La API respondió, pero no entregó un resultado utilizable."""

    def __init__(self, status_code, body, message):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class NoNewReadingError(ValueError):
    """La lectura OEM no es posterior a la lectura ya registrada."""


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

    El número de serie se busca en field_4.

    La búsqueda utiliza paginación para recorrer todos los
    equipos registrados en Fracttal.

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

    serial = str(serial).strip().upper()

    start = 0
    limit = 100

    matches = []

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

        if not equipment_page:
            break

        current_first_code = equipment_page[0].get("code")

        if (
            previous_first_code is not None
            and current_first_code == previous_first_code
        ):
            raise RuntimeError(
                "Fracttal devolvió nuevamente la misma página. "
                "Se detuvo la búsqueda para evitar un loop infinito."
            )

        previous_first_code = current_first_code

        for equipment in equipment_page:

            equipment_serial = str(
                equipment.get("field_4", "")
            ).strip().upper()

            if equipment_serial == serial:
                matches.append(equipment)

        # ----------------------------------------------------
        # Si la página tiene menos registros que el límite,
        # significa que llegamos al final
        # ----------------------------------------------------

        if len(equipment_page) < limit:
            break

        start += len(equipment_page)

    if len(matches) > 1:
        raise ValueError(
            f"DUPLICATE_IDENTITY: se encontraron {len(matches)} "
            f"equipos con el serial {serial}"
        )

    if len(matches) == 1:
        return matches[0]

    return None


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

        if not equipment_page:
            break

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

        all_equipment.extend(equipment_page)

        print(
            f"[OK] Página recibida: "
            f"{len(equipment_page)} equipos "
            f"(start={start}, "
            f"total acumulado={len(all_equipment)})"
        )

        if len(equipment_page) < limit:
            break

        start += len(equipment_page)

    return all_equipment


# ============================================================
# CLASIFICACIÓN DEL ACTIVO
# ============================================================

def get_asset_type(equipment):
    """
    Obtiene la clasificación del activo directamente desde
    la configuración de Fracttal.

    Fuente maestra:

        groups_description

    Equivalencia con Fracttal:

        groups_description      -> asset_type
        groups_1_description    -> asset_group_1
        groups_2_description    -> asset_group_2

    Ejemplos:

        EXCAVADORA
        CARGADOR FRONTAL
        CAMA BAJA
        CAMIONETAS
        ELECTROIMAN CHINO
        GENERADOR DYNASET
        GRUA FORESTAL
        MINI CARGADOR
        MOTONIVELADORA
        RAMPLA
        REMOLQUES
        RETROCARGADORA
        TRACTO CAMION

    IMPORTANTE:

        - No modifica equipment_code.
        - No utiliza manufacturer para clasificar.
        - No utiliza model para clasificar.
        - Fracttal es la fuente de verdad para el tipo.

    Si Fracttal no tiene groups_description:

        asset_type = "NO CLASIFICADO"

    Retorna:

        {
            "asset_type": ...,
            "group": ...,
            "group_1": ...,
            "group_2": ...,
            "classified": True/False
        }
    """

    if not equipment:
        return {
            "asset_type": "NO CLASIFICADO",
            "group": None,
            "group_1": None,
            "group_2": None,
            "classified": False
        }

    group = equipment.get("groups_description")
    group_1 = equipment.get("groups_1_description")
    group_2 = equipment.get("groups_2_description")

    if group:

        asset_type = str(
            group
        ).strip().upper()

    else:

        asset_type = "NO CLASIFICADO"

    return {
        "asset_type": asset_type,
        "group": group,
        "group_1": group_1,
        "group_2": group_2,
        "classified": bool(group)
    }


# ============================================================
# MEDIDORES
# ============================================================

def get_meters_by_code(token, code):
    """
    Obtiene los medidores asociados a un equipo.

    Retorna siempre una lista.

    Si Fracttal responde sin datos:
        []
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
    3. active debe ser True.
    4. No puede contener "NO UTILIZAR".
    5. Debe existir exactamente un horómetro válido.
    6. El serial del único horómetro debe coincidir
       con el serial del equipo.

    La única excepción vigente permite el meter MH07/1028944 sin serial,
    siempre que la identidad del equipo ya haya sido validada.
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

        if meter.get("active") is not True:
            continue

        if "NO UTILIZAR" in description:
            continue

        if units != "HRS":
            continue

        if is_counter is not True:
            continue

        valid_meters.append(meter)

    if len(valid_meters) == 0:
        raise ValueError(
            f"NO_VALID_METER: el activo {code} no tiene "
            "horómetros válidos."
        )

    if len(valid_meters) > 1:
        raise ValueError(
            f"NO_VALID_METER: el activo {code} tiene "
            f"{len(valid_meters)} horómetros válidos; "
            "no se seleccionará ninguno automáticamente."
        )

    meter = valid_meters[0]
    meter_serial = str(
        meter.get("serial", "")
    ).strip()

    if not meter_serial:
        if (
            str(code).strip().upper(),
            str(meter.get("id")).strip()
        ) in _MISSING_METER_SERIAL_ALLOWLIST:
            return meter

        raise ValueError(
            f"METER_SERIAL_MISSING: el horómetro del activo {code} "
            "no tiene serial."
        )

    if meter_serial.upper() != equipment_serial:
        raise ValueError(
            f"METER_SERIAL_MISMATCH: el horómetro del activo {code} "
            f"tiene serial {meter_serial}, esperado {equipment_serial}."
        )

    return meter


# ============================================================
# LECTURA ACTUAL
# ============================================================

def get_current_hourmeter(token, equipment):
    """
    Obtiene el horómetro válido y su última lectura operacional.

    ``counter_value`` representa el acumulado del contador en Fracttal.
    Para este flujo, el valor comparable y actualizable es
    ``last_data.value``.
    """

    meter = get_valid_hourmeter(
        token,
        equipment
    )

    if meter is None:
        return None

    last_data = meter.get("last_data") or {}
    current_value = last_data.get("value")
    last_reading_datetime = last_data.get("date")

    if current_value is None:
        raise ValueError(
            "FRACTTAL_READING_MISSING: el horómetro no tiene "
            "last_data.value."
        )

    try:
        float(current_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "FRACTTAL_READING_INVALID: last_data.value no es numérico."
        ) from error

    if not isinstance(last_reading_datetime, str):
        raise ValueError(
            "FRACTTAL_READING_DATE_MISSING: el horómetro no tiene "
            "last_data.date."
        )

    try:
        last_reading_datetime = datetime.fromisoformat(
            last_reading_datetime.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(
            "FRACTTAL_READING_DATE_INVALID: last_data.date no es válido."
        ) from error

    if (
        last_reading_datetime.tzinfo is None
        or last_reading_datetime.utcoffset() is None
    ):
        raise ValueError(
            "FRACTTAL_READING_DATE_INVALID: last_data.date no tiene zona."
        )

    return {
        "meter": meter,
        "value": current_value,
        "last_reading_datetime": last_reading_datetime
    }


# ============================================================
# VALIDACIÓN DEL NUEVO HORÓMETRO
# ============================================================

def normalize_comparison_value(value):
    """Normaliza a 2 decimales; None si no es numérico finito."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return round(number, 2)


def validate_hourmeter_update(current_value, new_value):
    """
    Determina qué acción corresponde realizar.

    Reglas:

        current = None → UPDATE

        new == current → SKIP_EQUAL

        new > current → UPDATE

        new < current → REVIEW_INCONSISTENCY
    """

    if current_value is None:
        return "UPDATE"

    current_value = normalize_comparison_value(current_value)
    new_value = normalize_comparison_value(new_value)

    if current_value is None or new_value is None:
        return "REVIEW_INCONSISTENCY"

    if new_value == current_value:
        return "SKIP_EQUAL"

    if new_value > current_value:
        return "UPDATE"

    if new_value < current_value:
        return "REVIEW_INCONSISTENCY"

    return "REVIEW_INCONSISTENCY"


def validate_source_timestamps(
    reading_datetime,
    retrieved_at,
    now=None
):
    """
    Valida timestamps de medición y recuperación.

    Retorna None si son válidos o un código de revisión.
    """

    if not isinstance(reading_datetime, datetime):
        return "REVIEW_SOURCE_DATE"

    if not isinstance(retrieved_at, datetime):
        return "REVIEW_SOURCE_DATE"

    if (
        reading_datetime.tzinfo is None
        or reading_datetime.utcoffset() is None
        or retrieved_at.tzinfo is None
        or retrieved_at.utcoffset() is None
    ):
        return "REVIEW_SOURCE_DATE"

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(
            "El timestamp de comparación debe incluir zona horaria."
        )

    reading_datetime = reading_datetime.astimezone(timezone.utc)
    now = now.astimezone(timezone.utc)

    age_hours = (
        now - reading_datetime
    ).total_seconds() / 3600.0

    if age_hours < -(
        MAX_FUTURE_SKEW_MINUTES / 60.0
    ):
        return "REVIEW_SOURCE_DATE"

    return None


def validate_reading_is_newer(
    reading_datetime,
    last_reading_datetime
):
    """Checks that the OEM reading is newer than Fracttal's last reading."""

    if not isinstance(last_reading_datetime, datetime):
        return "REVIEW_SOURCE_DATE"

    if (
        last_reading_datetime.tzinfo is None
        or last_reading_datetime.utcoffset() is None
    ):
        return "REVIEW_SOURCE_DATE"

    if (
        reading_datetime.astimezone(timezone.utc)
        < last_reading_datetime.astimezone(timezone.utc)
    ):
        return "REVIEW_OLD_SOURCE"

    if (
        reading_datetime.astimezone(timezone.utc)
        == last_reading_datetime.astimezone(timezone.utc)
    ):
        return "SKIP_EQUAL"

    return None


# ============================================================
# ACTUALIZAR HORÓMETRO EN FRACTTAL
# ============================================================

def insert_meter_reading(
    token,
    code,
    value,
    serial,
    reading_datetime,
    retrieved_at,
    *,
    write_context=None
):
    """
    Registra una nueva lectura de horómetro en Fracttal.
    """

    if write_context is not _APPLY_WRITE_CONTEXT:
        raise PermissionError(
            "insert_meter_reading() solo puede ser invocada "
            "por apply_meter_reading()."
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    timestamp_status = validate_source_timestamps(
        reading_datetime=reading_datetime,
        retrieved_at=retrieved_at
    )

    if timestamp_status is not None:
        raise ValueError(
            f"No se puede escribir la lectura: {timestamp_status}."
        )

    date = reading_datetime.astimezone(
        timezone.utc
    ).isoformat()

    body = {
        "date": date,
        "value": value,
        "serial": serial,
        "is_historical": False
    }

    try:
        response = requests.put(
            f"{METER_READING_URL}{code}",
            headers=headers,
            json=body,
            timeout=30
        )
    except (
        requests.exceptions.InvalidURL,
        requests.exceptions.MissingSchema,
        requests.exceptions.InvalidSchema
    ) as error:
        raise RetryableWriteError(
            "La solicitud no pudo prepararse antes del envío."
        ) from error

    response_body = response.text[:4000]

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        raise FracttalResponseError(
            status_code=response.status_code,
            body=response_body,
            message=(
                f"Fracttal respondió HTTP {response.status_code}: "
                f"{response_body}"
            )
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise FracttalResponseError(
            status_code=response.status_code,
            body=response_body,
            message=(
                "Fracttal respondió con un body no JSON después del PUT: "
                f"{response_body}"
            )
        ) from error

    return {
        "payload": payload,
        "http_status": response.status_code
    }


def build_idempotency_key(
    source,
    serial,
    meter_id,
    reading_datetime,
    source_value
):
    """Construye una identidad estable para una lectura OEM."""

    if reading_datetime.tzinfo is None or reading_datetime.utcoffset() is None:
        raise ValueError("La lectura OEM debe incluir zona horaria.")

    canonical_datetime = reading_datetime.astimezone(
        timezone.utc
    ).isoformat().replace("+00:00", "Z")

    canonical_value = f"{float(source_value):.2f}"
    canonical = "|".join(
        (
            str(source).strip().upper(),
            str(serial).strip().upper(),
            str(meter_id).strip(),
            canonical_datetime,
            canonical_value
        )
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def apply_meter_reading(
    token,
    code,
    value,
    serial,
    reading_datetime,
    retrieved_at,
    decision,
    dry_run=True,
    source="MyDevelon",
    *,
    equipment,
    machinery_id
):
    """
    Aplica únicamente una decisión explícita de UPDATE.

    Las decisiones de revisión nunca llegan al endpoint de escritura.
    """

    if decision != "UPDATE":
        raise ValueError(
            f"La decisión {decision} no está autorizada para escritura."
        )

    if dry_run:
        return {
            "status": "WOULD_UPDATE",
            "code": code,
            "value": value
        }

    revalidated_equipment = get_equipment_by_serial(
        token,
        serial
    )

    if revalidated_equipment is None:
        raise ValueError(
            "NO_MATCH_SERIAL: no existe un equipo Fracttal "
            f"para el serial {serial}."
        )

    received_equipment_id = equipment.get("id")
    revalidated_equipment_id = revalidated_equipment.get("id")

    received_equipment_code = str(
        equipment.get("code", "")
    ).strip().upper()
    revalidated_equipment_code = str(
        revalidated_equipment.get("code", "")
    ).strip().upper()

    received_equipment_serial = str(
        equipment.get("field_4", "")
    ).strip().upper()
    revalidated_equipment_serial = str(
        revalidated_equipment.get("field_4", "")
    ).strip().upper()

    received_equipment_model = str(
        equipment.get("field_3", "")
    ).strip().upper()
    revalidated_equipment_model = str(
        revalidated_equipment.get("field_3", "")
    ).strip().upper()

    if (
        received_equipment_id != revalidated_equipment_id
        or received_equipment_code != revalidated_equipment_code
        or received_equipment_serial != revalidated_equipment_serial
        or received_equipment_model != revalidated_equipment_model
    ):
        raise ValueError(
            "EQUIPMENT_IDENTITY_MISMATCH: el equipo recibido "
            "no coincide con el equipo revalidado."
        )

    timestamp_status = validate_source_timestamps(
        reading_datetime=reading_datetime,
        retrieved_at=retrieved_at
    )

    if timestamp_status is not None:
        raise ValueError(
            f"No se puede aplicar la lectura: {timestamp_status}."
        )

    if not serial:
        raise ValueError(
            "No se puede aplicar la lectura sin serial de meter."
        )

    equipment_code = str(
        equipment.get("code", "")
    ).strip().upper()

    if not equipment_code or equipment_code != str(code).strip().upper():
        raise ValueError(
            "EQUIPMENT_MISMATCH: el código de equipo no coincide "
            "con el equipo validado."
        )

    equipment_serial = str(
        equipment.get("field_4", "")
    ).strip().upper()

    machinery = get_machinery_by_id(machinery_id)

    if machinery is None:
        raise ValueError(
            "MACHINERY_NOT_FOUND: no existe la maquinaria SQL."
        )

    machinery_serial = str(
        machinery.get("serial", "")
    ).strip().upper()

    if machinery_serial != equipment_serial:
        raise ValueError(
            "MACHINERY_IDENTITY_MISMATCH: el serial SQL no coincide "
            "con el equipo validado."
        )

    telemetry_config = get_telemetry_sync_config(
        machinery_id=machinery_id,
        telemetry_source=str(source).strip().upper()
    )

    if telemetry_config is None:
        raise ValueError(
            "CONFIG_MISSING: no existe configuración de telemetría."
        )

    if not telemetry_config.get("sync_enabled"):
        raise ValueError(
            "SYNC_DISABLED: la telemetría está deshabilitada."
        )

    action_policy = str(
        telemetry_config.get("action_policy") or ""
    ).strip().upper()

    if action_policy != "AUTO":
        raise ValueError(
            "CONFIG_REVIEW: la política no autoriza escritura automática."
        )

    current_result = get_current_hourmeter(
        token,
        equipment
    )

    if current_result is None:
        raise ValueError(
            "NO_VALID_METER: no existe un horómetro inequívoco."
        )

    current_meter = current_result["meter"]
    current_value = current_result["value"]
    current_last_reading_datetime = current_result[
        "last_reading_datetime"
    ]

    current_meter_serial = str(
        current_meter.get("serial", "")
    ).strip().upper()

    missing_meter_serial_allowed = (
        not current_meter_serial
        and (
            str(code).strip().upper(),
            str(current_meter.get("id")).strip()
        ) in _MISSING_METER_SERIAL_ALLOWLIST
        and str(serial).strip().upper() == equipment_serial
    )

    if (
        current_meter_serial != equipment_serial
        and not missing_meter_serial_allowed
    ):
        raise ValueError(
            "METER_SERIAL_MISMATCH: el serial del meter "
            "no coincide con el serial del equipo."
        )

    if (
        str(serial).strip().upper() != current_meter_serial
        and not missing_meter_serial_allowed
    ):
        raise ValueError(
            "METER_SERIAL_MISMATCH: el meter autorizado "
            "no coincide con el meter actual."
        )

    idempotency_key = build_idempotency_key(
        source="MYDEVELON",
        serial=serial,
        meter_id=current_meter.get("id"),
        reading_datetime=reading_datetime,
        source_value=value
    )

    existing_event = get_horometer_update_by_idempotency_key(
        idempotency_key
    )

    if existing_event is not None:
        existing_status = str(
            existing_event.get("write_status")
            or existing_event.get("status")
            or ""
        ).strip().upper()

        if existing_status == "VERIFIED":
            return {
                "status": "ALREADY_PROCESSED",
                "idempotency_key": idempotency_key,
                "event_id": existing_event.get("id")
            }

        if existing_status == "WRITE_AMBIGUOUS":
            raise ValueError(
                "REEXECUTION_BLOCKED: la lectura anterior "
                "quedó en WRITE_AMBIGUOUS."
            )

        if existing_status == "SKIP_EQUAL":
            return {
                "status": "ALREADY_EVALUATED",
                "idempotency_key": idempotency_key,
                "event_id": existing_event.get("id")
            }

        if existing_status == "ERROR_RETRYABLE":
            event_id = existing_event.get("id")
        else:
            raise ValueError(
                "REEXECUTION_BLOCKED: ya existe un intento para "
                f"la lectura {idempotency_key}."
            )
    else:
        event_id = None

    order_status = validate_reading_is_newer(
        reading_datetime,
        current_last_reading_datetime
    )

    if order_status == "SKIP_EQUAL":
        raise NoNewReadingError(
            "SKIP_EQUAL: la lectura MyDevelon no es posterior "
            "a la última lectura de Fracttal."
        )

    if order_status == "REVIEW_OLD_SOURCE":
        raise ValueError(
            "REVIEW_OLD_SOURCE: la lectura MyDevelon es anterior "
            "a la última lectura de Fracttal."
        )

    try:
        current_value = float(current_value)
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            "No se puede aplicar la lectura con valores no numéricos."
        )

    if not math.isfinite(current_value) or not math.isfinite(value):
        raise ValueError(
            "No se puede aplicar la lectura con valores no finitos."
        )

    if normalize_comparison_value(value) == normalize_comparison_value(
        current_value
    ):
        raise ValueError(
            "SKIP_EQUAL: el valor ya coincide con Fracttal."
        )

    if normalize_comparison_value(value) < normalize_comparison_value(
        current_value
    ):
        raise ValueError(
            "REVIEW_INCONSISTENCY: el valor MyDevelon "
            "es menor que Fracttal."
        )

    if value <= current_value:
        raise ValueError(
            "UPDATE no autorizado: el nuevo valor no es mayor "
            "que el valor actual."
        )

    if event_id is None:
        try:
            event_id = create_horometer_write_intent(
                machinery_id=machinery_id,
                meter_id=current_meter.get("id"),
                meter_serial=current_meter_serial,
                old_value=current_value,
                new_value=value,
                source="MyDevelon",
                reading_date=retrieved_at,
                idempotency_key=idempotency_key,
                source_reading_datetime=reading_datetime,
                source_value=value,
                decision=decision,
                message="Intención de escritura registrada antes del PUT."
            )
        except IdempotencyConflictError as error:
            existing_event = get_horometer_update_by_idempotency_key(
                idempotency_key
            )
            if existing_event is None:
                raise ValueError(
                    "REEXECUTION_BLOCKED: conflicto de idempotencia "
                    "sin registro recuperable."
                ) from error
            raise ValueError(
                "REEXECUTION_BLOCKED: la lectura fue reservada "
                "por otra ejecución."
            ) from error

    if not event_id:
        raise PersistenceError(
            "P1.1 no registró la intención: event_id inválido, "
            "PUT bloqueado antes de ejecutarse."
        )

    mark_horometer_write_in_progress(event_id)

    try:
        write_result = insert_meter_reading(
            token=token,
            code=code,
            value=value,
            serial=serial,
            reading_datetime=reading_datetime,
            retrieved_at=retrieved_at,
            write_context=_APPLY_WRITE_CONTEXT
        )

        payload = write_result["payload"]
        meter_data = payload.get("data", {}) if isinstance(payload, dict) else {}
        reading_id = meter_data.get("id_meters_readings")
        is_duplicate = meter_data.get("is_duplicate")

        try:
            verification = get_current_hourmeter(
                token,
                equipment
            )
        except (
            requests.exceptions.RequestException,
            ValueError
        ) as error:
            update_horometer_write_result(
                event_id,
                status="WRITE_AMBIGUOUS",
                write_status="WRITE_AMBIGUOUS",
                http_status=write_result["http_status"],
                fracttal_reading_id=reading_id,
                fracttal_is_duplicate=is_duplicate,
                verification_status="VERIFICATION_ERROR",
                error_code=f"VERIFICATION_{type(error).__name__}",
                message=(
                    "El PUT respondió, pero el GET de verificación "
                    f"falló: {error}"
                )
            )
            raise ValueError(
                "WRITE_AMBIGUOUS: el PUT respondió, pero el GET "
                "de verificación falló."
            ) from error

        if verification is None:
            update_horometer_write_result(
                event_id,
                status="WRITE_AMBIGUOUS",
                write_status="WRITE_AMBIGUOUS",
                http_status=write_result["http_status"],
                fracttal_reading_id=reading_id,
                fracttal_is_duplicate=is_duplicate,
                verification_status="VERIFICATION_FAILED",
                error_code="NO_VERIFICATION_METER",
                message="El PUT respondió, pero no fue posible verificar el meter."
            )
            raise ValueError(
                "WRITE_AMBIGUOUS: no fue posible verificar el meter."
            )

        verification_meter = verification["meter"]
        verification_value = normalize_comparison_value(
            verification["value"]
        )
        expected_value = normalize_comparison_value(value)
        verification_ok = (
            verification_meter.get("id") == current_meter.get("id")
            and str(verification_meter.get("serial", "")).strip().upper()
            == current_meter_serial
            and verification_value is not None
            and expected_value is not None
            and verification_value == expected_value
        )

        if not verification_ok:
            update_horometer_write_result(
                event_id,
                status="WRITE_AMBIGUOUS",
                write_status="WRITE_AMBIGUOUS",
                http_status=write_result["http_status"],
                fracttal_reading_id=reading_id,
                fracttal_is_duplicate=is_duplicate,
                verification_value=verification_value,
                verification_status="VERIFICATION_FAILED",
                error_code="VERIFICATION_FAILED",
                message="El GET posterior no confirmó exactamente la lectura."
            )
            raise ValueError(
                "WRITE_AMBIGUOUS: el GET posterior no confirmó "
                "exactamente la lectura."
            )

        update_horometer_write_result(
            event_id,
            status="VERIFIED",
            write_status="VERIFIED",
            http_status=write_result["http_status"],
            fracttal_reading_id=reading_id,
            fracttal_is_duplicate=is_duplicate,
            verification_value=verification_value,
            verification_status="PASS",
            message="PUT y GET posterior verificados correctamente."
        )

        return {
            "status": "VERIFIED",
            "idempotency_key": idempotency_key,
            "event_id": event_id,
            "http_status": write_result["http_status"],
            "response": payload
        }

    except FracttalResponseError as error:
        status_code = error.status_code or 0
        if status_code in (408, 429):
            result_status = "WRITE_AMBIGUOUS"
        elif 400 <= status_code < 500:
            result_status = "ERROR"
        else:
            result_status = "WRITE_AMBIGUOUS"
        update_horometer_write_result(
            event_id,
            status=result_status,
            write_status=result_status,
            http_status=error.status_code,
            verification_status="NOT_ATTEMPTED",
            error_code=f"HTTP_{error.status_code}",
            message=(
                f"{error}. Body: {error.body}"
            )
        )
        raise ValueError(
            f"{result_status}: respuesta HTTP de Fracttal "
            f"{error.status_code}."
        ) from error
    except RetryableWriteError as error:
        update_horometer_write_result(
            event_id,
            status="ERROR_RETRYABLE",
            write_status="ERROR_RETRYABLE",
            verification_status="NOT_ATTEMPTED",
            error_code=type(error).__name__,
            message=str(error)
        )
        raise ValueError(
            "ERROR_RETRYABLE: la escritura no fue enviada."
        ) from error
    except requests.exceptions.RequestException as error:
        update_horometer_write_result(
            event_id,
            status="WRITE_AMBIGUOUS",
            write_status="WRITE_AMBIGUOUS",
            verification_status="NOT_ATTEMPTED",
            error_code=type(error).__name__,
            message=str(error)
        )
        raise ValueError(
            "WRITE_AMBIGUOUS: el resultado del PUT no pudo determinarse."
        ) from error


# ============================================================
# PROCESAR UN EQUIPO
# ============================================================

def process_equipment(
    token,
    serial,
    new_value,
    dry_run=True,
    reading_datetime=None,
    retrieved_at=None,
    source="MyDevelon"
):
    """
    Procesa una lectura de horómetro.

    Flujo:

        1. Buscar equipo en Fracttal.
        2. Obtener clasificación desde Fracttal.
        3. Crear/actualizar maquinaria en SQL.
        4. Buscar horómetro válido.
        5. Validar timestamps.
        6. Consultar autorización de telemetría.
        7. Comparar valores.
        8. Determinar UPDATE / SKIP_EQUAL /
           REVIEW_INCONSISTENCY.
        9. Registrar resultado en SQL.
        10. Si corresponde y dry_run=False,
           actualizar Fracttal.

    Fuente de clasificación:

        Fracttal → groups_description

    Equivalencias:

        groups_description   → asset_type
        groups_1_description → asset_group_1
        groups_2_description → asset_group_2

    IMPORTANTE:

        equipment_code se conserva intacto.

        manufacturer NO se utiliza para clasificar.

        model NO se utiliza para clasificar.

        dry_run=True
        nunca modifica Fracttal.

        Semántica dry_run (proyecto): dry_run=True = ningún
        PUT/POST/PATCH/DELETE a Fracttal; SQL solo recibe filas
        WOULD_UPDATE/revisión. dry_run=False = flujo P1.1
        completo con PUT.
    """

    serial = str(serial).strip().upper()

    timestamp_status = validate_source_timestamps(
        reading_datetime=reading_datetime,
        retrieved_at=retrieved_at
    )

    if timestamp_status is not None:
        save_horometer_update(
            machinery_id=None,
            meter_id=None,
            meter_serial=serial,
            old_value=None,
            new_value=new_value,
            source=source,
            reading_date=retrieved_at,
            status="REVIEW",
            decision="REVIEW_SOURCE_DATE",
            write_status="BLOCKED",
            idempotency_key=None,
            message=(
                "No se pudo validar la fecha de la lectura."
            )
        )
        return {
            "status": timestamp_status,
            "serial": serial,
            "new_value": new_value
        }

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
            source=source,
            reading_date=retrieved_at,
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

    # ========================================================
    # 3. CLASIFICACIÓN DESDE FRACTTAL
    # ========================================================

    classification = get_asset_type(
        equipment
    )

    asset_type = classification["asset_type"]
    group_1 = classification["group_1"]
    group_2 = classification["group_2"]

    print()
    print("[OK] Equipo encontrado")
    print(f"     Código: {code}")
    print(f"     Tipo Fracttal: {asset_type}")
    print(f"     Grupo 1: {group_1}")
    print(f"     Grupo 2: {group_2}")
    print(f"     Nombre: {name}")
    print(f"     Fabricante: {manufacturer}")
    print(f"     Modelo: {model}")
    print(f"     Serial: {fracttal_serial}")

    if not classification["classified"]:

        print()
        print(
            "[WARNING] El activo no tiene "
            "groups_description en Fracttal."
        )

        print(
            "          Se utilizará: NO CLASIFICADO"
        )

    # ========================================================
    # 4. GUARDAR / ACTUALIZAR MAQUINARIA EN SQL
    # ========================================================

    machinery = upsert_machinery(
        serial=serial,
        equipment_code=code,
        name=name,
        manufacturer=manufacturer,
        model=model,
        asset_type=asset_type,
        asset_group_1=group_1,
        asset_group_2=group_2
    )

    machinery_id = machinery["id"]

    try:
        telemetry_config = get_telemetry_sync_config(
            machinery_id=machinery_id,
            telemetry_source=str(source).strip().upper()
        )

    except ValueError as error:
        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=None,
            meter_serial=serial,
            old_value=None,
            new_value=new_value,
            source=source,
            reading_date=retrieved_at,
            status="REVIEW",
            error_code="CONFIG_MULTIPLE",
            decision="CONFIG_MULTIPLE",
            write_status="BLOCKED",
            message=str(error)
        )
        return {
            "status": "CONFIG_MULTIPLE",
            "serial": serial,
            "code": code,
            "asset_type": asset_type,
            "error": str(error)
        }

    if telemetry_config is None:
        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=None,
            meter_serial=serial,
            old_value=None,
            new_value=new_value,
            source=source,
            reading_date=retrieved_at,
            status="REVIEW",
            error_code="CONFIG_MISSING",
            decision="CONFIG_MISSING",
            write_status="BLOCKED",
            message=(
                "Sin configuración de telemetría "
                f"para el activo {code}."
            )
        )
        return {
            "status": "CONFIG_MISSING",
            "serial": serial,
            "code": code,
            "asset_type": asset_type
        }

    if not telemetry_config.get("sync_enabled"):
        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=None,
            meter_serial=serial,
            old_value=None,
            new_value=new_value,
            source=source,
            reading_date=retrieved_at,
            status="REVIEW",
            error_code="SYNC_DISABLED",
            decision="SYNC_DISABLED",
            write_status="BLOCKED",
            message=(
                "Telemetría deshabilitada "
                f"para el activo {code}."
            )
        )
        return {
            "status": "SYNC_DISABLED",
            "serial": serial,
            "code": code,
            "asset_type": asset_type
        }

    action_policy = str(
        telemetry_config.get("action_policy") or ""
    ).strip().upper()

    if action_policy != "AUTO":
        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=None,
            meter_serial=serial,
            old_value=None,
            new_value=new_value,
            source=source,
            reading_date=retrieved_at,
            status="REVIEW",
            error_code="CONFIG_REVIEW",
            decision="CONFIG_REVIEW",
            write_status="BLOCKED",
            message=(
                "Política no automática "
                f"para el activo {code}."
            )
        )
        return {
            "status": "CONFIG_REVIEW",
            "serial": serial,
            "code": code,
            "asset_type": asset_type
        }

    print()
    print(
        f"[OK] Machinery ID: {machinery_id}"
    )

    print(
        f"[OK] Tipo almacenado en SQL: "
        f"{machinery.get('asset_type')}"
    )

    # ========================================================
    # 5. OBTENER HORÓMETRO
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

        error_text = str(error)
        meter_status = "ERROR"

        if error_text.startswith("METER_SERIAL_MISMATCH"):
            meter_status = "METER_SERIAL_MISMATCH"
        elif error_text.startswith("METER_SERIAL_MISSING"):
            meter_status = "REVIEW"
        elif error_text.startswith(
            (
                "FRACTTAL_READING_MISSING",
                "FRACTTAL_READING_INVALID"
            )
        ):
            meter_status = "REVIEW"
        elif error_text.startswith(
            (
                "METER_SERIAL_DUPLICATE",
                "NO_VALID_METER"
            )
        ):
            meter_status = "NO_VALID_METER"

        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=None,
            meter_serial=None,
            old_value=None,
            new_value=new_value,
            source=source,
            reading_date=retrieved_at,
            status=meter_status,
            message=str(error)
        )

        return {
            "status": meter_status,
            "serial": serial,
            "code": code,
            "asset_type": asset_type,
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
            source=source,
            reading_date=retrieved_at,
            status="METER_NOT_FOUND",
            message=(
                f"No se encontró horómetro válido "
                f"para el activo {code}"
            )
        )

        return {
            "status": "METER_NOT_FOUND",
            "serial": serial,
            "code": code,
            "asset_type": asset_type
        }

    # ========================================================
    # 6. DATOS DEL HORÓMETRO
    # ========================================================

    meter = result["meter"]
    current_value = result["value"]
    last_reading_datetime = result["last_reading_datetime"]

    meter_id = meter.get("id")
    meter_serial = meter.get("serial")
    meter_description = meter.get("description")
    reading_idempotency_key = build_idempotency_key(
        source="MYDEVELON",
        serial=serial,
        meter_id=meter_id,
        reading_datetime=reading_datetime,
        source_value=new_value
    )

    print()
    print("[OK] Horómetro encontrado")
    print(f"     ID: {meter_id}")
    print(f"     Descripción: {meter_description}")
    print(f"     Serial: {meter_serial}")
    print(f"     Valor Fracttal: {current_value}")
    print(
        "     Última lectura Fracttal: "
        f"{last_reading_datetime.isoformat()}"
    )

    source_order_status = validate_reading_is_newer(
        reading_datetime,
        last_reading_datetime
    )

    if source_order_status == "REVIEW_SOURCE_DATE":
        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=meter_id,
            meter_serial=meter_serial,
            old_value=current_value,
            new_value=new_value,
            source=source,
            reading_date=retrieved_at,
            status="REVIEW",
            idempotency_key=reading_idempotency_key,
            source_reading_datetime=reading_datetime,
            source_value=new_value,
            decision="REVIEW_SOURCE_DATE",
            write_status="BLOCKED",
            message=(
                "No se pudo validar la fecha de la última lectura "
                "de Fracttal."
            )
        )
        return {
            "status": "REVIEW",
            "serial": serial,
            "code": code,
            "asset_type": asset_type,
            "old_value": current_value,
            "new_value": new_value
        }

    if source_order_status == "REVIEW_OLD_SOURCE":
        save_horometer_update(
            machinery_id=machinery_id,
            meter_id=meter_id,
            meter_serial=meter_serial,
            old_value=current_value,
            new_value=new_value,
            source=source,
            reading_date=retrieved_at,
            status="REVIEW",
            idempotency_key=reading_idempotency_key,
            source_reading_datetime=reading_datetime,
            source_value=new_value,
            decision="REVIEW_OLD_SOURCE",
            write_status="BLOCKED",
            message=(
                "La lectura MyDevelon es anterior a la última "
                "lectura de Fracttal; jamás equivale a igual."
            )
        )
        return {
            "status": "REVIEW",
            "serial": serial,
            "code": code,
            "asset_type": asset_type,
            "old_value": current_value,
            "new_value": new_value
        }

    if source_order_status == "SKIP_EQUAL":
        norm_new = normalize_comparison_value(new_value)
        norm_current = normalize_comparison_value(current_value)

        if (
            norm_new is not None
            and norm_current is not None
            and norm_new == norm_current
        ):
            save_horometer_update(
                machinery_id=machinery_id,
                meter_id=meter_id,
                meter_serial=meter_serial,
                old_value=current_value,
                new_value=new_value,
                source=source,
                reading_date=retrieved_at,
                status="SKIP_EQUAL",
                idempotency_key=reading_idempotency_key,
                source_reading_datetime=reading_datetime,
                source_value=new_value,
                decision="SKIP_EQUAL",
                write_status="SKIP_EQUAL",
                message=(
                    "La lectura MyDevelon coincide en fecha y valor "
                    "con la última lectura de Fracttal."
                )
            )
            return {
                "status": "SKIP_EQUAL",
                "serial": serial,
                "code": code,
                "asset_type": asset_type,
                "old_value": current_value,
                "new_value": new_value
            }
        # Misma fecha pero valor distinto: continúa a validación de
        # actualización. (new_value no normalizable no llega aquí:
        # la construcción de la key falla antes, en voz alta.)

    # ========================================================
    # 7. VALIDAR ACTUALIZACIÓN
    # ========================================================

    action = validate_hourmeter_update(
        current_value,
        new_value
    )

    print()
    print(f"Valor MyDevelon: {new_value}")
    print(f"Acción: {action}")

    # ========================================================
    # 8. SKIP
    # ========================================================

    if action == "SKIP_EQUAL":

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
            source=source,
            reading_date=retrieved_at,
            status="SKIP_EQUAL",
            idempotency_key=reading_idempotency_key,
            source_reading_datetime=reading_datetime,
            source_value=new_value,
            decision="SKIP_EQUAL",
            write_status="SKIP_EQUAL",
            message=(
                "El valor recibido es igual "
                "al valor actual de Fracttal."
            )
        )

        return {
            "status": "SKIP_EQUAL",
            "serial": serial,
            "code": code,
            "asset_type": asset_type,
            "old_value": current_value,
            "new_value": new_value
        }

    # ========================================================
    # 9. REVIEW INCONSISTENCY
    # ========================================================

    if action == "REVIEW_INCONSISTENCY":

        print()
        print(
            "[REVIEW_INCONSISTENCY] MyDevelon tiene menos horas "
            "que el valor registrado actualmente."
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
            source=source,
            reading_date=retrieved_at,
            status="REVIEW_INCONSISTENCY",
            idempotency_key=reading_idempotency_key,
            source_reading_datetime=reading_datetime,
            source_value=new_value,
            decision="REVIEW_INCONSISTENCY",
            write_status="BLOCKED",
            message=(
                "El valor MyDevelon es menor que el valor "
                "actual de Fracttal."
            )
        )

        return {
            "status": "REVIEW_INCONSISTENCY",
            "serial": serial,
            "code": code,
            "asset_type": asset_type,
            "old_value": current_value,
            "new_value": new_value
        }

    # ========================================================
    # 10. UPDATE
    # ========================================================

    print()
    print(
        f"[UPDATE] {current_value} -> {new_value}"
    )

    # ========================================================
    # 11. DRY RUN
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
            source=source,
            reading_date=retrieved_at,
            status="WOULD_UPDATE",
            idempotency_key=reading_idempotency_key,
            source_reading_datetime=reading_datetime,
            source_value=new_value,
            decision="WOULD_UPDATE",
            write_status="WOULD_UPDATE",
            message=(
                "Simulación DRY RUN. "
                "Fracttal no fue modificado."
            )
        )

        return {
            "status": "WOULD_UPDATE",
            "serial": serial,
            "code": code,
            "asset_type": asset_type,
            "old_value": current_value,
            "new_value": new_value,
            "idempotency_key": reading_idempotency_key
        }

    # ========================================================
    # 12. ESCRIBIR EN FRACTTAL
    # ========================================================

    try:

        response = apply_meter_reading(
            token=token,
            code=code,
            value=new_value,
            serial=serial,
            reading_datetime=reading_datetime,
            retrieved_at=retrieved_at,
            decision=action,
            dry_run=dry_run,
            source=source,
            equipment=equipment,
            machinery_id=machinery_id
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

        existing_event = get_horometer_update_by_idempotency_key(
            reading_idempotency_key
        )
        existing_write_status = (
            str(
                (existing_event or {}).get("write_status")
                or ""
            ).strip().upper()
        )

        if existing_event is None:
            save_horometer_update(
                machinery_id=machinery_id,
                meter_id=meter_id,
                meter_serial=meter_serial,
                old_value=current_value,
                new_value=new_value,
                source=source,
                reading_date=retrieved_at,
                status="ERROR",
                idempotency_key=reading_idempotency_key,
                source_reading_datetime=reading_datetime,
                source_value=new_value,
                decision="ERROR",
                write_status="ERROR",
                message=str(error)
            )

        return {
            "status": existing_write_status or "ERROR",
            "serial": serial,
            "code": code,
            "asset_type": asset_type,
            "old_value": current_value,
            "new_value": new_value,
            "error": str(error)
        }

    # ========================================================
    # 13. REGISTRAR ACTUALIZACIÓN EXITOSA
    # ========================================================

    print()
    print(
        "[OK] Horómetro actualizado correctamente."
    )

    return {
        "status": response.get("status") or "VERIFIED",
        "serial": serial,
        "code": code,
        "asset_type": asset_type,
        "old_value": current_value,
        "new_value": new_value,
        "event_id": response.get("event_id"),
        "idempotency_key": response.get("idempotency_key"),
        "response": response
    }