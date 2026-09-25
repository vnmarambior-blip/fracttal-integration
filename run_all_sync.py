#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ejecuta MyDevelon + Komtrax -> Fracttal en un solo comando.

Orden: MyDevelon primero (cuota 15 min), luego Komtrax (cuota 5 min/URL).
Respeta SYNC_DRY_RUN del entorno.

Uso:
  python run_all_sync.py                 # dry-run MyDevelon (fixture) + Komtrax (requiere --live o --fleet-xml)
  python run_all_sync.py --live          # ambos en vivo
  python run_all_sync.py --live --report ejecucion.md  # con reporte
"""

import sys
import subprocess
import os


def run_sync(script_name, args, description, env=None):
    """Ejecuta un script de sincronizacion y retorna (ok, output)."""
    cmd = [sys.executable, script_name] + args
    print("\n" + "=" * 60)
    print(">> " + description)
    print("=" * 60)
    print("Comando: " + " ".join(cmd))
    print()

    # Merge environment
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    try:
        result = subprocess.run(cmd, check=True, text=True, capture_output=False, env=merged_env)
        print("\n[OK] " + description + " completado")
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        print("\n[ERROR] " + description + " FALLO (exit code " + str(e.returncode) + ")")
        return False, e.stdout


def main():
    # Argumentos pasados al script (--live, --report, etc.)
    extra_args = sys.argv[1:]

    print("INICIANDO SINCRONIZACION COMPLETA MyDevelon + Komtrax")
    print("Argumentos: " + (str(extra_args) if extra_args else "(default dry-run)"))

    # 1. MyDevelon primero (usa fixture por defecto si no hay --live)
    ok_md, _ = run_sync(
        "run_mydevelon_sync.py",
        extra_args,
        "MyDevelon -> Fracttal"
    )

    if not ok_md:
        print("\nMyDevelon fallo. Abortando Komtrax.")
        sys.exit(1)

    # 2. Komtrax segundo (requiere --live o --fleet-xml; en dry-run usa fixture por defecto)
    # Si no hay --live ni --fleet-xml, pasar la fixture por defecto para Komtrax
    komtrax_args = list(extra_args)
    if "--live" not in komtrax_args and "--fleet-xml" not in komtrax_args:
        # Usar la fixture por defecto si existe
        if os.path.exists("fixtures/komtrax_fleet.xml"):
            komtrax_args.extend(["--fleet-xml", "fixtures/komtrax_fleet.xml"])
        else:
            print("\n[AVISO] Komtrax dry-run requiere --live o --fleet-xml. Saltando Komtrax.")
            print("Usa: python run_all_sync.py --live  (para ambos en vivo)")
            print("   o: python run_all_sync.py --fleet-xml fixtures/komtrax_fleet.xml")
            print("\nSolo MyDevelon completado.")
            sys.exit(0)

    ok_kt, _ = run_sync(
        "run_komtrax_sync.py",
        komtrax_args,
        "Komtrax -> Fracttal"
    )

    if not ok_kt:
        print("\nKomtrax fallo.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("SINCRONIZACION COMPLETA FINALIZADA")
    print("=" * 60)


if __name__ == "__main__":
    main()