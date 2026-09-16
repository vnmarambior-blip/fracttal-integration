"""Ejecutor programable de la sincronización MyDevelon -> Fracttal.

Este archivo es el punto de entrada para la tarea diaria. A diferencia de los
archivos ``test_*``, puede aplicar actualizaciones cuando SYNC_DRY_RUN=false.
"""

import os
from collections import Counter
from datetime import datetime, timezone

from api import get_access_token as get_fracttal_access_token
from api import process_equipment
from mydevelon import get_access_token as get_mydevelon_access_token
from mydevelon import get_fleet_xml, parse_fleet_xml


TARGET_OEM = "DEVELON"


def env_flag(name, default=False):
    """Convierte una variable de entorno booleana de manera predecible."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_reading_datetime(value):
    """Convierte el timestamp entregado por el OEM a un datetime con zona."""
    if not value:
        return None

    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed
    except ValueError:
        return None


def main():
    # La opción segura es no escribir hasta que el responsable lo habilite
    # explícitamente como secreto de GitHub.
    dry_run = env_flag("SYNC_DRY_RUN", default=True)
    retrieved_at = datetime.now(timezone.utc)

    print("=" * 70)
    print("SINCRONIZACIÓN DIARIA: MYDEVELON -> FRACTTAL")
    print(f"Modo: {'SIMULACIÓN' if dry_run else 'PRODUCCIÓN'}")
    print("=" * 70)

    mydevelon_token = get_mydevelon_access_token()
    fleet = parse_fleet_xml(get_fleet_xml(mydevelon_token))
    develon_fleet = [
        item for item in fleet
        if str(item.get("oem_name", "")).strip().upper() == TARGET_OEM
    ]

    print(f"Equipos {TARGET_OEM} recibidos: {len(develon_fleet)}")
    fracttal_token = get_fracttal_access_token()
    results = []

    for item in develon_fleet:
        serial = str(item.get("pin") or "").strip().upper()
        value = item.get("operating_hours")
        reading_datetime = parse_reading_datetime(
            item.get("operating_hours_datetime")
        )

        if not serial:
            result = {"status": "ERROR_NO_PIN", "serial": ""}
        elif value is None:
            result = {"status": "ERROR_SOURCE_HOURS", "serial": serial}
        else:
            try:
                result = process_equipment(
                    token=fracttal_token,
                    serial=serial,
                    new_value=value,
                    dry_run=dry_run,
                    reading_datetime=reading_datetime,
                    retrieved_at=retrieved_at,
                )
            except Exception as error:  # Continúa para que un equipo no bloquee al resto.
                print(f"[ERROR] {serial}: {error}")
                result = {
                    "status": "ERROR_UNEXPECTED",
                    "serial": serial,
                    "error": str(error),
                }

        results.append(result)
        print(f"[RESULTADO] {serial or 'SIN_PIN'}: {result['status']}")

    statuses = Counter(result.get("status", "UNKNOWN") for result in results)
    print("\nRESUMEN")
    for status, count in sorted(statuses.items()):
        print(f"{status}: {count}")

    failures = {"ERROR_UNEXPECTED"}
    if any(result.get("status") in failures for result in results):
        raise RuntimeError("La sincronización terminó con errores inesperados.")


if __name__ == "__main__":
    main()
