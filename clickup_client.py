"""
Cliente para interactuar con la API de ClickUp.
Documentación oficial: https://clickup.com/api
"""
import requests
from config import CLICKUP_TOKEN, FOLDERS

# URL base de la API de ClickUp v2
BASE_URL = "https://api.clickup.com/api/v2"

# Headers de autenticación que se mandan en cada request
HEADERS = {
    "Authorization": CLICKUP_TOKEN,
    "Content-Type": "application/json"
}


def get_tasks_from_folder(folder_id, include_closed=True):
    """
    Trae todas las tasks de una carpeta específica de ClickUp.
    """
    all_tasks = []

    url = f"{BASE_URL}/folder/{folder_id}/list"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        raise Exception(
            f"Error al obtener lists de la carpeta {folder_id}: "
            f"{response.status_code} - {response.text}"
        )

    lists = response.json().get("lists", [])

    for lst in lists:
        list_id = lst["id"]
        list_name = lst["name"]
        tasks = get_tasks_from_list(list_id, include_closed)
        for task in tasks:
            task["_list_name"] = list_name
        all_tasks.extend(tasks)

    return all_tasks


def get_tasks_from_list(list_id, include_closed=True):
    """Trae todas las tasks de una list, manejando paginación."""
    all_tasks = []
    page = 0

    while True:
        url = f"{BASE_URL}/list/{list_id}/task"
        params = {
            "page": page,
            "include_closed": str(include_closed).lower(),
            "subtasks": "true",
        }

        response = requests.get(url, headers=HEADERS, params=params)

        if response.status_code != 200:
            raise Exception(
                f"Error al obtener tasks de list {list_id}: "
                f"{response.status_code} - {response.text}"
            )

        data = response.json()
        tasks = data.get("tasks", [])

        if not tasks:
            break

        all_tasks.extend(tasks)

        if data.get("last_page", False):
            break

        page += 1

    return all_tasks


def _ms_to_iso(ms_value):
    """
    ClickUp devuelve fechas como strings de timestamp en milisegundos UTC
    (ej: "1714214400000"). Las convertimos a ISO 8601 UTC.
    Si viene None, vacio, o no convertible, devolvemos None.
    """
    if not ms_value:
        return None
    try:
        from datetime import datetime, timezone
        ms = int(ms_value)
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def test_connection():
    """Función de prueba: trae tasks de la primera carpeta y muestra info."""
    print("🔌 Probando conexión con ClickUp...\n")

    for client_name, folder_id in FOLDERS.items():
        print(f"📁 Carpeta: {client_name} (ID: {folder_id})")

        try:
            tasks = get_tasks_from_folder(folder_id)
            print(f"   ✅ {len(tasks)} tasks encontradas\n")

            if tasks:
                print(f"   Muestra (primeras 3 tasks):")
                for task in tasks[:3]:
                    name = task.get("name", "Sin nombre")
                    status = task.get("status", {}).get("status", "Sin status")
                    assignees = task.get("assignees", [])
                    assignee_names = [a.get("username", "?") for a in assignees]
                    list_name = task.get("_list_name", "?")

                    print(f"   • [{status}] {name}")
                    print(f"     List: {list_name}")
                    print(f"     Assignees: {', '.join(assignee_names) if assignee_names else 'Sin asignar'}")
                    print(f"     date_created: {_ms_to_iso(task.get('date_created'))}")
                    print(f"     date_done:    {_ms_to_iso(task.get('date_done'))}")
                    print()

        except Exception as e:
            print(f"   ❌ Error: {e}\n")


def get_snapshot():
    """
    Toma un snapshot del estado actual de todas las tasks en todas las carpetas.

    NUEVO en v2: incluye fechas (date_created, date_updated, date_done) para
    poder calcular tiempo medio de entrega en el dashboard.

    Returns:
    {
        "timestamp": "2026-05-08T07:00:00",
        "tasks": {
            "task_id_1": {
                "name": "Nombre",
                "status": "completado",
                "assignee": "Alejandra Ramirez",
                "client": "HAIR BIOLABS",
                "list": "Diseño Gráfico",
                "url": "https://...",
                "date_created": "2026-04-15T10:30:00+00:00",
                "date_updated": "2026-05-01T14:20:00+00:00",
                "date_done":    "2026-05-01T14:20:00+00:00"
            },
            ...
        }
    }
    """
    from datetime import datetime

    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "tasks": {}
    }

    for client_name, folder_id in FOLDERS.items():
        tasks = get_tasks_from_folder(folder_id)

        for task in tasks:
            task_id = task["id"]
            assignees = task.get("assignees", [])

            if assignees:
                assignee_names = ", ".join([a.get("username", "?") for a in assignees])
            else:
                assignee_names = "SIN ASIGNAR"

            snapshot["tasks"][task_id] = {
                "name":         task.get("name", "Sin nombre"),
                "status":       task.get("status", {}).get("status", "sin_status"),
                "assignee":     assignee_names,
                "client":       client_name,
                "list":         task.get("_list_name", "?"),
                "url":          task.get("url", ""),
                "date_created": _ms_to_iso(task.get("date_created")),
                "date_updated": _ms_to_iso(task.get("date_updated")),
                "date_done":    _ms_to_iso(task.get("date_done")),
            }

    return snapshot


if __name__ == "__main__":
    test_connection()
    print("\n" + "=" * 60)
    print("📸 Probando snapshot...")
    snapshot = get_snapshot()
    print(f"   Snapshot tomado: {snapshot['timestamp']}")
    print(f"   Total tasks capturadas: {len(snapshot['tasks'])}")

    # Estadistica rapida de fechas capturadas
    with_done = sum(1 for t in snapshot['tasks'].values() if t.get('date_done'))
    with_created = sum(1 for t in snapshot['tasks'].values() if t.get('date_created'))
    print(f"   Con date_created: {with_created}")
    print(f"   Con date_done:    {with_done}")
