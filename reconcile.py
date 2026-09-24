"""R0: reconciliación de intenciones huérfanas INTENT_RECORDED.

Solo lectura + cierre con evidencia sobre la MISMA fila.
Prohibido en este path: PUT (insert_meter_reading), filas nuevas
(save_horometer_update) y reintento automático.
"""

from api import get_current_hourmeter, get_equipment_by_serial
from api import normalize_comparison_value
from api import insert_meter_reading  # noqa: F401 (prohibido; testeable)
from database import get_machinery_by_id
from database import list_horometer_write_intents
from database import save_horometer_update  # noqa: F401 (prohibido; testeable)
from database import update_horometer_write_result


def _close(intent_id, status, write_status, error_code, message,
           dry_run, verification_value=None, verification_status=None):
    """Registra el cierre (o lo reporta en dry-run)."""

    if dry_run:
        return {
            "id": intent_id,
            "status": status,
            "write_status": write_status,
            "error_code": error_code,
            "written": False,
        }

    update_horometer_write_result(
        intent_id,
        status=status,
        write_status=write_status,
        error_code=error_code,
        message=message,
        verification_value=verification_value,
        verification_status=verification_status,
    )

    return {
        "id": intent_id,
        "status": status,
        "write_status": write_status,
        "error_code": error_code,
        "written": True,
    }


def _reconcile_one(token, intent, dry_run):
    """Verifica una huérfana contra Fracttal y la cierra con evidencia."""

    intent_id = intent["id"]

    machinery = get_machinery_by_id(intent["machinery_id"])

    if machinery is None:
        return _close(
            intent_id, "ERROR", "ERROR", "MACHINERY_NOT_FOUND",
            "Reconciliación: maquinaria SQL inexistente.",
            dry_run,
        )

    serial = str(machinery.get("serial", "")).strip().upper()

    if not serial:
        return _close(
            intent_id, "ERROR", "ERROR", "MACHINERY_NOT_FOUND",
            "Reconciliación: maquinaria sin serial.",
            dry_run,
        )

    equipment = get_equipment_by_serial(token, serial)

    if equipment is None:
        return _close(
            intent_id, "ERROR", "ERROR", "EQUIPMENT_NOT_FOUND",
            f"Reconciliación: {serial} inexistente en Fracttal.",
            dry_run,
        )

    try:
        current = get_current_hourmeter(token, equipment)
    except Exception as error:
        return _close(
            intent_id, "WRITE_AMBIGUOUS", "WRITE_AMBIGUOUS",
            "VERIFICATION_ERROR",
            f"Reconciliación: GET de verificación falló: {error}.",
            dry_run,
        )

    if current is None:
        return _close(
            intent_id, "ERROR", "ERROR", "NO_VALID_METER",
            "Reconciliación: sin horómetro inequívoco en Fracttal.",
            dry_run,
        )

    meter = current.get("meter") or {}

    expected_meter_id = str(intent["meter_id"]).strip()
    observed_meter_id = str(meter.get("id")).strip()

    if observed_meter_id != expected_meter_id:
        return _close(
            intent_id, "ERROR", "ERROR", "METER_MISMATCH",
            "Reconciliación: el meter consultado no corresponde "
            "a la intención.",
            dry_run,
        )

    expected = normalize_comparison_value(intent["new_value"])
    previous = normalize_comparison_value(intent["old_value"])
    observed = normalize_comparison_value(current.get("value"))

    if observed is None or expected is None:
        return _close(
            intent_id, "WRITE_AMBIGUOUS", "WRITE_AMBIGUOUS",
            "UNVERIFIABLE_VALUE",
            "Reconciliación: valor no numérico, sin evidencia.",
            dry_run,
        )

    if observed == expected:
        return _close(
            intent_id, "VERIFIED", "VERIFIED", None,
            "Reconciliación: Fracttal contiene el valor intentado.",
            dry_run,
            verification_value=observed,
            verification_status="PASS",
        )

    if previous is not None and observed == previous:
        return _close(
            intent_id, "ERROR", "ERROR", "RECONCILIATION_NOT_APPLIED",
            "Reconciliación: Fracttal conserva el valor anterior; "
            "el PUT no se aplicó. Sin reintento automático.",
            dry_run,
        )

    return _close(
        intent_id, "WRITE_AMBIGUOUS", "WRITE_AMBIGUOUS",
        "UNATTRIBUTED_VALUE",
        "Reconciliación: Fracttal tiene un tercer valor no atribuible.",
        dry_run,
    )


def reconcile_orphan_intents(token, dry_run=False):
    """Cierra huérfanas INTENT_RECORDED con evidencia. Sin PUT ni INSERT."""

    intents = list_horometer_write_intents("INTENT_RECORDED")

    summary = {"VERIFIED": 0, "WRITE_AMBIGUOUS": 0, "ERROR": 0}
    items = []

    for intent in intents:
        result = _reconcile_one(token, intent, dry_run)
        summary[result["write_status"]] += 1
        items.append(result)

    summary["items"] = items

    return summary


if __name__ == "__main__":
    raise SystemExit(
        "Uso controlado: importar reconcile_orphan_intents; "
        "no ejecutar reconciliación real sin autorización."
    )
