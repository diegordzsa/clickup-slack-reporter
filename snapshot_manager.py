"""
Gestiona snapshots: los guarda, los carga, y compara dos para
detectar cambios de status entre ellos.
"""
import json
import os
from datetime import datetime

# Dónde se guarda el snapshot. Lo guardamos en el repo
# para que GitHub Actions pueda commitearlo y persistirlo.
SNAPSHOT_FILE = "data/last_snapshot.json"


def save_snapshot(snapshot):
    """Guarda un snapshot en disco como JSON."""
    # Crear carpeta data/ si no existe
    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)

    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"💾 Snapshot guardado en {SNAPSHOT_FILE}")


def load_previous_snapshot():
    """
    Carga el snapshot anterior. Si no existe (primera ejecución),
    devuelve None.
    """
    if not os.path.exists(SNAPSHOT_FILE):
        return None

    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_snapshots(previous, current):
    """
    Compara dos snapshots y devuelve:
    - Cambios de status en tasks existentes
    - Tasks nuevas creadas

    Returns:
        dict con dos listas:
        {
            "status_changes": [...],
            "new_tasks": [...]
        }
    """
    if previous is None:
        # Primera ejecución, no hay con qué comparar
        return {"status_changes": [], "new_tasks": []}

    status_changes = []
    new_tasks = []

    previous_tasks = previous.get("tasks", {})
    current_tasks = current.get("tasks", {})

    for task_id, current_data in current_tasks.items():
        if task_id in previous_tasks:
            # Task existía antes → ver si cambió de status
            previous_data = previous_tasks[task_id]

            if previous_data["status"] != current_data["status"]:
                status_changes.append({
                    "task_id": task_id,
                    "name": current_data["name"],
                    "client": current_data["client"],
                    "assignee": current_data["assignee"],
                    "old_status": previous_data["status"],
                    "new_status": current_data["status"],
                    "url": current_data.get("url", "")
                })
        else:
            # Task no existía antes → es nueva
            new_tasks.append({
                "task_id": task_id,
                "name": current_data["name"],
                "client": current_data["client"],
                "assignee": current_data["assignee"],
                "status": current_data["status"],
                "url": current_data.get("url", "")
            })

    return {
        "status_changes": status_changes,
        "new_tasks": new_tasks
    }


def group_changes_by_client_and_assignee(comparison_result):
    """
    Agrupa cambios y tasks nuevas por cliente y editor.

    Args:
        comparison_result: dict con "status_changes" y "new_tasks"

    Returns:
        {
            "HAIR BIOLABS": {
                "Alejandra Ramirez": {
                    "status_changes": [...],
                    "new_tasks": [...]
                },
                ...
            },
            ...
        }
    """
    grouped = {}

    # Procesar cambios de status
    for change in comparison_result["status_changes"]:
        client = change["client"]
        assignee = change["assignee"]

        if client not in grouped:
            grouped[client] = {}
        if assignee not in grouped[client]:
            grouped[client][assignee] = {"status_changes": [], "new_tasks": []}

        grouped[client][assignee]["status_changes"].append(change)

    # Procesar tasks nuevas
    for new_task in comparison_result["new_tasks"]:
        client = new_task["client"]
        assignee = new_task["assignee"]

        if client not in grouped:
            grouped[client] = {}
        if assignee not in grouped[client]:
            grouped[client][assignee] = {"status_changes": [], "new_tasks": []}

        grouped[client][assignee]["new_tasks"].append(new_task)

    return grouped

if __name__ == "__main__":
    from clickup_client import get_snapshot

    print("📸 Tomando snapshot actual...")
    current = get_snapshot()
    print(f"   {len(current['tasks'])} tasks capturadas\n")

    print("📂 Cargando snapshot anterior...")
    previous = load_previous_snapshot()

    if previous is None:
        print("   ⚠️ No hay snapshot anterior. Esta es la primera ejecución.")
        print("   El próximo run sí podrá comparar.\n")
    else:
        print(f"   Snapshot anterior es de: {previous['timestamp']}")
        print(f"   {len(previous['tasks'])} tasks en snapshot anterior\n")

        print("🔍 Comparando snapshots...")
        result = compare_snapshots(previous, current)
        n_changes = len(result["status_changes"])
        n_new = len(result["new_tasks"])
        print(f"   {n_changes} cambios de status detectados")
        print(f"   {n_new} tasks nuevas creadas\n")

        if n_changes > 0 or n_new > 0:
            grouped = group_changes_by_client_and_assignee(result)
            for client, editors in grouped.items():
                print(f"\n📁 {client}")
                for editor, activity in editors.items():
                    print(f"   👤 {editor}")

                    for ch in activity["status_changes"]:
                        print(f"      🔄 '{ch['name'][:50]}' → [{ch['old_status']}] a [{ch['new_status']}]")

                    for nt in activity["new_tasks"]:
                        print(f"      🆕 '{nt['name'][:50]}' → CREADA con status [{nt['status']}]")

    print("\n💾 Guardando snapshot actual como nuevo 'anterior'...")
    save_snapshot(current)
    print("✅ Listo")