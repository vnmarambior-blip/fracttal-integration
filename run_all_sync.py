#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ejecuta MyDevelon + Komtrax -> Fracttal en un solo comando.

Default SEGURO: DRY-RUN con fixtures (cero PUTs).
Produccion solo con --live explicito.

Uso:
  python run_all_sync.py                                  # DRY-RUN (fixtures)
  python run_all_sync.py --live                           # PRODUCCION (ambos en vivo)
  python run_all_sync.py --live --report ejecucion.md     # + reporte consolidado
  python run_all_sync.py --dry-run                        # DRY-RUN explicito
  python run_all_sync.py --md-fleet-xml F --kt-fleet-xml K  # fixtures por fuente
"""

import sys
import subprocess
import os
from datetime import datetime, timezone


def run_sync(script_name, args, description, env=None):
    """Ejecuta un worker capturando stdout. Retorna (ok, output)."""
    cmd = [sys.executable, script_name] + args
    header = (
        "\n" + "=" * 60 + "\n"
        + ">> " + description + "\n"
        + "=" * 60 + "\n"
        + "Comando: " + " ".join(cmd) + "\n"
    )
    print(header)

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    try:
        result = subprocess.run(
            cmd, check=False, text=True, capture_output=True,
            env=merged_env,
        )
        output = header + (result.stdout or "") + (result.stderr or "")
        print(result.stdout or "", end="")
        if result.stderr:
            print(result.stderr, end="")
        if result.returncode == 0:
            print("\n[OK] " + description + " completado")
            return True, output
        print("\n[ERROR] " + description + " FALLO (exit code "
              + str(result.returncode) + ")")
        return False, output
    except subprocess.CalledProcessError as error:
        output = header + (error.stdout or "") + (error.stderr or "")
        print("\n[ERROR] " + description + " FALLO (exit code "
              + str(error.returncode) + ")")
        return False, output
    except OSError as error:
        output = header + f"[ERROR] no se pudo ejecutar: {error}\n"
        print(output, end="")
        return False, output


def split_orchestrator_args(argv):
    """Separa args del orquestador de los args de cada worker.

    El orquestador consume: --live, --dry-run, --report <path>,
    --md-fleet-xml <path>, --kt-fleet-xml <path>.
    MyDevelon recibe: --live (+ --fleet-xml si --md-fleet-xml).
    Komtrax recibe: --live (+ --fleet-xml si --kt-fleet-xml).
    --report NUNCA va a los workers: el reporte consolidado
    lo escribe el orquestador.
    """

    live = "--live" in argv
    dry_run = "--dry-run" in argv
    report = None
    md_fixture = None
    kt_fixture = None

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--report" and index + 1 < len(argv):
            report = argv[index + 1]
            index += 2
        elif arg == "--md-fleet-xml" and index + 1 < len(argv):
            md_fixture = argv[index + 1]
            index += 2
        elif arg == "--kt-fleet-xml" and index + 1 < len(argv):
            kt_fixture = argv[index + 1]
            index += 2
        else:
            index += 1

    md_args = []
    kt_args = []
    if live:
        md_args.append("--live")
        kt_args.append("--live")
    if md_fixture is not None:
        md_args += ["--fleet-xml", md_fixture]
    if kt_fixture is not None:
        kt_args += ["--fleet-xml", kt_fixture]

    return {
        "live": live,
        "dry_run": dry_run,
        "report": report,
        "md_args": md_args,
        "kt_args": kt_args,
    }


def write_consolidated_report(path, md_output, kt_output,
                               ok_md, ok_kt, exit_code, mode):
    """Escribe el unico reporte consolidado del orquestador."""

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Sincronizacion MyDevelon + Komtrax -> Fracttal\n")
        handle.write(f"\nFecha (UTC): {started}\n")
        handle.write(f"Modo: {mode}\n")
        handle.write(f"Resultado: {'OK' if exit_code == 0 else 'PARCIAL' if exit_code == 3 else 'FALLIDO'}\n")
        handle.write(f"MyDevelon: {'OK' if ok_md else 'FALLO'}\n")
        handle.write(f"Komtrax: {'OK' if ok_kt else 'FALLO'}\n")
        handle.write("\n## MyDevelon -> Fracttal\n\n```\n")
        handle.write(md_output or "(sin salida)")
        handle.write("\n```\n\n## Komtrax -> Fracttal\n\n```\n")
        handle.write(kt_output or "(sin salida)")
        handle.write("\n```\n")

    print(f"\nReporte consolidado: {path}")


def main(argv=None):
    parsed = split_orchestrator_args(list(argv) if argv is not None else sys.argv[1:])

    # Default SEGURO: DRY-RUN salvo --live explicito.
    live = parsed["live"] and not parsed["dry_run"]
    mode = "PRODUCCION (--live)" if live else "DRY-RUN (fixtures)"

    env = os.environ.copy()
    env["SYNC_DRY_RUN"] = "false" if live else "true"

    print("INICIANDO SINCRONIZACION COMPLETA MyDevelon + Komtrax")
    print("Modo: " + mode)
    print("MyDevelon args: " + str(parsed["md_args"]))
    print("Komtrax args: " + str(parsed["kt_args"]))

    # 1. MyDevelon primero
    ok_md, md_output = run_sync(
        "run_mydevelon_sync.py",
        parsed["md_args"],
        "MyDevelon -> Fracttal",
        env=env,
    )

    # 2. Komtrax segundo (siempre, aunque MyDevelon falle)
    ok_kt, kt_output = run_sync(
        "run_komtrax_sync.py",
        parsed["kt_args"],
        "Komtrax -> Fracttal",
        env=env,
    )

    print("\n" + "=" * 60)
    if ok_md and ok_kt:
        print("SINCRONIZACION COMPLETA FINALIZADA")
        print("=" * 60)
        exit_code = 0
    elif not ok_md and not ok_kt:
        print("SINCRONIZACION COMPLETA FALLIDA (ambas fuentes)")
        print("=" * 60)
        exit_code = 1
    else:
        print("SINCRONIZACION PARCIAL (una fuente fallo)")
        print("=" * 60)
        exit_code = 3

    if parsed["report"]:
        write_consolidated_report(
            parsed["report"], md_output, kt_output,
            ok_md, ok_kt, exit_code, mode,
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
