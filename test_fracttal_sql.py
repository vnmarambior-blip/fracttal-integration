from database import get_machinery_by_serial
from api import (
    get_access_token,
    get_equipment_by_serial,
    get_valid_hourmeter,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

MACHINERY_CODE = "MH22"
SERIAL = "DHKCEBDXCK0001085"


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("TEST SQL SERVER -> FRACTTAL")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. Buscar activo en SQL Server
    # --------------------------------------------------------

    print("\n1. Buscando activo en SQL Server...")
    print(f"   Código:  {MACHINERY_CODE}")
    print(f"   Serial:  {SERIAL}")

    machinery = get_machinery_by_serial(SERIAL)

    if machinery is None:
        print("[ERROR] No se encontró el activo en SQL Server.")
        return

    print("[OK] Activo encontrado en SQL Server.")

    print()
    print("Datos SQL:")
    print(f"  ID:             {machinery.get('id')}")
    print(f"  Código:         {machinery.get('equipment_code')}")
    print(f"  Serial:         {machinery.get('serial')}")
    print(f"  Nombre:         {machinery.get('name')}")
    print(f"  Fabricante:     {machinery.get('manufacturer')}")
    print(f"  Modelo:         {machinery.get('model')}")
    print(f"  Tipo activo:    {machinery.get('asset_type')}")
    print(f"  Grupo 1:        {machinery.get('asset_group_1')}")
    print(f"  Grupo 2:        {machinery.get('asset_group_2')}")
    print(f"  Activo:         {machinery.get('active')}")

    # --------------------------------------------------------
    # 2. Obtener token de Fracttal
    # --------------------------------------------------------

    print("\n2. Obteniendo token de Fracttal...")

    token = get_access_token()

    if not token:
        print("[ERROR] No se obtuvo token de Fracttal.")
        return

    print("[OK] Token obtenido.")

    # --------------------------------------------------------
    # 3. Buscar activo en Fracttal por serial
    # --------------------------------------------------------

    print("\n3. Buscando activo en Fracttal por serial...")

    equipment = get_equipment_by_serial(
        token=token,
        serial=machinery.get("serial"),
    )

    if equipment is None:
        print("[ERROR] No se encontró el activo en Fracttal.")
        return

    print("[OK] Activo encontrado en Fracttal.")

    print()
    print("Datos Fracttal:")
    print(f"  Código:         {equipment.get('code')}")
    print(f"  Nombre:         {equipment.get('field_1')}")
    print(f"  Fabricante:     {equipment.get('field_2')}")
    print(f"  Modelo:         {equipment.get('field_3')}")
    print(f"  Serial:         {equipment.get('field_4')}")

    # --------------------------------------------------------
    # 4. Validar coincidencia de serial
    # --------------------------------------------------------

    sql_serial = str(
        machinery.get("serial", "")
    ).strip().upper()

    fracttal_serial = str(
        equipment.get("field_4", "")
    ).strip().upper()

    print("\n4. Validación de serial:")

    print(f"  SQL Server:  {sql_serial}")
    print(f"  Fracttal:    {fracttal_serial}")

    if sql_serial == fracttal_serial:
        print("[OK] Serial SQL = Serial Fracttal.")
    else:
        print("[ERROR] El serial no coincide.")
        return

    # --------------------------------------------------------
    # 5. Buscar horómetro válido
    # --------------------------------------------------------

    print("\n5. Buscando horómetro válido en Fracttal...")

    meter = get_valid_hourmeter(
        token=token,
        equipment=equipment,
    )

    if meter is None:
        print("[ERROR] No se encontró un horómetro válido.")
        return

    print("[OK] Horómetro válido encontrado.")

    # --------------------------------------------------------
    # 6. Mostrar objeto COMPLETO del horómetro
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("OBJETO COMPLETO DEL HORÓMETRO")
    print("=" * 70)

    print(meter)

    print("=" * 70)

    # --------------------------------------------------------
    # 7. Mostrar campos conocidos
    # --------------------------------------------------------

    print("\nDatos del horómetro:")

    print(f"  ID:             {meter.get('id')}")
    print(f"  Descripción:    {meter.get('description')}")
    print(f"  Serial:         {meter.get('serial')}")
    print(f"  Unidad:         {meter.get('units_code')}")
    print(f"  Contador:       {meter.get('is_counter')}")
    print(f"  Valor (value):  {meter.get('value')}")

    # --------------------------------------------------------
    # 8. Validar serial del horómetro
    # --------------------------------------------------------

    meter_serial = str(
        meter.get("serial", "")
    ).strip().upper()

    equipment_serial = str(
        machinery.get("serial", "")
    ).strip().upper()

    print("\n8. Validación de serial del medidor:")

    print(f"  Serial activo:  {equipment_serial}")
    print(f"  Serial medidor: {meter_serial}")

    if meter_serial == equipment_serial:
        print("[OK] Serial del medidor coincide con el activo.")
    else:
        print("[ADVERTENCIA] Serial del medidor NO coincide con el activo.")

    # --------------------------------------------------------
    # 9. Fin
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("TEST FINALIZADO - SOLO LECTURA")
    print("=" * 70)


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()