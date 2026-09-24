from api import get_access_token, get_equipment_by_serial


SERIALS = [
    "DHKCEBADJK0008232",
    "DHKCEBEFEN0001189",
    "DHKCEWCKAR5001236",
    "DHKCEWCKLR5001237",
]


token = get_access_token()

print("=" * 80)
print("VERIFICACION MYDEVELON -> FRACTTAL")
print("=" * 80)

for serial in SERIALS:

    print(f"\nMyDevelon PIN: {serial}")
    print("-" * 80)

    equipment = get_equipment_by_serial(token, serial)

    if not equipment:
        print("[NO ENCONTRADO] No existe ese serial en Fracttal.")
        continue

    print("[OK] Encontrado en Fracttal")
    print(f"  ID:          {equipment.get('id')}")
    print(f"  Codigo:      {equipment.get('code')}")
    print(f"  Nombre:      {equipment.get('field_1')}")
    print(f"  Fabricante:  {equipment.get('field_2')}")
    print(f"  Modelo:      {equipment.get('field_3')}")
    print(f"  Serial:      {equipment.get('field_4')}")

print("\n" + "=" * 80)