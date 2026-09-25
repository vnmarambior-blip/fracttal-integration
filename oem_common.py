# -*- coding: utf-8 -*-
"""Helpers OEM genéricos compartidos (MyDevelon, Komtrax, etc.).

Contiene únicamente lógica independiente del OEM:
- parseo AEMP / ISO 15143-3 namespace-agnostic,
- cache de tokens en archivo con TTL,
- guardián de cuota por archivo de estado.

Sin credenciales, sin red, sin SQL.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import os


def env_flag(name, default=False):
    """Convierte una variable de entorno booleana de manera predecible."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class FleetEmptyError(ValueError):
    """La flota no contiene ningún equipo auditable."""


def _read_timestamp(path):
    """Lee un ISO-8601 con zona desde un archivo de estado."""

    with open(path, encoding="utf-8") as handle:
        text = handle.read().strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    return datetime.fromisoformat(text)


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
