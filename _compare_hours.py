# -*- coding: utf-8 -*-
"""Comparacion horometros: Komtrax vs Fracttal (READ-ONLY)."""
import os

from dotenv import load_dotenv
load_dotenv()

import requests
from api import get_access_token as get_fracttal_token, get_valid_hourmeter
from komtrax import (
    KomtraxFleetError,
    get_komtrax_token_cached,
    get_komtrax_fleet_all,
    parse_komtrax_hours,
    classify_komtrax_gap,
    normalize_unit,
    decide_comparison,
)


FRACTTAL_CLIENT_ID = os.getenv("FRACTTAL_CLIENT_ID")
FRACTTAL_CLIENT_SECRET = os.getenv("FRACTTAL_CLIENT_SECRET")

KOMTRAX_MACHINES = [
    {"serial": "55267", "unit": "MN04", "model": "GD675-5"},
    {"serial": "354483", "unit": "MH02", "model": "PC200LC-8"},
    {"serial": "400293", "unit": "MH04", "model": "PC200LC-8M0"},
    {"serial": "73180", "unit": "CF01", "model": "WA200"},
    {"serial": "400743", "unit": "MH06", "model": "PC200LC-8M0"},
    {"serial": "400726", "unit": "MH05", "model": "PC200LC-8M0"},
    {"serial": "600578", "unit": "MH20", "model": "PC210LC-10M0"},
    {"serial": "600730", "unit": "MH21", "model": "PC210LC-10M0"},
    {"serial": "68181", "unit": "CF02", "model": "WA380-6"},
    {"serial": "600958", "unit": "MH23", "model": "PC210LC-10M0"},
    {"serial": "601076", "unit": "MH24", "model": "PC210LC-10M0"},
    {"serial": "601326", "unit": "MH31", "model": "PC210LC-10M0"},
    {"serial": "19144", "unit": "CF05", "model": "WA380-8E0"},
]

def get_fracttal_items(token):
    headers = {"Authorization": f"Bearer {token}"}
    items = []
    start = 0
    while True:
        resp = requests.get("https://app.fracttal.com/api/items/",
            headers=headers, params={"item_type": 2, "limit": 100, "start": start}, timeout=30)
        if not resp.ok:
            raise RuntimeError(f"Fracttal items: HTTP {resp.status_code}")
        data = resp.json()
        items.extend(data.get("data", []))
        total = data.get("total", 0)
        if len(items) >= total or not items:
            break
        start += 100
    return items

def get_fracttal_hourmeter(ft_token, code, all_items):
    wanted = normalize_unit(code)
    for item in all_items:
        if normalize_unit(item.get("code", "")) != wanted or wanted is None:
            continue
        try:
            meter = get_valid_hourmeter(ft_token, item)
            last_data = meter.get("last_data") or {}
            return {"value": last_data.get("value"), "date": last_data.get("date")}
        except ValueError as e:
            return {"error": str(e)}
    return {"error": "EQUIPMENT_NOT_FOUND"}

def main():
    print("=" * 90)
    print("COMPARACION HOROMETROS: Komtrax vs Fracttal (READ-ONLY)")
    print("=" * 90)
    print()

    print("1. Autenticando Komtrax...")
    kt_token = get_komtrax_token_cached()
    print("   OK")

    print("2. Obteniendo flota Komtrax...")
    try:
        kt_pages = get_komtrax_fleet_all(kt_token)
    except KomtraxFleetError as error:
        print(str(error))
        raise SystemExit(0)
    kt_data = {}
    for kt_xml in kt_pages:
        kt_data.update(parse_komtrax_hours(kt_xml))
    print(f"   Páginas Komtrax: {len(kt_pages)}")
    print(f"   Equipos Komtrax parseados: {len(kt_data)}")

    print("3. Autenticando Fracttal...")
    ft_token = get_fracttal_token()
    print("   OK")

    print("4. Obteniendo equipos Fracttal...")
    ft_items = get_fracttal_items(ft_token)
    print(f"   {len(ft_items)} equipos obtenidos")

    print()
    print("=" * 90)
    print(f"{'Serial':<8} {'Komtrax h':<12} {'Komtrax dt':<22} {'Fracttal h':<12} {'Fracttal dt':<22} {'Delta':<8} {'Resultado'}")
    print("=" * 90)

    match_count = 0
    skip_count = 0
    review_count = 0
    inconsistency_count = 0
    error_count = 0

    for mach in KOMTRAX_MACHINES:
        serial = mach["serial"]
        unit = mach["unit"]

        kt = kt_data.get(serial)
        gap = classify_komtrax_gap(kt)
        if gap != "OK":
            print(f"{serial:<8} {'N/A':<12} {'N/A':<22} {'N/A':<12} {'N/A':<22} {'N/A':<8} REVIEW_INCONSISTENCY: Komtrax {gap}")
            inconsistency_count += 1
            continue

        kt_hours = kt["hours"]
        kt_dt = kt["datetime"]

        ft_result = get_fracttal_hourmeter(ft_token, unit, ft_items)
        if "error" in ft_result:
            print(f"{serial:<8} {str(kt_hours):<12} {str(kt_dt):<22} {'N/A':<12} {'N/A':<22} {'N/A':<8} ERROR: {ft_result['error'][:50]}")
            error_count += 1
            continue

        ft_value = ft_result["value"]
        ft_date = ft_result["date"]
        if ft_value is None:
            print(f"{serial:<8} {str(kt_hours):<12} {str(kt_dt):<22} {'N/A':<12} {'N/A':<22} {'N/A':<8} ERROR: Fracttal sin last_data")
            error_count += 1
            continue

        try:
            kt_val = round(float(kt_hours), 2)
            ft_val = round(float(ft_value), 2)
        except (ValueError, TypeError):
            print(f"{serial:<8} {str(kt_hours):<12} {str(kt_dt):<22} {str(ft_value):<12} {str(ft_date):<22} {'N/A':<8} ERROR: No numerico")
            error_count += 1
            continue

        delta = round(kt_val - ft_val, 2)

        result = decide_comparison(kt_val, ft_val, kt_dt, ft_date)
        if result == "SKIP_EQUAL":
            skip_count += 1
        elif result == "UPDATE":
            match_count += 1
        else:
            review_count += 1

        kt_dt_str = kt_dt.strftime("%Y-%m-%d %H:%M") if kt_dt else "N/A"
        ft_dt_str = ft_date[:19] if ft_date else "N/A"
        print(f"{serial:<8} {kt_val:<12.2f} {kt_dt_str:<22} {ft_val:<12.2f} {ft_dt_str:<22} {delta:+8.2f} {result}")

    print("=" * 90)
    print()
    print(f"Total evaluados: {len(KOMTRAX_MACHINES)}")
    print(f"MATCH (UPDATE): {match_count}")
    print(f"SKIP_EQUAL: {skip_count}")
    print(f"REVIEW_OLD_SOURCE: {review_count}")
    print(f"REVIEW_INCONSISTENCY: {inconsistency_count}")
    print(f"ERROR: {error_count}")
    print()
    print("GETs realizados: Komtrax fleet(1) + Fracttal items(3 pag) + Fracttal meters(13)")
    print("PUT/POST/PATCH/DELETE: 0")
    print("Cambios SQL: 0")


if __name__ == "__main__":
    main()
