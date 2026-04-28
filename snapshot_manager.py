"""
Gestiona snapshots: los guarda, los carga, y compara dos para detectar
tareas que fueron COMPLETADAS entre snapshots.

Logica del reporte:
- Solo cuentan tareas que pasaron de un status NO completado a un status
  completado (definidos en config.COMPLETED_STATUSES).
- Las tareas multi-asignadas se cuentan a CADA assignee (suman a todos).
- Las tareas SIN ASIGNAR se ignoran completamente.
"""
import json
import os
from datetime import datetime

from config import is_completed_status

# Donde se guarda el snapshot. Lo guardamos en el repo
# para que GitHub Actions pueda commitearlo y persistirlo.
SNAPSHOT_FILE = "data/last_snapshot.json"

# Marcador para tareas sin assignees (mantiene compatibilidad con snapshots viejos)
UNASSIGNED_MARKER = "SIN ASIGNAR"


def save_snapshot(snapshot):
    """Guarda un snapshot en disco como JSON."""
    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)

    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"Snapshot guardado en {SNAPSHOT_FILE}")


def load_previous_snapshot():
    """
    Carga el snapshot anterior. Si no existe (primera ejecucion),
    devuelve None.
    """
    if not os.path.exists(SNAPSHOT_FILE):
        return None

    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_assignee_list(task_data):
    """
    Devuelve la lista de assignees individuales de una task del snapshot.
    El snapshot guarda assignees como string separado por ", " (formato viejo).
    Esta funcion los separa en lista limpia.

    Tareas sin asignar devuelven lista vacia.
    """
    raw = task_data.get("assignee", "")
    if not raw or raw == UNASSIGNED_MARKER:
        return []

    # Separar por coma y limpiar espacios
    names = [n.strip() for n in raw.split(",") if n.strip()]
    # Filtrar marcador por si quedo mezclado
    return [n for n in names if n != UNASSIGNED_MARKER]


def find_completed_tasks(previous, current):
    """
    Encuentra todas las tareas que pasaron de un status NO completado
    a un status completado entre los dos snapshots.

    Args:
        previous: snapshot anterior (dict)
        current: snapshot actual (dict)

    Returns:
        Lista de dicts, una por tarea completada:
        [
            {
                "task_id": "...",
                "name": "...",
                "client": "HAIR BIOLABS",
                "list": "Diseño Gráfico",
                "old_status": "en progreso",
                "new_status": "completado",
                "assignees": ["Juan Perez", "Maria Lopez"],  # lista, no string
                "url": "..."
            },
            ...
        ]

    Tareas SIN ASIGNAR son ignoradas (no aparecen en el resultado).
    """
    if previous is None:
        return []

    completed = []
    previous_tasks = previous.get("tasks", {})
    current_tasks = current.get("tasks", {})

    for task_id, current_data in current_tasks.items():
        current_status = current_data.get("status", "")

        # Solo nos interesan tareas que AHORA estan en status completado
        if not is_completed_status(current_status):
            continue

        # Si la tarea no existia antes, no podemos saber si "paso a completada"
        # (puede haber sido creada ya completada). La ignoramos.
        if task_id not in previous_tasks:
            continue

        previous_status = previous_tasks[task_id].get("status", "")

        # Si ya estaba completada antes, no es una "completada hoy"
        if is_completed_status(previous_status):
            continue

        # Aqui ya sabemos que paso de NO completado -> completado
        assignees = _get_assignee_list(current_data)

        # Ignorar tareas sin asignar
        if not assignees:
            continue

        completed.append({
            "task_id": task_id,
            "name": current_data.get("name", "Sin nombre"),
            "client": current_data.get("client", "?"),
            "list": current_data.get("list", "?"),
            "old_status": previous_status,
            "new_status": current_status,
            "assignees": assignees,
            "url": current_data.get("url", ""),
        })

    return completed


def group_completed_by_client_and_editor(completed_tasks):
    """
    Agrupa las tareas completadas por cliente, y dentro de cada cliente,
    por editor. Como una tarea puede tener varios assignees, aparece
    repetida bajo cada editor que la tenia asignada.

    Args:
        completed_tasks: lista devuelta por find_completed_tasks()

    Returns:
        {
            "HAIR BIOLABS": {
                "Alejandra Ramirez": [
                    {"name": "...", "list": "...", "url": "...", ...},
                    ...
                ],
                "Juan Perez": [...],
            },
            "SKIN+": {
                ...
            }
        }

    Editores ordenados (dentro de cada cliente) por cantidad de tareas
    completadas (mayor a menor). Clientes en el orden en que aparecen.
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

    # Ordenar editores por cantidad de tareas (descendente) dentro de cada cliente
    for client in grouped:
        sorted_editors = sorted(
            grouped[client].items(),
            key=lambda kv: (-len(kv[1]), kv[0].lower())
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
        print("   El proximo run podra comparar.\n")
    else:
        print(f"   Snapshot anterior: {previous['timestamp']}")
        print(f"   {len(previous['tasks'])} tasks en snapshot anterior\n")

        print("Buscando tareas completadas...")
        completed = find_completed_tasks(previous, current)
        print(f"   {len(completed)} tareas completadas detectadas\n")

        if completed:
            grouped = group_completed_by_client_and_editor(completed)
            for client, editors in grouped.items():
                print(f"\n[{client}]")
                for editor, tasks in editors.items():
                    print(f"   {editor} - {len(tasks)} tareas")
                    for t in tasks:
                        print(f"      - {t['name']} ({t['list']})")

    print("\nGuardando snapshot actual...")
    save_snapshot(current)
    print("Listo")