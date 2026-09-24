# -*- coding: utf-8 -*-
"""Reconciliacion READ-ONLY: inventario Komtrax vs maquinaria Fracttal (SQL)."""

from database import get_connection

# Inventario Komtrax recibido
KOMTRAX_INVENTORY = [
    {"serial": "55267",   "model": "GD675",  "type": "5",    "unit_name": "MN04"},
    {"serial": "354483",  "model": "PC200LC", "type": "8",    "unit_name": "MH02"},
    {"serial": "400293",  "model": "PC200LC", "type": "8M0",  "unit_name": "MH04"},
    {"serial": "73180",   "model": "WA200",  "type": "6",    "unit_name": "CF 01"},
    {"serial": "400743",  "model": "PC200LC", "type": "8M0",  "unit_name": "MH06"},
    {"serial": "400726",  "model": "PC200LC", "type": "8M0",  "unit_name": "MH05"},
    {"serial": "600578",  "model": "PC210LC", "type": "10M0", "unit_name": "MH20"},
    {"serial": "600730",  "model": "PC210LC", "type": "10M0", "unit_name": "MH21"},
    {"serial": "68181",   "model": "WA380",  "type": "6",    "unit_name": "CF 02"},
    {"serial": "600958",  "model": "PC210LC", "type": "10M0", "unit_name": "MH23"},
    {"serial": "601076",  "model": "PC210LC", "type": "10M0", "unit_name": "MH24"},
    {"serial": "601326",  "model": "PC210LC", "type": "10M0", "unit_name": "MH31"},
    {"serial": "19144",   "model": "WA380",  "type": "8.00E+00", "unit_name": "vacio"},
]


def main():
    cursor = connection.cursor()

    # Obtener TODA la maquinaria
    cursor.execute("""
        SELECT
            m.id,
            m.serial,
            m.equipment_code,
            m.name,
            m.manufacturer,
            m.model,
            m.active,
            m.asset_type
        FROM machinery m
        ORDER BY m.serial
    """)

    rows = cursor.fetchall()

    # Construir indices
    machines_by_serial = {}
    machines_by_code = {}
    for row in rows:
        m_id, serial, code, name, manuf, model, active, asset_type = row
        serial_str = str(serial).strip().upper() if serial else ""
        code_str = str(code).strip().upper() if code else ""
        model_str = str(model).strip().upper() if model else ""

        rec = {
            "id": m_id,
            "serial": serial_str,
            "equipment_code": code_str,
            "name": name,
            "manufacturer": manuf,
            "model": model_str,
            "active": active,
            "asset_type": asset_type,
        }
        if serial_str:
            machines_by_serial.setdefault(serial_str, []).append(rec)
        if code_str:
            machines_by_code.setdefault(code_str, []).append(rec)

    print("=" * 80)
    print("RECONCILIACION KOMTRAX -> FRACTTAL (READ-ONLY)")
    print("=" * 80)
    print(f"Maquinarias en Fracttal (SQL): {len(rows)}")
    print(f"Equipos en inventario Komtrax: {len(KOMTRAX_INVENTORY)}")
    print()

    print("=" * 80)
    print("COMPARACION PUERTA-A-PUERTA")
    print("=" * 80)

    results = []
    for kom in KOMTRAX_INVENTORY:
        serial = kom["serial"]
        model = kom["model"]
        unit_name = kom["unit_name"]
        kom_type = kom["type"]

        # Buscar por serial
        by_serial = machines_by_serial.get(serial, [])

        # Buscar por equipment_code (unit_name)
        by_code = machines_by_code.get(str(unit_name).strip().upper(), [])

        # Buscar por modelo parcial
        by_model = [m for m in rows if model.upper() in str(m["model"]).upper()]

        entry = {
            "serial": serial,
            "model": model,
            "unit_name": unit_name,
            "komtrax_type": kom_type,
            "by_serial": by_serial,
            "by_code": by_code,
            "by_model_match": by_model,
        }
        results.append(entry)

    # Imprimir resultados
    for i, r in enumerate(results, 1):
        serial = r["serial"]
        model = r["model"]
        unit_name = r["unit_name"]

        by_serial = r["by_serial"]
        by_code = r["by_code"]

        status = ""
        if by_serial and by_code:
            if by_serial == by_code:
                status = "EXACT MATCH"
            else:
                status = "CONFLICT: serial vs code"
        elif by_serial:
            status = "FOUND BY SERIAL"
        elif by_code:
            status = "FOUND BY CODE (no serial match)"
        else:
            status = "NOT FOUND"

        print(f"\n[{i}] Komtrax: serial={serial}, model={model}, unit={unit_name}")
        print(f"     Estado: {status}")

        if by_serial:
            for m in by_serial:
                print(f"     -> SQL por serial: id={m['id']}, serial={m['serial']}, "
                      f"code={m['equipment_code']}, model={m['model']}, "
                      f"name={m['name']}, active={m['active']}")
        if by_code and by_code != by_serial:
            for m in by_code:
                print(f"     -> SQL por code: id={m['id']}, serial={m['serial']}, "
                      f"code={m['equipment_code']}, model={m['model']}, "
                      f"name={m['name']}, active={m['active']}")
        if not by_serial and not by_code:
            print(f"     -> No encontrado en SQL por serial ni equipment_code")

    # Resumen
    print()
    print("=" * 80)
    print("RESUMEN")
    print("=" * 80)
    found_by_serial = sum(1 for r in results if r["by_serial"])
    found_by_code = sum(1 for r in results if r["by_code"] and not r["by_serial"])
    not_found = sum(1 for r in results if not r["by_serial"] and not r["by_code"])
    conflicts = sum(1 for r in results if r["by_serial"] and r["by_code"] and r["by_serial"] != r["by_code"])

    print(f"Total Komtrax: {len(KOMTRAX_INVENTORY)}")
    print(f"Found by serial: {found_by_serial}")
    print(f"Found by code only: {found_by_code}")
    print(f"Conflict serial vs code: {conflicts}")
    print(f"Not found in Fracttal: {not_found}")

    # Buscar maquinas en Fracttal que NO estan en Komtrax
    kom_serials = {str(k["serial"]).strip().upper() for k in KOMTRAX_INVENTORY}
    extra_in_fracttal = []
    for serial, machines in machines_by_serial.items():
        if serial not in kom_serials:
            for m in machines:
                extra_in_fracttal.append(m)

    print(f"\nMaquinas en Fracttal NO en inventario Komtrax: {len(extra_in_fracttal)}")
    if extra_in_fracttal:
        for m in extra_in_fracttal[:10]:
            print(f"  SQL serial={m['serial']}, code={m['equipment_code']}, model={m['model']}, name={m['name']}")

    connection.close()
    print("\nReconciliacion completada (read-only).")


if __name__ == "__main__":
    main()
