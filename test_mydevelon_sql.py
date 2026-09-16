from mydevelon import (
    get_access_token,
    get_equipment_snapshot_xml,
    parse_equipment_snapshot_xml,
)
from database import get_machinery_by_serial


# ============================================================
# CONFIGURACIÓN DE PRUEBA
# ============================================================

OEM = "DEVELON"
MODEL = "DX225LCA"
MYDEVELON_SERIAL = "CEBDX-001085"


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("TEST MYDEVELON → SQL SERVER")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. Obtener token MyDevelon
    # --------------------------------------------------------

    print("\n1. Obteniendo token MyDevelon...")

    try:
        token = get_access_token()
        print("[OK] Token obtenido.")

    except Exception as e:
        print(f"[ERROR] No fue posible obtener el token:")
        print(e)
        return

    # --------------------------------------------------------
    # 2. Consultar equipo en MyDevelon
    # --------------------------------------------------------

    print("\n2. Consultando equipo en MyDevelon...")

    print(f"OEM: {OEM}")
    print(f"Modelo: {MODEL}")
    print(f"Serial MyDevelon: {MYDEVELON_SERIAL}")

    try:
        xml_text = get_equipment_snapshot_xml(
            token=token,
            make_code=OEM,
            model=MODEL,
            serial_number=MYDEVELON_SERIAL,
        )

        equipment = parse_equipment_snapshot_xml(xml_text)

    except Exception as e:
        print(f"[ERROR] No fue posible consultar MyDevelon:")
        print(e)
        return

    # --------------------------------------------------------
    # 3. Mostrar información obtenida
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("DATOS OBTENIDOS DESDE MYDEVELON")
    print("=" * 70)

    print(f"OEM:              {equipment.get('oem_name')}")
    print(f"Modelo:            {equipment.get('model')}")
    print(f"Equipment ID:      {equipment.get('equipment_id')}")
    print(f"SerialNumber:      {equipment.get('serial_number')}")
    print(f"PIN:               {equipment.get('pin')}")
    print(f"Horómetro:         {equipment.get('operating_hours')}")
    print(f"Fecha horómetro:   {equipment.get('operating_hours_datetime')}")
    print(f"Hora consulta:     {equipment.get('retrieved_at')}")

    # --------------------------------------------------------
    # 4. Validar PIN
    # --------------------------------------------------------

    pin = equipment.get("pin")

    if not pin:
        print("\n[ERROR] MyDevelon no entregó PIN.")
        return

    print("\n[OK] PIN obtenido:")
    print(f"     {pin}")

    # --------------------------------------------------------
    # 5. Buscar PIN en SQL Server
    # --------------------------------------------------------

    print("\n3. Buscando PIN en SQL Server...")

    try:
        machinery = get_machinery_by_serial(pin)

    except Exception as e:
        print("[ERROR] Error consultando SQL Server:")
        print(e)
        return

    # --------------------------------------------------------
    # 6. Resultado
    # --------------------------------------------------------

    if machinery is None:

        print("\n" + "=" * 70)
        print("RESULTADO")
        print("=" * 70)

        print("[ERROR] No se encontró el PIN en machinery.serial.")
        print(f"PIN buscado: {pin}")

        return

    print("\n" + "=" * 70)
    print("MATCH MYDEVELON → SQL SERVER")
    print("=" * 70)

    print(f"SQL ID:            {machinery.get('id')}")
    print(f"Código Fracttal:   {machinery.get('equipment_code')}")
    print(f"Nombre:            {machinery.get('name')}")
    print(f"Fabricante:        {machinery.get('manufacturer')}")
    print(f"Modelo:            {machinery.get('model')}")
    print(f"Serial:            {machinery.get('serial')}")

    print("\n" + "=" * 70)
    print("VALIDACIÓN")
    print("=" * 70)

    sql_serial = machinery.get("serial")

    if sql_serial == pin:
        print("[OK] PIN MyDevelon coincide con machinery.serial.")
    else:
        print("[ERROR] El serial no coincide.")

    print("\n[OK] Prueba terminada.")
    print("[OK] No se modificó SQL Server.")
    print("[OK] No se modificó Fracttal.")
    print("[OK] No se modificó MyDevelon.")


if __name__ == "__main__":
    main()