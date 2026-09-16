from datetime import datetime, timezone

from mydevelon import (
    get_access_token as get_mydevelon_token,
    get_equipment_snapshot_xml,
    parse_equipment_snapshot_xml,
)

from database import get_machinery_by_serial

from api import (
    get_access_token as get_fracttal_token,
    get_equipment_by_serial,
    get_valid_hourmeter,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

MYDEVELON_MAKE = "DEVELON"
MYDEVELON_MODEL = "DX225LCA"
MYDEVELON_SERIAL = "CEBDX-001085"


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def parse_datetime(value):
    """
    Convierte una fecha ISO 8601 a datetime.

    Si no puede convertirla, devuelve None.
    """

    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (ValueError, TypeError):
        return None


def print_separator():
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print_separator()
    print("TEST MYDEVELON -> SQL SERVER -> FRACTTAL")
    print_separator()

    # ========================================================
    # 1. MYDEVELON
    # ========================================================

    print("\n1. MYDEVELON")
    print("-" * 70)

    print(f"OEM:       {MYDEVELON_MAKE}")
    print(f"Modelo:    {MYDEVELON_MODEL}")
    print(f"Serial:    {MYDEVELON_SERIAL}")

    print("\nObteniendo token de MyDevelon...")

    mydevelon_token = get_mydevelon_token()

    if not mydevelon_token:
        print("[ERROR] No se obtuvo token de MyDevelon.")
        return

    print("[OK] Token MyDevelon obtenido.")

    print("\nConsultando equipo...")

    xml_text = get_equipment_snapshot_xml(
        token=mydevelon_token,
        make_code=MYDEVELON_MAKE,
        model=MYDEVELON_MODEL,
        serial_number=MYDEVELON_SERIAL,
    )

    if not xml_text:
        print("[ERROR] MyDevelon no devolvió información.")
        return

    equipment_data = parse_equipment_snapshot_xml(xml_text)

    if not equipment_data:
        print("[ERROR] No fue posible interpretar la respuesta de MyDevelon.")
        return

    print("[OK] Equipo recibido desde MyDevelon.")

    print("\nDatos MyDevelon:")
    print(f"  OEM:                    {equipment_data.get('oem_name')}")
    print(f"  Modelo:                 {equipment_data.get('model')}")
    print(f"  Equipment ID:           {equipment_data.get('equipment_id')}")
    print(f"  SerialNumber:            {equipment_data.get('serial_number')}")
    print(f"  PIN:                     {equipment_data.get('pin')}")
    print(f"  Horómetro:              {equipment_data.get('operating_hours')}")
    print(f"  Fecha horómetro:        {equipment_data.get('operating_hours_datetime')}")
    print(f"  Hora consulta:          {equipment_data.get('retrieved_at')}")

    pin = str(
        equipment_data.get("pin", "")
    ).strip().upper()

    source_hours = equipment_data.get("operating_hours")

    source_datetime = equipment_data.get(
        "operating_hours_datetime"
    )

    if not pin:
        print("\n[ERROR] MyDevelon no entregó PIN.")
        return

    if source_hours is None:
        print("\n[ERROR] MyDevelon no entregó horómetro.")
        return

    print("\n[OK] PIN obtenido.")
    print(f"    PIN = {pin}")

    # ========================================================
    # 2. SQL SERVER
    # ========================================================

    print("\n2. SQL SERVER")
    print("-" * 70)

    print("Buscando activo mediante PIN/serial...")

    machinery = get_machinery_by_serial(pin)

    if machinery is None:
        print(
            "[ERROR] El PIN de MyDevelon no existe "
            "como serial en SQL Server."
        )
        print(f"        PIN buscado: {pin}")
        return

    print("[OK] Activo encontrado en SQL Server.")

    print("\nDatos SQL:")
    print(f"  ID:             {machinery.get('id')}")
    print(f"  Código:         {machinery.get('equipment_code')}")
    print(f"  Serial:         {machinery.get('serial')}")
    print(f"  Nombre:         {machinery.get('name')}")
    print(f"  Fabricante:     {machinery.get('manufacturer')}")
    print(f"  Modelo:         {machinery.get('model')}")
    print(f"  Tipo activo:    {machinery.get('asset_type')}")
    print(f"  Activo:         {machinery.get('active')}")

    sql_serial = str(
        machinery.get("serial", "")
    ).strip().upper()

    if sql_serial != pin:
        print("\n[ERROR] El serial SQL no coincide con el PIN MyDevelon.")
        return

    print("\n[OK] PIN MyDevelon = serial SQL.")

    # ========================================================
    # 3. FRACTTAL - ACTIVO
    # ========================================================

    print("\n3. FRACTTAL")
    print("-" * 70)

    print("Obteniendo token de Fracttal...")

    fracttal_token = get_fracttal_token()

    if not fracttal_token:
        print("[ERROR] No se obtuvo token de Fracttal.")
        return

    print("[OK] Token Fracttal obtenido.")

    print("\nBuscando activo en Fracttal por serial...")

    equipment = get_equipment_by_serial(
        token=fracttal_token,
        serial=sql_serial,
    )

    if equipment is None:
        print("[ERROR] Activo no encontrado en Fracttal.")
        return

    print("[OK] Activo encontrado en Fracttal.")

    print("\nDatos Fracttal:")
    print(f"  Código:         {equipment.get('code')}")
    print(f"  Nombre:         {equipment.get('field_1')}")
    print(f"  Fabricante:     {equipment.get('field_2')}")
    print(f"  Modelo:         {equipment.get('field_3')}")
    print(f"  Serial:         {equipment.get('field_4')}")

    fracttal_serial = str(
        equipment.get("field_4", "")
    ).strip().upper()

    if fracttal_serial != sql_serial:
        print("\n[ERROR] Serial SQL != serial Fracttal.")
        return

    print("\n[OK] Serial SQL = serial Fracttal.")

    # ========================================================
    # 4. FRACTTAL - HORÓMETRO
    # ========================================================

    print("\n4. HORÓMETRO FRACTTAL")
    print("-" * 70)

    print("Buscando horómetro válido...")

    meter = get_valid_hourmeter(
        token=fracttal_token,
        equipment=equipment,
    )

    if meter is None:
        print("[ERROR] No se encontró un horómetro válido.")
        return

    print("[OK] Horómetro válido encontrado.")

    meter_id = meter.get("id")

    meter_serial = str(
        meter.get("serial", "")
    ).strip().upper()

    meter_description = meter.get("description")
    meter_units = meter.get("units_code")
    meter_counter = meter.get("is_counter")

    last_data = meter.get("last_data") or {}

    last_fracttal_date = last_data.get("date")
    last_fracttal_value = last_data.get("value")
    fracttal_hours = last_fracttal_value

    print("\nDatos del horómetro:")
    print(f"  ID:                  {meter_id}")
    print(f"  Descripción:         {meter_description}")
    print(f"  Serial:              {meter_serial}")
    print(f"  Unidad:              {meter_units}")
    print(f"  Contador:            {meter_counter}")
    print(f"  Counter value:       {fracttal_hours}")
    print(f"  Último valor:        {last_fracttal_value}")
    print(f"  Fecha último dato:   {last_fracttal_date}")

    if meter_units != "HRS":
        print("\n[ERROR] El medidor no está expresado en HRS.")
        return

    if meter_counter is not True:
        print("\n[ERROR] El medidor no está configurado como contador.")
        return

    if meter_serial and meter_serial != sql_serial:
        print("\n[ERROR] Serial del medidor != serial del activo.")
        return

    if fracttal_hours is None:
        print("\n[ERROR] Fracttal no entregó last_data.value.")
        return

    # ========================================================
    # 5. COMPARACIÓN
    # ========================================================

    print("\n5. COMPARACIÓN")
    print("-" * 70)

    print(f"Fuente MyDevelon:      {source_hours:.2f} h")
    print(f"Fracttal actual:       {float(fracttal_hours):.2f} h")

    difference = float(source_hours) - float(fracttal_hours)

    print(f"Diferencia:            {difference:+.2f} h")

    # ========================================================
    # 6. REGLA DE NEGOCIO
    # ========================================================

    print("\n6. DECISIÓN")
    print("-" * 70)

    if source_hours > fracttal_hours:

        print("[UPDATE]")
        print(
            "El horómetro de MyDevelon es MAYOR "
            "que el de Fracttal."
        )
        print(
            f"Fracttal debería pasar de "
            f"{float(fracttal_hours):.2f} h "
            f"a {float(source_hours):.2f} h."
        )

    elif source_hours == fracttal_hours:

        print("[SKIP]")
        print(
            "El horómetro de MyDevelon es igual "
            "al de Fracttal."
        )
        print("No sería necesario actualizar.")

    else:

        print("[REJECT]")
        print(
            "El horómetro de MyDevelon es MENOR "
            "que el de Fracttal."
        )
        print(
            "No se debe actualizar Fracttal."
        )

    # ========================================================
    # 7. VALIDACIÓN DE FECHAS
    # ========================================================

    print("\n7. FECHAS")
    print("-" * 70)

    source_dt = parse_datetime(source_datetime)
    fracttal_dt = parse_datetime(last_fracttal_date)

    print(f"Fecha lectura MyDevelon: {source_datetime}")
    print(f"Fecha último Fracttal:   {last_fracttal_date}")

    if source_dt and fracttal_dt:

        if source_dt > fracttal_dt:
            print(
                "[OK] El dato de MyDevelon es más reciente "
                "que el último dato de Fracttal."
            )

        elif source_dt == fracttal_dt:
            print(
                "[INFO] Ambos datos tienen la misma fecha."
            )

        else:
            print(
                "[ADVERTENCIA] El dato de MyDevelon es "
                "más antiguo que el último dato de Fracttal."
            )

    # ========================================================
    # 8. RESUMEN
    # ========================================================

    print("\n")
    print_separator()
    print("RESUMEN DE INTEGRACIÓN")
    print_separator()

    print(f"Activo:                 {machinery.get('equipment_code')}")
    print(f"Serial:                 {sql_serial}")
    print(f"Fuente:                 MyDevelon")
    print(f"Horómetro fuente:       {float(source_hours):.2f} h")
    print(f"Horómetro Fracttal:     {float(fracttal_hours):.2f} h")
    print(f"Diferencia:             {difference:+.2f} h")

    if source_hours > fracttal_hours:
        print("Acción propuesta:       UPDATE")
    elif source_hours == fracttal_hours:
        print("Acción propuesta:       SKIP")
    else:
        print("Acción propuesta:       REJECT")

    print()
    print("[IMPORTANTE] Este test NO modifica Fracttal.")
    print("[OK] Ejecución finalizada.")

    print_separator()


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()