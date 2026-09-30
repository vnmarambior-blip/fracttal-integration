# -*- coding: utf-8 -*-
"""Ejecutor Komtrax -> Fracttal (Fracttal intocable + SQL auditable).

Flujo: Komtrax -> normalizacion -> comparacion -> decision ->
``process_equipment(source="Komtrax")`` -> reporte.

Semántica dry_run (proyecto): ningún PUT/POST/PATCH/DELETE a Fracttal;
SQL solo recibe filas WOULD_UPDATE/revisión. El modo productivo de este
runner está bloqueado por diseño (SystemExit 2) hasta habilitarlo.
"""

import argparse
import os
from datetime import datetime, timezone

import api
import komtrax
from oem_common import env_flag
from _compare_hours import (
    KOMTRAX_MACHINES,
    get_fracttal_hourmeter,
    get_fracttal_items,
)


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
        "--dry-run",
        action="store_true",
        help="Fuerza simulación aunque SYNC_DRY_RUN=false (cero PUTs).",
    )
    parser.add_argument(
        "--fleet-xml",
        default=os.getenv("KOMTRAX_FIXTURE"),
        help="Fixture XML en modo file.",
    )

    return parser.parse_args(argv)


def main(argv=None, now=None):
    args = parse_args(argv)

    # Contrato CLI:
    #   sin --live            -> DRY-RUN (fixtures, cero PUTs), ignore env.
    #   --dry-run             -> DRY-RUN explícito, ignore env.
    #   --live + env true     -> DRY-RUN contra API live (lectura real, cero PUTs).
    #   --live + env false    -> PRODUCCIÓN.
    # Sin flag --production: --live es la única vía a producción.
    if args.dry_run or not args.live:
        dry_run = True
    else:
        dry_run = env_flag("SYNC_DRY_RUN", default=True)

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
        try:
            with open(args.fleet_xml, encoding="utf-8") as handle:
                fleet_text = handle.read()
        except OSError as error:
            print(f"ERROR: fixture inválido/inexistente: {args.fleet_xml} ({error})")
            raise SystemExit(2)
        kt_pages = [fleet_text]

    try:
        kt_data = {}
        for kt_xml in kt_pages:
            kt_data.update(komtrax.parse_komtrax_hours(kt_xml))
    except Exception as error:
        print(f"ERROR: fixture inválido/inexistente: {args.fleet_xml or '--live'} ({error})")
        raise SystemExit(2)

    ft_token = api.get_access_token()
    ft_items = get_fracttal_items(ft_token)

    counts = {
        "UPDATE": 0,
        "SKIP_EQUAL": 0,
        "REVIEW_OLD_SOURCE": 0,
        "REVIEW_INCONSISTENCY": 0,
        "ERROR": 0,
        "VERIFIED": 0,
        "WRITE_AMBIGUOUS": 0,
    }

    mode_label = "PRODUCCION" if not dry_run else "DRY-RUN"
    print("=" * 90)
    print(f"SINCRONIZACION KOMTRAX -> FRACTTAL ({'PRODUCCION' if not dry_run else 'DRY-RUN'})")
    print("=" * 90)

    for mach in KOMTRAX_MACHINES:
        serial = mach["serial"]
        unit = mach["unit"]
        model = mach.get("model")
        status = None

        kt = kt_data.get(serial)
        gap = komtrax.classify_komtrax_gap(kt)
        if gap != "OK":
            print()
            print("=" * 60)
            print(f"PROCESANDO SERIAL: {serial}")
            print("=" * 60)
            print(f"     Código: {unit}")
            print(f"     Modelo: {model}")
            print(f"Komtrax {gap}: sin lectura válida; no se procesa.")
            print(f"[RESULTADO] {serial}: REVIEW_INCONSISTENCY")
            counts["REVIEW_INCONSISTENCY"] += 1
            continue

        ft_result = get_fracttal_hourmeter(ft_token, unit, ft_items)
        if "error" in ft_result:
            print()
            print("=" * 60)
            print(f"PROCESANDO SERIAL: {serial}")
            print("=" * 60)
            print(f"     Código: {unit}")
            print(f"     Modelo: {model}")
            print(f"ERROR: {ft_result['error'][:50]}")
            print(f"[RESULTADO] {serial}: ERROR")
            counts["ERROR"] += 1
            continue

        try:
            kt_val = round(float(kt["hours"]), 2)
            ft_val = round(float(ft_result["value"]), 2)
        except (ValueError, TypeError):
            print()
            print("=" * 60)
            print(f"PROCESANDO SERIAL: {serial}")
            print("=" * 60)
            print(f"     Código: {unit}")
            print(f"     Modelo: {model}")
            print("ERROR: No numerico")
            print(f"[RESULTADO] {serial}: ERROR")
            counts["ERROR"] += 1
            continue

        result = komtrax.decide_comparison(
            kt_val, ft_val, kt["datetime"], ft_result["date"]
        )
        if result != "UPDATE":
            print()
            print("=" * 60)
            print(f"PROCESANDO SERIAL: {serial}")
            print("=" * 60)
            print(f"     Código: {unit}")
            print(f"     Modelo: {model}")
            print(f"     Valor Fracttal: {ft_val}")
            print(f"     Última lectura Fracttal: {ft_result.get('date')}")
            print(f"     Valor Komtrax: {kt_val}")
            print(f"     Acción: {result}")
            print(f"[RESULTADO] {serial}: {result}")
            counts[result] += 1
            continue

        pipeline = api.process_equipment(
            token=ft_token,
            serial=serial,
            new_value=kt_val,
            dry_run=dry_run,
            reading_datetime=kt["datetime"],
            retrieved_at=retrieved_at,
            source="Komtrax",
        )
        status = pipeline.get("status")
        print(f"[RESULTADO] {serial}: {status}")
        counts["UPDATE"] += 1
        if status == "VERIFIED":
            counts["VERIFIED"] += 1
        elif status == "WRITE_AMBIGUOUS":
            counts["WRITE_AMBIGUOUS"] += 1

    print("=" * 90)
    print(f"Total evaluados: {len(KOMTRAX_MACHINES)}")
    for key in (
        "UPDATE",
        "SKIP_EQUAL",
        "REVIEW_OLD_SOURCE",
        "REVIEW_INCONSISTENCY",
        "ERROR",
        "VERIFIED",
        "WRITE_AMBIGUOUS",
    ):
        print(f"{key}: {counts[key]}")

    if len(KOMTRAX_MACHINES) > 0 and counts["UPDATE"] == 0 and counts["SKIP_EQUAL"] == 0:
        print("COBERTURA BAJA: 0 equipos en estado exitoso.")
        raise SystemExit(3)

    if dry_run:
        print("PUT/POST/PATCH/DELETE productivos: 0")
    else:
        unverified = counts["UPDATE"] - counts["VERIFIED"] - counts["WRITE_AMBIGUOUS"]
        print(f"PUT verificados: {counts['VERIFIED']}")
        print(f"PUT ambiguos: {counts['WRITE_AMBIGUOUS']}")
        print(f"UPDATE no verificados (bloqueados/error): {unverified}")

    return counts


if __name__ == "__main__":
    main()
