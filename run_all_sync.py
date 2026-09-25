#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ejecuta MyDevelon + Komtrax -> Fracttal en un solo comando (PRODUCCIÓN por defecto).

Orden: MyDevelon primero (cuota 15 min), luego Komtrax (cuota 5 min/URL).
Por defecto: PRODUCCIÓN (--live, SYNC_DRY_RUN=false).
Usa --dry-run para simulación.

Uso:
  python run_all_sync.py                 # PRODUCCIÓN: MyDevelon live + Komtrax live
  python run_all_sync.py --dry-run       # Simulación: MyDevelon fixture + Komtrax fixture
  python run_all_sync.py --report ejecucion.md  # con reporte
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
    # Argumentos pasados al script
    extra_args = sys.argv[1:]

    # POR DEFECTO: PRODUCCIÓN (--live). Solo dry-run si se pasa --dry-run explícito
    is_dry_run = "--dry-run" in extra_args
    if is_dry_run:
        extra_args = [a for a in extra_args if a != "--dry-run"]
    else:
        # Forzar --live si no está explícito
        if "--live" not in extra_args:
            extra_args = ["--live"] + extra_args

    # Entorno: producción por defecto
    env = os.environ.copy()
    if is_dry_run:
        env["SYNC_DRY_RUN"] = "true"
    else:
        env["SYNC_DRY_RUN"] = "false"

    print("INICIANDO SINCRONIZACION COMPLETA MyDevelon + Komtrax")
    print("Modo: " + ("DRY-RUN (simulacion)" if is_dry_run else "PRODUCCION (--live, SYNC_DRY_RUN=false)"))
    print("Argumentos: " + str(extra_args))

    # 1. MyDevelon primero
    ok_md, _ = run_sync(
        "run_mydevelon_sync.py",
        extra_args,
        "MyDevelon -> Fracttal",
        env=env
    )

    # 2. Komtrax segundo (siempre, aunque MyDevelon falle)
    ok_kt, _ = run_sync(
        "run_komtrax_sync.py",
        extra_args,
        "Komtrax -> Fracttal",
        env=env
    )

    print("\n" + "=" * 60)
    if ok_md and ok_kt:
        print("SINCRONIZACION COMPLETA FINALIZADA")
        print("=" * 60)
        return 0
    if not ok_md and not ok_kt:
        print("SINCRONIZACION COMPLETA FALLIDA (ambas fuentes)")
        print("=" * 60)
        return 1
    print("SINCRONIZACION PARCIAL (una fuente fallo)")
    print("=" * 60)
    return 3


if __name__ == "__main__":
    sys.exit(main())