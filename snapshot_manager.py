"""
Gestiona snapshots: los guarda, los carga, y los compara para detectar
transiciones de tareas entre categorias de status.

Logica del reporte:
- "Asignados" es un SNAPSHOT del estado actual (cuantas tareas estan AHORA en
  status "asignado" por editor).
- "En curso", "En revision", "Aprobados" y "Completados" son TRANSICIONES:
  tareas que cambiaron a esa categoria entre el snapshot anterior y el actual.
- Las tareas multi-asignadas se cuentan a CADA assignee (suman a todos).
- Las tareas SIN ASIGNAR se ignoran completamente.
"""
import json
import os
from datetime import datetime

from config import (
    categorize_status,
    is_completed_status,  # mantenido por compat hacia atras
    CATEGORY_ORDER,
)

# Donde se guarda el snapshot. Lo guardamos en el repo
# para que GitHub Actions pueda commitearlo y persistirlo.
SNAPSHOT_FILE = "data/last_snapshot.json"

# Marcador para tareas sin assignees
UNASSIGNED_MARKER = "SIN ASIGNAR"


def save_snapshot(snapshot):
    """Guarda un snapshot en disco como JSON."""
    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)

    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"Snapshot guardado en {SNAPSHOT_FILE}")


def load_previous_snapshot():
    """Carga el snapshot anterior. Si no existe, devuelve None."""
    if not os.path.exists(SNAPSHOT_FILE):
        return None

    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_assignee_list(task_data):
    """
    Devuelve la lista de assignees individuales de una task del snapshot.
    El snapshot guarda assignees como string separado por ", ".
    Tareas sin asignar devuelven lista vacia.
    """
    raw = task_data.get("assignee", "")
    if not raw or raw == UNASSIGNED_MARKER:
        return []

    names = [n.strip() for n in raw.split(",") if n.strip()]
    return [n for n in names if n != UNASSIGNED_MARKER]


def _task_to_dict(task_id, task_data, category):
    """
    Construye el dict de salida para una tarea, listo para usar en Slack.
    """
    return {
        "task_id":   task_id,
        "name":      task_data.get("name", "Sin nombre"),
        "client":    task_data.get("client", "?"),
        "list":      task_data.get("list", "?"),
        "status":    task_data.get("status", ""),
        "category":  category,
        "assignees": _get_assignee_list(task_data),
        "url":       task_data.get("url", ""),
    }


# ----------------------------------------------------------------------------
# DETECCION DE EVENTOS
# ----------------------------------------------------------------------------

def find_transitions(previous, current):
    """
    Detecta tareas que cambiaron de categoria entre dos snapshots.

    Una transicion cuenta cuando:
    - La tarea existia en el snapshot anterior (no es nueva)
    - La categoria nueva es distinta de la anterior
    - La categoria nueva es una de las 5 categorias trackeadas
    - La tarea tiene al menos un assignee

    Tareas que entran al sistema YA en una categoria (no estaban antes)
    se IGNORAN porque no podemos saber si "transitaron" o si fueron creadas asi.

    Returns:
        Dict {category: [task_dict, ...]}, una entrada por cada categoria del
        CATEGORY_ORDER. Las tareas vienen como dicts listos para Slack.
    """
    transitions = {cat: [] for cat in CATEGORY_ORDER}

    if previous is None:
        return transitions

    previous_tasks = previous.get("tasks", {})
    current_tasks = current.get("tasks", {})

    for task_id, current_data in current_tasks.items():
        # Necesitamos que la tarea existiera antes para saber si transito
        if task_id not in previous_tasks:
            continue

        previous_data = previous_tasks[task_id]

        old_category = categorize_status(previous_data.get("status", ""))
        new_category = categorize_status(current_data.get("status", ""))

        # Solo nos interesan transiciones REALES a una categoria trackeada
        if new_category is None:
            continue
        if new_category == old_category:
            continue

        # Sin assignees, se ignora
        assignees = _get_assignee_list(current_data)
        if not assignees:
            continue

        transitions[new_category].append(
            _task_to_dict(task_id, current_data, new_category)
        )

    return transitions


def find_current_assigned(current):
    """
    Devuelve la lista de tareas que actualmente estan en categoria 'asignado'
    (snapshot del estado actual, no transiciones).

    Se ignoran tareas sin assignees.
    """
    result = []
    if current is None:
        return result

    current_tasks = current.get("tasks", {})

    for task_id, task_data in current_tasks.items():
        category = categorize_status(task_data.get("status", ""))
        if category != "asignado":
            continue

        assignees = _get_assignee_list(task_data)
        if not assignees:
            continue

        result.append(_task_to_dict(task_id, task_data, "asignado"))

    return result


# ----------------------------------------------------------------------------
# AGRUPACION PARA EL REPORTE
# ----------------------------------------------------------------------------

def build_report(previous, current):
    """
    Construye la estructura completa del reporte: por cliente, por editor,
    con las 5 categorias.

    Returns:
        {
            "HAIR BIOLABS": {
                "Maria Garcia": {
                    "asignado":   [task, task, ...],   # snapshot actual
                    "en_curso":   [task, ...],         # transiciones 24h
                    "revision":   [task, ...],
                    "aprobado":   [task, ...],
                    "completado": [task, ...],
                },
                "Juan Perez": {...},
            },
            "SKIN+": {...},
        }

    Reglas:
    - Tareas multi-asignadas suman a CADA editor.
    - Tareas SIN ASIGNAR se ignoran.
    - "asignado" es snapshot; el resto son transiciones de las ultimas 24h.
    - Editores que aparezcan en CUALQUIER categoria se incluyen, aunque
      tengan 0 en otras (lista vacia).
    """
    transitions = find_transitions(previous, current)
    asignados_actuales = find_current_assigned(current)

    # Estructura: report[client][editor][category] = [tasks]
    report = {}

    def _ensure_editor(client, editor):
        if client not in report:
            report[client] = {}
        if editor not in report[client]:
            report[client][editor] = {cat: [] for cat in CATEGORY_ORDER}

    # 1. Snapshot de asignados actuales
    for task in asignados_actuales:
        client = task["client"]
        for editor in task["assignees"]:
            _ensure_editor(client, editor)
            report[client][editor]["asignado"].append(task)

    # 2. Transiciones (en_curso, revision, aprobado, completado)
    for category in CATEGORY_ORDER:
        if category == "asignado":
            continue
        for task in transitions.get(category, []):
            client = task["client"]
            for editor in task["assignees"]:
                _ensure_editor(client, editor)
                report[client][editor][category].append(task)

    # Ordenar editores por carga total (asignados + transiciones), descendente
    for client in report:
        sorted_editors = sorted(
            report[client].items(),
            key=lambda kv: (
                -sum(len(kv[1][cat]) for cat in CATEGORY_ORDER),
                kv[0].lower(),
            ),
        )
        report[client] = dict(sorted_editors)

    return report


def compute_totals(report):
    """
    Calcula totales agregados por categoria, sumando todos los clientes y
    editores. Ojo: como las multi-asignadas se cuentan por editor, este
    total puede ser mayor al numero unico de tareas. Es lo que queremos.
    """
    totals = {cat: 0 for cat in CATEGORY_ORDER}
    for client_data in report.values():
        for editor_data in client_data.values():
            for cat in CATEGORY_ORDER:
                totals[cat] += len(editor_data[cat])
    return totals


# ----------------------------------------------------------------------------
# COMPATIBILIDAD HACIA ATRAS
# ----------------------------------------------------------------------------
# Estas funciones se mantienen para no romper scripts viejos que las importen
# (test_report_preview.py, diagnose_statuses.py, etc.). Internamente delegan
# en la nueva logica.

def find_completed_tasks(previous, current):
    """
    DEPRECATED: usa find_transitions(previous, current)["completado"].
    Devuelve la lista de tareas completadas en formato viejo.
    """
    transitions = find_transitions(previous, current)
    completed = []
    for task in transitions["completado"]:
        completed.append({
            "task_id":    task["task_id"],
            "name":       task["name"],
            "client":     task["client"],
            "list":       task["list"],
            "old_status": "",  # ya no lo trackeamos en la nueva logica
            "new_status": task["status"],
            "assignees":  task["assignees"],
            "url":        task["url"],
        })
    return completed


def group_completed_by_client_and_editor(completed_tasks):
    """
    DEPRECATED: usa build_report(previous, current).
    Mantiene formato viejo: dict cliente -> editor -> lista de tareas.
    """
    grouped = {}
    for task in completed_tasks:
        client = task["client"]
        if client not in grouped:
            grouped[client] = {}
        for editor in task["assignees"]:
            if editor not in grouped[client]:
                grouped[client][editor] = []
            grouped[client][editor].append(task)

    for client in grouped:
        sorted_editors = sorted(
            grouped[client].items(),
            key=lambda kv: (-len(kv[1]), kv[0].lower()),
        )
        grouped[client] = dict(sorted_editors)

    return grouped


# ----------------------------------------------------------------------------
# Test rapido manual
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    from clickup_client import get_snapshot

    print("Tomando snapshot actual...")
    current = get_snapshot()
    print(f"   {len(current['tasks'])} tasks capturadas\n")

    print("Cargando snapshot anterior...")
    previous = load_previous_snapshot()

    if previous is None:
        print("   No hay snapshot anterior. Esta es la primera ejecucion.")
    else:
        print(f"   Snapshot anterior: {previous['timestamp']}\n")

        print("Construyendo reporte...")
        report = build_report(previous, current)
        totals = compute_totals(report)

        print(f"\nTotales: {totals}\n")
        for client, editors in report.items():
            print(f"[{client}]")
            for editor, cats in editors.items():
                counts = ", ".join(
                    f"{cat}={len(cats[cat])}" for cat in CATEGORY_ORDER
                )
                print(f"   {editor}: {counts}")

    print("\nGuardando snapshot actual...")
    save_snapshot(current)
    print("Listo")