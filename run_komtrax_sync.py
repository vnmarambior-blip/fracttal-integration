"""Ejecutor programable de la sincronización Komtrax -> Fracttal.

Este archivo es el punto de entrada para la tarea diaria. A diferencia de los
archivos ``test_*``, puede aplicar actualizaciones cuando SYNC_DRY_RUN=false.

Modo por defecto: file (lee el fixture XML, cero red Komtrax). Solo ``--live``
consulta la API real de Komtrax, con la cuota mínima aplicada por
``_compare_hours.get_komtrax_fleet``.

Decisión controladora (vinculante) sobre namespacing:
``KOMTRAX_SOURCE = "Komtrax"`` es el nombre canónico de la fuente Komtrax.
Su forma canónica en claves de idempotencia es ``"KOMTRAX"``, distinta de
``"MYDEVELON"`` (ver ``api.build_idempotency_key`` y los tests de
namespacing en ``test_komtrax_sync.py``). Este ejecutor pasa
``source="Komtrax"`` a ``api.process_equipment``, que lo propaga a la
consulta ``telemetry_source``, a la construcción interna de la clave de
idempotencia y a ``apply_meter_reading`` (etiquetas y auditoría); el
default ``source="MyDevelon"`` conserva el comportamiento MyDevelon
byte-idéntico.
"""

import argparse
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone

import _compare_hours
from _compare_hours import KOMTRAX_MACHINES
from _compare_hours import classify_komtrax_gap
from _compare_hours import decide_comparison
from _compare_hours import get_fracttal_hourmeter
from _compare_hours import get_fracttal_items
from _compare_hours import get_komtrax_fleet
from _compare_hours import get_komtrax_token_cached
from _compare_hours import parse_komtrax_hours
from api import get_access_token as get_fracttal_access_token
from api import process_equipment


KOMTRAX_SOURCE = "Komtrax"

DEFAULT_FIXTURE = "komtrax_fleet_fixture.xml"
DEFAULT_MIN_INTERVAL_SECONDS = 300

COUNT_KEYS = (
    "UPDATE",
    "SKIP_EQUAL",
    "REVIEW_OLD_SOURCE",
    "REVIEW_INCONSISTENCY",
    "ERROR",
)


def env_flag(name, default=False):
    """Convierte una variable de entorno booleana de manera predecible."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def gates_closed():
    """Gate productivo: True solo si Regla 0 y H1 están cerrados.

    No existe un helper importable y barato para este gate:
    ``reconcile.py`` solo expone ``reconcile_orphan_intents`` (cierra con
    PUT/GET reales, no es una consulta pura) y el conteo de huérfanas
    exigiría conexión SQL vía ``database.list_horometer_write_intents``;
    además no hay ningún flag H1 consultable en código. Por eso el gate
    usa el env explícito ``KOMTRAX_SYNC_GATES_OK == "1"``, fijado
    manualmente solo tras verificar el cierre de Regla 0/H1.
    """
    return (os.getenv("KOMTRAX_SYNC_GATES_OK") or "").strip() == "1"


def normalize_unit(value):
    """Normaliza un código de unidad para comparación (quita espacios)."""
    return "".join(str(value or "").split()).upper()


def find_fracttal_item(unit, all_items):
    """Busca el item Fracttal por unidad normalizada.

    La comparación ignora espacios y mayúsculas; el item devuelto conserva
    el código Fracttal original intacto (nunca se reescribe).
    """
    wanted = normalize_unit(unit)
    for item in all_items or []:
        if normalize_unit(item.get("code", "")) == wanted:
            return item
    return None


def parse_args(argv=None):
    """Argumentos de fuente Komtrax (file por defecto, cero red)."""

    parser = argparse.ArgumentParser(
        description="Sincronización Komtrax -> Fracttal."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Consulta la API real (respeta cuota mínima).",
    )
    parser.add_argument(
        "--fleet-xml",
        default=os.getenv("KOMTRAX_FIXTURE", DEFAULT_FIXTURE),
        help="Fixture XML en modo file.",
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
                "KOMTRAX_FLEET_MIN_INTERVAL_SECONDS",
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
    if not dry_run and not gates_closed():
        print("BLOQUEADO: Regla 0 / H1 abiertos; solo dry-run permitido.")
        raise SystemExit(2)

    mode = "live" if args.live else "file"
    retrieved_at = datetime.now(timezone.utc)

    print("=" * 70)
    print("SINCRONIZACIÓN DIARIA: KOMTRAX -> FRACTTAL")
    print(f"Modo: {'SIMULACIÓN' if dry_run else 'PRODUCCIÓN'}")
    print(f"Fuente Komtrax: {mode}")
    print("=" * 70)

    if mode == "live":
        # La cuota la aplica get_komtrax_fleet; el intervalo del flag se
        # propaga temporalmente y se restaura para no mutar el módulo
        # (pasarlo como parámetro exigiría cambiar get_komtrax_fleet).
        previous_interval = (
            _compare_hours.KOMTRAX_FLEET_MIN_INTERVAL_SECONDS
        )
        _compare_hours.KOMTRAX_FLEET_MIN_INTERVAL_SECONDS = (
            args.min_interval_seconds
        )
        try:
            komtrax_token = get_komtrax_token_cached()
            try:
                fleet_xml = get_komtrax_fleet(komtrax_token)
            except _compare_hours.KomtraxFleetError as error:
                print(f"[CUOTA] {error}")
                raise RuntimeError(
                    "Fetch Komtrax bloqueado por cuota mínima."
                ) from error
        finally:
            _compare_hours.KOMTRAX_FLEET_MIN_INTERVAL_SECONDS = (
                previous_interval
            )
    else:
        with open(args.fleet_xml, encoding="utf-8") as handle:
            fleet_xml = handle.read()

    kt_data = parse_komtrax_hours(fleet_xml)
    print(f"Equipos Komtrax parseados: {len(kt_data)}")

    fracttal_token = get_fracttal_access_token()
    ft_items = get_fracttal_items(fracttal_token)
    print(f"Equipos Fracttal recibidos: {len(ft_items)}")

    counts = {key: 0 for key in COUNT_KEYS}

    for mach in KOMTRAX_MACHINES:
        serial = str(mach.get("serial", "")).strip()
        unit = str(mach.get("unit", "")).strip()

        kt = kt_data.get(serial)
        gap = classify_komtrax_gap(kt)
        if gap != "OK":
            counts["REVIEW_INCONSISTENCY"] += 1
            print(f"[RESULTADO] {serial}: REVIEW_INCONSISTENCY "
                  f"(Komtrax {gap})")
            continue

        kt_hours = kt["hours"]
        kt_dt = kt["datetime"]

        item = find_fracttal_item(unit, ft_items)
        if item is None:
            counts["ERROR"] += 1
            print(f"[RESULTADO] {serial}: ERROR "
                  f"(unidad {unit} sin match Fracttal)")
            continue

        code = item.get("code")
        try:
            ft_result = get_fracttal_hourmeter(
                fracttal_token, code, ft_items)
        except Exception as error:
            counts["ERROR"] += 1
            print(f"[RESULTADO] {serial}: ERROR ({error})")
            continue

        if "error" in ft_result:
            counts["ERROR"] += 1
            print(f"[RESULTADO] {serial}: ERROR "
                  f"({ft_result['error']})")
            continue

        ft_value = ft_result["value"]
        ft_date = ft_result["date"]
        if ft_value is None:
            counts["ERROR"] += 1
            print(f"[RESULTADO] {serial}: ERROR "
                  "(Fracttal sin last_data)")
            continue

        try:
            kt_val = round(float(kt_hours), 2)
            ft_val = round(float(ft_value), 2)
        except (TypeError, ValueError):
            counts["ERROR"] += 1
            print(f"[RESULTADO] {serial}: ERROR (no numérico)")
            continue

        decision = decide_comparison(kt_val, ft_val, kt_dt, ft_date)
        if decision == "SKIP_EQUAL":
            counts["SKIP_EQUAL"] += 1
            print(f"[RESULTADO] {serial}: SKIP_EQUAL "
                  f"({kt_val} == {ft_val})")
            continue
        if decision == "REVIEW_OLD_SOURCE":
            counts["REVIEW_OLD_SOURCE"] += 1
            print(f"[RESULTADO] {serial}: REVIEW_OLD_SOURCE "
                  f"({kt_val} vs {ft_val})")
            continue
        if decision != "UPDATE":
            counts["ERROR"] += 1
            print(f"[RESULTADO] {serial}: ERROR "
                  f"(decisión inesperada {decision})")
            continue

        try:
            result = process_equipment(
                token=fracttal_token,
                serial=serial,
                new_value=kt_val,
                dry_run=dry_run,
                reading_datetime=kt_dt,
                retrieved_at=retrieved_at,
                source=KOMTRAX_SOURCE,
            )
        except Exception as error:  # Continúa para que un equipo no bloquee al resto.
            counts["ERROR"] += 1
            print(f"[ERROR] {serial}: {error}")
            continue

        counts["UPDATE"] += 1
        status = result.get("status", "UPDATE") if result else "UPDATE"
        print(f"[RESULTADO] {serial}: UPDATE ({kt_val}) -> {status}")

    print("")
    print("RESUMEN")
    for key in COUNT_KEYS:
        print(f"{key}: {counts[key]}")

    return counts


if __name__ == "__main__":
    main()
