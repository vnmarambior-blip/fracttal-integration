"""Ejecutor programable de la sincronización MyDevelon -> Fracttal.

Este archivo es el punto de entrada para la tarea diaria. A diferencia de los
archivos ``test_*``, puede aplicar actualizaciones cuando SYNC_DRY_RUN=false.
"""

import argparse
import os
import sys
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timezone

from api import get_access_token as get_fracttal_access_token
from api import process_equipment
from database import save_horometer_update
from mydevelon import QuotaExceededError
from mydevelon import get_access_token as get_mydevelon_access_token
from mydevelon import get_cached_token, get_fleet_xml, parse_fleet_xml
from mydevelon import resolve_fleet_xml_text


TARGET_OEM = "DEVELON"

DEFAULT_FIXTURE = "mydevelon_fleet_minutes.xml"
DEFAULT_STATE_FILE = ".mydevelon_last_fetch.txt"
DEFAULT_TOKEN_CACHE = ".mydevelon_token.txt"
DEFAULT_MIN_INTERVAL_SECONDS = 900
DEFAULT_TOKEN_TTL_SECONDS = 1800


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


def parse_args(argv=None):
    """Argumentos de fuente MyDevelon (file por defecto, cero red)."""

    parser = argparse.ArgumentParser(
        description="Sincronización MyDevelon -> Fracttal."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Consulta la API real (respeta cuota mínima de 15 min).",
    )
    parser.add_argument(
        "--fleet-xml",
        default=os.getenv("MYDEVELON_FIXTURE", DEFAULT_FIXTURE),
        help="Fixture XML en modo file.",
    )
    parser.add_argument(
        "--record",
        default=None,
        help="Guarda el XML live como fixture en esta ruta.",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Guarda el reporte detallado en esta ruta.",
    )
    parser.add_argument(
        "--min-interval-seconds",
        type=int,
        default=int(
            os.getenv(
                "MYDEVELON_MIN_INTERVAL_SECONDS",
                str(DEFAULT_MIN_INTERVAL_SECONDS),
            )
        ),
        help="Intervalo mínimo entre fetch reales.",
    )

    return parser.parse_args(argv)


class _Tee:
    """Duplica stdout a consola y archivo de reporte."""

    def __init__(self, console, handle):
        self.console = console
        self.handle = handle

    def write(self, text):
        self.console.write(text)
        self.handle.write(text)

    def flush(self):
        self.console.flush()
        self.handle.flush()


def main(argv=None):
    # La opción segura es no escribir hasta que el responsable lo habilite
    # explícitamente como secreto de GitHub.
    dry_run = env_flag("SYNC_DRY_RUN", default=True)
    args = parse_args(argv)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            with redirect_stdout(_Tee(sys.stdout, handle)):
                return _main(args, dry_run)
    return _main(args, dry_run)


def _main(args, dry_run):
    mode = "live" if args.live else os.getenv("MYDEVELON_SOURCE", "file")
    retrieved_at = datetime.now(timezone.utc)

    print("=" * 70)
    print("SINCRONIZACIÓN DIARIA: MYDEVELON -> FRACTTAL")
    print(f"Modo: {'SIMULACIÓN' if dry_run else 'PRODUCCIÓN'}")
    print(f"Fuente MyDevelon: {mode}")
    print("=" * 70)

    token_ttl = int(
        os.getenv(
            "MYDEVELON_TOKEN_TTL_SECONDS",
            str(DEFAULT_TOKEN_TTL_SECONDS),
        )
    )

    def fetch_fleet(token):
        return get_fleet_xml(token)

    if mode == "live":
        mydevelon_token = get_cached_token(
            DEFAULT_TOKEN_CACHE,
            token_ttl,
            get_mydevelon_access_token,
        )

        try:
            fleet_xml = resolve_fleet_xml_text(
                mode="live",
                fleet_xml_path=args.fleet_xml,
                state_path=os.getenv(
                    "MYDEVELON_STATE_FILE", DEFAULT_STATE_FILE
                ),
                fetcher=lambda: fetch_fleet(mydevelon_token),
                record_path=args.record,
                min_interval_seconds=args.min_interval_seconds,
            )
        except QuotaExceededError as error:
            print(f"[CUOTA] {error}")
            raise RuntimeError(
                "Fetch MyDevelon bloqueado por cuota mínima."
            ) from error
    else:
        fleet_xml = resolve_fleet_xml_text(
            mode="file",
            fleet_xml_path=args.fleet_xml,
            state_path=os.getenv(
                "MYDEVELON_STATE_FILE", DEFAULT_STATE_FILE
            ),
            fetcher=lambda: fetch_fleet(""),
        )

    fleet = parse_fleet_xml(fleet_xml)
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
            save_horometer_update(
                machinery_id=None,
                meter_id=None,
                meter_serial="",
                old_value=None,
                new_value=value,
                source="MyDevelon",
                reading_date=retrieved_at,
                status="ERROR_NO_PIN",
                error_code="ERROR_NO_PIN",
                decision="ERROR_NO_PIN",
                write_status="ERROR",
                idempotency_key=None,
                message="Equipo sin PIN; no procesado."
            )
            result = {"status": "ERROR_NO_PIN", "serial": ""}
        elif value is None:
            save_horometer_update(
                machinery_id=None,
                meter_id=None,
                meter_serial=serial,
                old_value=None,
                new_value=None,
                source="MyDevelon",
                reading_date=retrieved_at,
                status="ERROR_SOURCE_HOURS",
                error_code="ERROR_SOURCE_HOURS",
                decision="ERROR_SOURCE_HOURS",
                write_status="ERROR",
                idempotency_key=None,
                message=(
                    f"Equipo {serial} sin horas de origen; no procesado."
                )
            )
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
