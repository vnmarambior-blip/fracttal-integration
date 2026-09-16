from database import initialize_database, get_machinery_by_serial


def main():

    print("=" * 60)
    print("PRUEBA DE CLASIFICACIÓN FRACTTAL → SQL")
    print("=" * 60)

    initialize_database()

    serial = "DHKCEBDXCK0001085"

    machinery = get_machinery_by_serial(serial)

    if machinery is None:
        print()
        print("[ERROR] La maquinaria no existe en SQL Server.")
        return

    print()
    print("[OK] Maquinaria encontrada en SQL Server")
    print()

    print(f"ID:              {machinery['id']}")
    print(f"Serial:          {machinery['serial']}")
    print(f"Código:          {machinery['equipment_code']}")
    print(f"Nombre:          {machinery['name']}")
    print(f"Fabricante:      {machinery['manufacturer']}")
    print(f"Modelo:          {machinery['model']}")
    print(f"Tipo:            {machinery['asset_type']}")
    print(f"Grupo 1:         {machinery['asset_group_1']}")
    print(f"Grupo 2:         {machinery['asset_group_2']}")
    print(f"Activo:          {machinery['active']}")

    print()
    print("=" * 60)

    if machinery["asset_type"] == "EXCAVADORA":
        print("[OK] CLASIFICACIÓN CORRECTA")
    else:
        print(
            "[ERROR] Clasificación incorrecta: "
            f"{machinery['asset_type']}"
        )


if __name__ == "__main__":
    main()