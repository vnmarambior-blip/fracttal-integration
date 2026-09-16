import requests

from api import get_access_token


# ============================================================
# CONFIGURACIÓN
# ============================================================

EQUIPMENT_URL = "https://app.fracttal.com/api/items/"


# ============================================================
# OBTENER TODOS LOS EQUIPOS
# ============================================================

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
            f"→ HTTP {response.status_code}"
        )

        response.raise_for_status()

        data = response.json()

        items = data.get(
            "data",
            []
        )

        all_items.extend(items)

        total = data.get(
            "total",
            0
        )

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


# ============================================================
# ANALIZAR CLASIFICACIONES
# ============================================================

def analizar_clasificaciones(items):

    print()
    print("=" * 70)
    print("CLASIFICACIONES EXISTENTES EN FRACTTAL")
    print("=" * 70)

    fields = [
        "items_types_description",
        "groups_description",
        "groups_1_description",
        "groups_2_description",
    ]

    for field in fields:

        values = set()

        for item in items:

            value = item.get(field)

            if value is not None:

                value = str(value).strip()

                if value:
                    values.add(value)

        print()
        print("-" * 70)
        print(f"{field}")
        print("-" * 70)

        if not values:

            print("SIN DATOS")

        else:

            for value in sorted(values):

                print(
                    f"- {value}"
                )

            print(
                f"\nTOTAL VALORES ÚNICOS: "
                f"{len(values)}"
            )


# ============================================================
# ANALIZAR COMBINACIONES
# ============================================================

def analizar_combinaciones(items):

    combinations = set()

    for item in items:

        combination = (
            item.get(
                "items_types_description"
            ),
            item.get(
                "groups_description"
            ),
            item.get(
                "groups_1_description"
            ),
            item.get(
                "groups_2_description"
            ),
        )

        combinations.add(
            combination
        )

    print()
    print("=" * 70)
    print("COMBINACIONES DE CLASIFICACIÓN")
    print("=" * 70)

    for combination in sorted(
        combinations,
        key=lambda x: (
            str(x[0]),
            str(x[1]),
            str(x[2]),
            str(x[3]),
        )
    ):

        print()
        print(
            f"Tipo:       {combination[0]}"
        )

        print(
            f"Grupo:      {combination[1]}"
        )

        print(
            f"Grupo 1:    {combination[2]}"
        )

        print(
            f"Grupo 2:    {combination[3]}"
        )

    print()
    print(
        f"TOTAL COMBINACIONES: "
        f"{len(combinations)}"
    )


# ============================================================
# EJEMPLOS
# ============================================================

def mostrar_ejemplos(items):

    print()
    print("=" * 70)
    print("EJEMPLOS DE ACTIVOS")
    print("=" * 70)

    for item in items[:20]:

        print()
        print(
            f"Código:       {item.get('code')}"
        )

        print(
            f"Descripción:  {item.get('description')}"
        )

        print(
            f"Tipo:         "
            f"{item.get('items_types_description')}"
        )

        print(
            f"Grupo:        "
            f"{item.get('groups_description')}"
        )

        print(
            f"Grupo 1:      "
            f"{item.get('groups_1_description')}"
        )

        print(
            f"Grupo 2:      "
            f"{item.get('groups_2_description')}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("ANÁLISIS DE CLASIFICACIÓN — FRACTTAL")
    print("=" * 70)

    print()
    print("Obteniendo token...")

    token = get_access_token()

    print("[OK] Token obtenido.")

    print()
    print("Obteniendo todos los activos...")

    items = get_all_items(
        token
    )

    print()
    print(
        f"[OK] Activos obtenidos: "
        f"{len(items)}"
    )

    analizar_clasificaciones(
        items
    )

    analizar_combinaciones(
        items
    )

    mostrar_ejemplos(
        items
    )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()