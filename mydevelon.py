import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

CLIENT_ID = os.getenv("MYDEVELON_CLIENT_ID")
CLIENT_SECRET = os.getenv("MYDEVELON_CLIENT_SECRET")

BASE_URL = (
    "https://extapi.mydevelon.com/"
    "api/rest/aemp/2.0"
)

TOKEN_URL = (
    f"{BASE_URL}/token"
)

# Endpoint Fleet paginado.
# Ejemplo:
# /Fleet/1
# /Fleet/2
# /Fleet/3
FLEET_URL = (
    f"{BASE_URL}/Fleet/1"
)

AEMP_NAMESPACE = {
    "aemp": "http://standards.iso.org/iso/15143/-3"
}


# ============================================================
# AUTENTICACIÓN
# ============================================================

def get_access_token():
    """
    Obtiene un token de acceso desde MyDevelon.

    El token tiene una duración limitada y debe solicitarse
    nuevamente cuando corresponda.
    """

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "Faltan MYDEVELON_CLIENT_ID o "
            "MYDEVELON_CLIENT_SECRET en .env"
        )

    response = requests.post(
        TOKEN_URL,
        auth=HTTPBasicAuth(
            CLIENT_ID,
            CLIENT_SECRET
        ),
        timeout=30
    )

    response.raise_for_status()

    token = response.text.strip()

    if not token:
        raise RuntimeError(
            "MyDevelon devolvió una respuesta vacía "
            "al solicitar el token."
        )

    if token.startswith("{"):
        raise RuntimeError(
            "MyDevelon devolvió un error en lugar de token: "
            f"{token[:120]}"
        )

    return token


# ============================================================
# FLEET SNAPSHOT
# ============================================================

def get_fleet_xml(token):
    """
    Obtiene el Fleet Snapshot de MyDevelon.

    Endpoint:
        GET /Fleet/1

    Retorna:
        XML como string.
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/xml"
    }

    response = requests.get(
        FLEET_URL,
        headers=headers,
        timeout=30
    )

    print()
    print("=" * 70)
    print("MYDEVELON FLEET RESPONSE")
    print("=" * 70)

    print("HTTP:", response.status_code)
    print(
        "Content-Type:",
        response.headers.get("Content-Type")
    )

    print()
    print("Headers:")

    for key, value in _safe_headers(response.headers).items():
        print(f"{key}: {value}")

    print()
    print("Respuesta:")
    print("-" * 70)
    print(response.text)
    print("-" * 70)

    response.raise_for_status()

    return response.text


# ============================================================
# SINGLE EQUIPMENT SNAPSHOT
# ============================================================

def get_equipment_snapshot_xml(
    token,
    make_code,
    model,
    serial_number,
):
    """
    Obtiene el snapshot de un equipo específico
    desde MyDevelon.

    IMPORTANTE:
    Este endpoint NO utiliza /Fleet/1.

    Endpoint:
        GET /Fleet/Equipment/MakeModelSerial/
            {makeCode}/{model}/{serialNumber}

    Ejemplo:
        /Fleet/Equipment/MakeModelSerial/
        DEVELON/DX225LCA/CEBDX-001085

    No intenta modificar ni transformar el XML.

    Si MyDevelon devuelve un error HTTP, se informa
    claramente para facilitar diagnóstico.
    """

    # --------------------------------------------------------
    # IMPORTANTE:
    # No utilizar FLEET_URL aquí porque FLEET_URL contiene /1.
    # --------------------------------------------------------

    url = (
        f"{BASE_URL}/Fleet/Equipment/MakeModelSerial/"
        f"{quote(str(make_code), safe='')}/"
        f"{quote(str(model), safe='')}/"
        f"{quote(str(serial_number), safe='')}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/xml",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=60,
    )

    print()
    print("=" * 70)
    print("MYDEVELON SINGLE EQUIPMENT RESPONSE")
    print("=" * 70)

    print(f"URL: {url}")
    print(f"HTTP: {response.status_code}")
    print(
        f"Content-Type: "
        f"{response.headers.get('Content-Type')}"
    )

    print()
    print("Response headers:")
    print("-" * 70)

    for key, value in _safe_headers(response.headers).items():
        print(f"{key}: {value}")

    print()
    print("Respuesta:")
    print("-" * 70)
    print(response.text)
    print("-" * 70)

    if response.status_code != 200:
        raise RuntimeError(
            f"MyDevelon respondió HTTP "
            f"{response.status_code}. "
            f"El error ocurrió en la API de MyDevelon, "
            f"antes de procesar SQL Server o Fracttal."
        )

    return response.text


# ============================================================
# UTILIDADES XML
# ============================================================

def _safe_headers(headers):
    """Redacta valores sensibles; conserva el resto para diagnóstico."""

    sensitive = ("authorization", "cookie", "set-cookie", "token",
                 "api-key", "secret", "credential")

    safe = {}
    for key, value in dict(headers).items():
        if any(part in str(key).lower() for part in sensitive):
            safe[key] = "[REDACTED]"
        else:
            safe[key] = value

    return safe


def _get_text(element, xpath):
    """
    Obtiene el texto de un elemento XML.

    Si el elemento no existe o está vacío:
        retorna None.
    """

    node = element.find(
        xpath,
        AEMP_NAMESPACE
    )

    if node is None:
        return None

    if node.text is None:
        return None

    value = node.text.strip()

    if value == "":
        return None

    return value


def load_fleet_xml_from_file(path):
    """Lee un snapshot de flota guardado (modo fixture, cero red)."""

    with open(path, encoding="utf-8") as handle:
        return handle.read()


def save_fleet_xml_snapshot(xml_text, path):
    """Guarda un snapshot de flota para reusarlo como fixture."""

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(xml_text)

    return path


def _read_timestamp(path):
    """Lee un ISO-8601 con zona desde un archivo de estado."""

    with open(path, encoding="utf-8") as handle:
        text = handle.read().strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    return datetime.fromisoformat(text)


class QuotaExceededError(RuntimeError):
    """El último fetch real fue hace menos del intervalo mínimo."""


class FleetEmptyError(ValueError):
    """La flota no contiene ningún equipo auditable."""


class FleetEmptyError(ValueError):
    """La flota no contiene ningún equipo auditable."""


def resolve_fleet_xml_text(
    mode,
    fleet_xml_path,
    state_path,
    fetcher,
    record_path=None,
    min_interval_seconds=900,
    now=None,
):
    """Obtiene el XML de flota según el modo (file/live) con cuota."""

    if mode != "live":
        return load_fleet_xml_from_file(fleet_xml_path)

    if not is_fetch_allowed(
        state_path,
        min_interval_seconds=min_interval_seconds,
        now=now,
    ):
        raise QuotaExceededError(
            "Último fetch hace menos de "
            f"{min_interval_seconds} segundos; "
            "usa modo file o espera."
        )

    xml_text = fetcher()

    if not xml_text or not xml_text.strip():
        raise FleetEmptyError(
            "Fleet live vacía; no se registra fetch "
            "para no consumir cuota en vano."
        )

    record_fetch(state_path, now=now)

    if record_path is not None:
        save_fleet_xml_snapshot(xml_text, record_path)

    return xml_text


def is_fetch_allowed(state_path, min_interval_seconds=900, now=None):
    """Indica si pasó el intervalo mínimo desde el último fetch real."""

    if now is None:
        now = datetime.now(timezone.utc)

    try:
        last = _read_timestamp(state_path)
    except (OSError, ValueError):
        return True

    return (now - last).total_seconds() >= min_interval_seconds


def record_fetch(state_path, now=None):
    """Registra el momento de un fetch real contra la API."""

    if now is None:
        now = datetime.now(timezone.utc)

    with open(state_path, "w", encoding="utf-8") as handle:
        handle.write(now.isoformat())


def get_cached_token(cache_path, ttl_seconds, fetcher, now=None):
    """Reutiliza el token guardado si sigue vigente; si no, lo renueva."""

    if now is None:
        now = datetime.now(timezone.utc)

    try:
        with open(cache_path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()

        token = lines[0].strip()
        saved_at = None

        if len(lines) >= 2:
            saved_at = datetime.fromisoformat(
                lines[1].strip().replace("Z", "+00:00")
            )

        if token and saved_at is not None:
            if (now - saved_at).total_seconds() < ttl_seconds:
                return token
    except (OSError, ValueError, IndexError):
        pass

    token = fetcher()

    with open(cache_path, "w", encoding="utf-8") as handle:
        handle.write(f"{token}\n{now.isoformat()}\n")

    return token


def _get_attribute(element, xpath, attribute):
    """
    Obtiene un atributo de un elemento XML.

    Si no existe:
        retorna None.
    """

    node = element.find(
        xpath,
        AEMP_NAMESPACE
    )

    if node is None:
        return None

    return node.attrib.get(attribute)


def _parse_datetime(value):
    """Convierte un timestamp ISO-8601 con zona horaria."""

    if not value:
        return None

    text = str(value).strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None

    return parsed


def parse_fleet_xml(xml_text):
    """
    Normaliza un Fleet Snapshot AEMP recibido desde /Fleet/1.

    La hora de lectura se obtiene de CumulativeOperatingHours/@datetime;
    snapshotTime solo identifica el snapshot completo.
    """

    if not xml_text or not xml_text.strip():
        raise FleetEmptyError(
            "Snapshot vacío: no hay flota que auditar."
        )

    root = ET.fromstring(xml_text)
    snapshot_time = _parse_datetime(
        root.attrib.get("snapshotTime")
    )
    retrieved_at = datetime.now(timezone.utc)
    fleet = []

    # Buscar todos los Equipment hijos por nombre local (namespace-agnostic).
    # Compatible con MyDevelon (http://standards.iso.org/iso/15143/-3)
    # y Komtrax (http://www.jcmanet.or.jp/english2017/ISO/15143/-3/20190501).
    if root.tag.split("}")[-1] == "Fleet":
        found = [
            child for child in root
            if child.tag.split("}")[-1] == "Equipment"
        ]
    else:
        found = []

    if not found:
        raise FleetEmptyError(
            "Snapshot sin elementos Equipment: flota vacía "
            "o namespace inesperado."
        )

    for equipment in found:
        try:
            parsed = _parse_equipment_element(
                equipment,
                snapshot_time,
                retrieved_at,
            )
        except Exception as error:
            parsed = _error_item(
                equipment,
                snapshot_time,
                retrieved_at,
                error,
            )
        if parsed is None:
            parsed = _error_item(
                equipment,
                snapshot_time,
                retrieved_at,
                ValueError("sin EquipmentHeader"),
            )
        fleet.append(parsed)

    return fleet


def _error_item(equipment, snapshot_time, retrieved_at, error):
    """Conserva evidencia del equipo que falló sin abortar la flota.

    Usa búsqueda por nombre local para ser compatible con cualquier
    namespace ISO 15143-3 (MyDevelon, Komtrax, etc.).
    """

    header = _find_element_local(equipment, "EquipmentHeader")
    scope = header if header is not None else equipment

    return {
        "oem_name": _get_text_local(scope, "OEMName"),
        "model": _get_text_local(scope, "Model"),
        "equipment_id": _get_text_local(scope, "EquipmentID"),
        "serial_number": _get_text_local(scope, "SerialNumber"),
        "pin": _get_text_local(scope, "PIN"),
        "operating_hours": None,
        "operating_hours_datetime": None,
        "snapshot_time": snapshot_time,
        "retrieved_at": retrieved_at,
        "_parse_error": str(error),
    }

def _get_text_local(element, local_name, namespace=None):
    """Extrae texto de un elemento buscando por nombre local (ignora namespace).

    Busca un hijo cuyo nombre local coincida con `local_name`.
    Si se provee `namespace`, usa match de namespace completo; si no,
    hace match por nombre local sin importar el namespace.
    """
    if namespace is not None:
        found = element.find(local_name, namespace)
    else:
        # Buscar por nombre local: probar ambos mods
        # 1) con namespace completo
        found = element.find(local_name, namespace) if namespace else None
        # 2) sin namespace (solo local name)
        if found is None:
            for child in element:
                if child.tag.split("}")[-1] == local_name:
                    found = child
                    break
    if found is None:
        return None
    text = found.text
    if text is None:
        return None
    return text.strip()


def _find_element_local(element, local_name, namespace=None):
    """Encuentra un elemento hijo por nombre local, ignorando namespace."""
    if namespace is not None:
        return element.find(local_name, namespace)
    # Buscar por nombre local
    for child in element:
        if child.tag.split("}")[-1] == local_name:
            return child
    return None


def _parse_equipment_element(equipment, snapshot_time, retrieved_at):
    """Extrae un elemento aemp:Equipment a dict (lógica única compartida).

    Versión tolerante a namespace: busca sub-elementos por nombre local
    en lugar de URI de namespace fijo. Compatible con MyDevelon y Komtrax.
    """

    header = _find_element_local(equipment, "EquipmentHeader")
    if header is None:
        return None

    operating_hours_node = _find_element_local(
        equipment,
        "CumulativeOperatingHours"
    )
    operating_hours = None
    operating_hours_datetime = None

    if operating_hours_node is not None:
        raw_hours = _get_text_local(
            operating_hours_node,
            "Hour"
        )
        if raw_hours is not None:
            operating_hours = float(raw_hours)

        operating_hours_datetime = _parse_datetime(
            operating_hours_node.attrib.get("datetime")
        )

    return {
        "oem_name": _get_text_local(header, "OEMName"),
        "model": _get_text_local(header, "Model"),
        "equipment_id": _get_text_local(
            header,
            "EquipmentID"
        ),
        "serial_number": _get_text_local(
            header,
            "SerialNumber"
        ),
        "pin": _get_text_local(header, "PIN"),
        "operating_hours": operating_hours,
        "operating_hours_datetime":
            operating_hours_datetime,
        "snapshot_time": snapshot_time,
        "retrieved_at": retrieved_at,
    }


def _find_equipment_root(root):
    """Busca el elemento Equipment como hijo directo, independientemente del namespace.

    Returns the first Equipment element found, or None.
    Usa local-name para ser compatible tanto con MyDevelon como con Komtrax.
    """
    # Si el raíz mismo es Equipment (con cualquier namespace)
    if root.tag.split("}")[-1] == "Equipment":
        return root

    # Buscar por nombre local entre hijos
    for child in root:
        if child.tag.split("}")[-1] == "Equipment":
            return child

    return None


def parse_equipment_snapshot_xml(xml_text):
    """Parsea un snapshot individual a dict (None si no hay equipo).

    Acepta raíz Equipment directa o documento con un aemp:Equipment.
    Incluye "oem" además de "oem_name" por compatibilidad con los
    tests de snapshot existentes.
    Admite cualquier namespace ISO 15143-3 (MyDevelon, Komtrax, etc.).
    """

    root = ET.fromstring(xml_text)
    snapshot_time = _parse_datetime(
        root.attrib.get("snapshotTime")
    )
    retrieved_at = datetime.now(timezone.utc)

    equipment = _find_equipment_root(root)

    if equipment is None:
        return None

    parsed = _parse_equipment_element(
        equipment,
        snapshot_time,
        retrieved_at,
    )

    if parsed is None:
        return None

    parsed["oem"] = parsed["oem_name"]

    return parsed