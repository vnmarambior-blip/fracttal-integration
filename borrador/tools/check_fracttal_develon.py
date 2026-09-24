import requests

from api import get_access_token


EQUIPMENT_URL = "https://app.fracttal.com/api/items/"


SERIALS = [
    "DHKCEBADJK0008232",
    "DHKCEBEFEN0001189",
    "DHKCEWCKAR5001236",
    "DHKCEWCKLR5001237",
]


def get_all_items(token):

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    all_items = []

    start = 0
    limit = 100

    while True:

        params = {
            "item_type": 2,
            "limit": limit,
            "start": start,
        }

        response = requests.get(
            EQUIPMENT_URL,
            headers=headers,
            params=params,
            timeout=30,
        )

        print(
            f"Consultando start={start} "
            f"limit={limit} "
            f"-> HTTP {response.status_code}"
        )

        response.raise_for_status()

        data = response.json()

        items = data.get("data", [])

        all_items.extend(items)

        total = data.get("total", 0)

        print(
            f"   Recibidos: {len(items)} | "
            f"Acumulados: {len(all_items)} | "
            f"Total Fracttal: {total}"
        )

        if len(all_items) >= total:
            break

        if not items:
            break

        start += limit

    return all_items


def buscar_seriales(items):

    print()
    print("=" * 80)
    print("VERIFICACION MYDEVELON -> FRACTTAL")
    print("=" * 80)

    for serial in SERIALS:

        print()
        print(f"MyDevelon PIN: {serial}")
        print("-" * 80)

        encontrados = []

        for item in items:

            fracttal_serial = item.get("field_4")

            if fracttal_serial:
                fracttal_serial = str(fracttal_serial).strip()

            if fracttal_serial == serial:
                encontrados.append(item)

        if not encontrados:

            print("[NO ENCONTRADO]")
            print("El serial no existe en Fracttal.")

            continue

        if len(encontrados) > 1:

            print(
                f"[ADVERTENCIA] "
                f"Se encontraron {len(encontrados)} activos con el mismo serial."
            )

        for item in encontrados:

            print("[OK] Encontrado en Fracttal")

            print(f"  ID:           {item.get('id')}")
            print(f"  Codigo:       {item.get('code')}")
            print(f"  Nombre:       {item.get('field_1')}")
            print(f"  Fabricante:   {item.get('field_2')}")
            print(f"  Modelo:       {item.get('field_3')}")
            print(f"  Serial:       {item.get('field_4')}")

            print()
            print("  Clasificacion:")
            print(
                f"    Tipo:       "
                f"{item.get('items_types_description')}"
            )
            print(
                f"    Grupo:      "
                f"{item.get('groups_description')}"
            )
            print(
                f"    Grupo 1:    "
                f"{item.get('groups_1_description')}"
            )
            print(
                f"    Grupo 2:    "
                f"{item.get('groups_2_description')}"
            )


def main():

    print("=" * 80)
    print("CHECK DE ACTIVOS DEVELON EN FRACTTAL")
    print("=" * 80)

    print()
    print("Obteniendo token...")

    token = get_access_token()

    print("[OK] Token obtenido.")

    print()
    print("Obteniendo equipos de Fracttal...")

    items = get_all_items(token)

    print()
    print(f"[OK] Equipos obtenidos: {len(items)}")

    buscar_seriales(items)


if __name__ == "__main__":
    main()