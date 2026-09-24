# -*- coding: utf-8 -*-
"""Ejecutor Komtrax -> Fracttal en modo DRY-RUN (READ-ONLY efectivo).

Flujo: Komtrax -> normalizacion -> comparacion -> decision ->
``process_equipment(source="Komtrax")`` -> reporte.

Sin escrituras productivas: SYNC_DRY_RUN=true por defecto y cualquier
intento de modo productivo aborta antes de red o writes (R0/H1 abiertos).
"""

import argparse
import os
from datetime import datetime, timezone

import api
import komtrax
from _compare_hours import (
    KOMTRAX_MACHINES,
    get_fracttal_hourmeter,
    get_fracttal_items,
)


def env_flag(name, default=False):
    """Convierte una variable de entorno booleana de manera predecible."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_args(argv=None):
    """Argumentos del ejecutor Komtrax (file por defecto, cero red)."""

    parser = argparse.ArgumentParser(
        description="Sincronización Komtrax -> Fracttal (dry-run)."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Consulta la API real (respeta cuota mínima de 5 min).",
    )
    parser.add_argument(
        "--fleet-xml",
        default=os.getenv("KOMTRAX_FIXTURE"),
        help="Fixture XML en modo file.",
    )

    return parser.parse_args(argv)


def main(argv=None, now=None):
    dry_run = env_flag("SYNC_DRY_RUN", default=True)
    args = parse_args(argv)

    if not dry_run:
        print("BLOQUEADO: SYNC_DRY_RUN=false con R0/H1 abiertos; "
              "solo dry-run permitido.")
        raise SystemExit(2)

    retrieved_at = now or datetime.now(timezone.utc)
    if isinstance(retrieved_at, str):
        retrieved_at = datetime.fromisoformat(retrieved_at)

    if args.live:
        kt_token = komtrax.get_komtrax_token_cached()
        kt_pages = komtrax.get_komtrax_fleet_all(kt_token)
    else:
        if not args.fleet_xml:
            print("BLOQUEADO: se requiere --live o --fleet-xml.")
            raise SystemExit(2)
        with open(args.fleet_xml, encoding="utf-8") as handle:
            kt_pages = [handle.read()]

    kt_data = {}
    for kt_xml in kt_pages:
        kt_data.update(komtrax.parse_komtrax_hours(kt_xml))

    ft_token = api.get_access_token()
    ft_items = get_fracttal_items(ft_token)

    counts = {
        "UPDATE": 0,
        "SKIP_EQUAL": 0,
        "REVIEW_OLD_SOURCE": 0,
        "REVIEW_INCONSISTENCY": 0,
        "ERROR": 0,
    }

    print("=" * 90)
    print("SINCRONIZACION KOMTRAX -> FRACTTAL (DRY-RUN)")
    print("=" * 90)

    for mach in KOMTRAX_MACHINES:
        serial = mach["serial"]
        unit = mach["unit"]

        kt = kt_data.get(serial)
        gap = komtrax.classify_komtrax_gap(kt)
        if gap != "OK":
            print(f"{serial:<8} {'N/A':<12} REVIEW_INCONSISTENCY: Komtrax {gap}")
            counts["REVIEW_INCONSISTENCY"] += 1
            continue

        ft_result = get_fracttal_hourmeter(ft_token, unit, ft_items)
        if "error" in ft_result:
            print(f"{serial:<8} {'N/A':<12} ERROR: {ft_result['error'][:50]}")
            counts["ERROR"] += 1
            continue

        try:
            kt_val = round(float(kt["hours"]), 2)
            ft_val = round(float(ft_result["value"]), 2)
        except (ValueError, TypeError):
            print(f"{serial:<8} {'N/A':<12} ERROR: No numerico")
            counts["ERROR"] += 1
            continue

        result = komtrax.decide_comparison(
            kt_val, ft_val, kt["datetime"], ft_result["date"]
        )
        if result != "UPDATE":
            print(f"{serial:<8} {kt_val:<12.2f} {result}")
            counts[result] += 1
            continue

        pipeline = api.process_equipment(
            token=ft_token,
            serial=serial,
            new_value=kt_val,
            dry_run=True,
            reading_datetime=kt["datetime"],
            retrieved_at=retrieved_at,
            source="Komtrax",
        )
        print(f"{serial:<8} {kt_val:<12.2f} UPDATE -> {pipeline.get('status')}")
        counts["UPDATE"] += 1

    print("=" * 90)
    print(f"Total evaluados: {len(KOMTRAX_MACHINES)}")
    for key in (
        "UPDATE",
        "SKIP_EQUAL",
        "REVIEW_OLD_SOURCE",
        "REVIEW_INCONSISTENCY",
        "ERROR",
    ):
        print(f"{key}: {counts[key]}")
    print("PUT/POST/PATCH/DELETE productivos: 0")

    return counts


if __name__ == "__main__":
    main()
