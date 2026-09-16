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

    for key, value in response.headers.items():
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

    for key, value in response.headers.items():
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

    root = ET.fromstring(xml_text)
    snapshot_time = _parse_datetime(
        root.attrib.get("snapshotTime")
    )
    retrieved_at = datetime.now(timezone.utc)
    fleet = []

    for equipment in root.findall(
        "aemp:Equipment",
        AEMP_NAMESPACE
    ):
        header = equipment.find(
            "aemp:EquipmentHeader",
            AEMP_NAMESPACE
        )
        if header is None:
            continue

        operating_hours_node = equipment.find(
            "aemp:CumulativeOperatingHours",
            AEMP_NAMESPACE
        )
        operating_hours = None
        operating_hours_datetime = None

        if operating_hours_node is not None:
            raw_hours = _get_text(
                operating_hours_node,
                "aemp:Hour"
            )
            if raw_hours is not None:
                operating_hours = float(raw_hours)

            operating_hours_datetime = _parse_datetime(
                operating_hours_node.attrib.get("datetime")
            )

        fleet.append(
            {
                "oem_name": _get_text(header, "aemp:OEMName"),
                "model": _get_text(header, "aemp:Model"),
                "equipment_id": _get_text(
                    header,
                    "aemp:EquipmentID"
                ),
                "serial_number": _get_text(
                    header,
                    "aemp:SerialNumber"
                ),
                "pin": _get_text(header, "aemp:PIN"),
                "operating_hours": operating_hours,
                "operating_hours_datetime":
                    operating_hours_datetime,
                "snapshot_time": snapshot_time,
                "retrieved_at": retrieved_at,
            }
        )

    return fleet