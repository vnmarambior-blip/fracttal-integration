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


from oem_common import (
    FleetEmptyError,
    _find_element_local,
    _find_equipment_root,
    _get_text_local,
    _parse_datetime,
    _parse_equipment_element,
    _error_item,
    _read_timestamp,
    get_cached_token,
    is_fetch_allowed,
    parse_fleet_xml,
    record_fetch,
)


class QuotaExceededError(RuntimeError):
    """El último fetch real fue hace menos del intervalo mínimo."""


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