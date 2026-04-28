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

    ClickUp paginará los resultados (máximo 100 por página),
    así que hay que iterar hasta que no haya más páginas.

    Args:
        folder_id: ID de la carpeta a consultar
        include_closed: Si True, incluye tasks cerradas (necesario para ver "REALIZADO")

    Returns:
        Lista de tasks (cada una es un dict con todos los datos)
    """
    all_tasks = []
    page = 0

    while True:
        # Endpoint: trae tasks de todas las lists dentro de la carpeta
        url = f"{BASE_URL}/folder/{folder_id}/list"

        # Primero necesitamos las lists dentro de la carpeta
        response = requests.get(url, headers=HEADERS)

        if response.status_code != 200:
            raise Exception(
                f"Error al obtener lists de la carpeta {folder_id}: "
                f"{response.status_code} - {response.text}"
            )

        lists = response.json().get("lists", [])

        # Para cada list dentro de la carpeta, traer sus tasks
        for lst in lists:
            list_id = lst["id"]
            list_name = lst["name"]
            tasks = get_tasks_from_list(list_id, include_closed)

            # Agregamos el nombre de la list a cada task para tener contexto
            for task in tasks:
                task["_list_name"] = list_name

            all_tasks.extend(tasks)

        # En este endpoint no hay paginación a nivel de carpeta
        # (la paginación está en el get_tasks_from_list)
        break

    return all_tasks


def get_tasks_from_list(list_id, include_closed=True):
    """
    Trae todas las tasks de una list específica, manejando paginación.

    Args:
        list_id: ID de la list
        include_closed: Si incluir tasks cerradas

    Returns:
        Lista de tasks
    """
    all_tasks = []
    page = 0

    while True:
        url = f"{BASE_URL}/list/{list_id}/task"
        params = {
            "page": page,
            "include_closed": str(include_closed).lower(),
            "subtasks": "true",  # incluir subtasks también
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
            # No hay más tasks, salimos del loop
            break

        all_tasks.extend(tasks)

        # ClickUp devuelve "last_page": true cuando ya no hay más
        if data.get("last_page", False):
            break

        page += 1

    return all_tasks


def test_connection():
    """
    Función de prueba: trae tasks de la primera carpeta configurada
    y muestra info básica para verificar que todo funciona.
    """
    print("🔌 Probando conexión con ClickUp...\n")

    for client_name, folder_id in FOLDERS.items():
        print(f"📁 Carpeta: {client_name} (ID: {folder_id})")

        try:
            tasks = get_tasks_from_folder(folder_id)
            print(f"   ✅ {len(tasks)} tasks encontradas\n")

            # Mostrar las primeras 3 tasks como muestra
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
                    print()

        except Exception as e:
            print(f"   ❌ Error: {e}\n")

def get_snapshot():
    """
    Toma un snapshot del estado actual de todas las tasks en todas las carpetas.

    Returns un dict con esta estructura:
    {
        "timestamp": "2026-04-28T06:00:00",
        "tasks": {
            "task_id_1": {
                "name": "Nombre de la task",
                "status": "completado",
                "assignee": "Alejandra Ramirez",
                "client": "HAIR BIOLABS",
                "list": "Diseño Gráfico"
            },
            ...
        }
    }

    Cada task se identifica por su ID único de ClickUp, lo cual permite
    comparar snapshots y detectar exactamente qué cambió.
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

            # Si tiene varios assignees, los juntamos en un string
            # Si no tiene, marcamos como SIN ASIGNAR
            if assignees:
                assignee_names = ", ".join([a.get("username", "?") for a in assignees])
            else:
                assignee_names = "SIN ASIGNAR"

            snapshot["tasks"][task_id] = {
                "name": task.get("name", "Sin nombre"),
                "status": task.get("status", {}).get("status", "sin_status"),
                "assignee": assignee_names,
                "client": client_name,
                "list": task.get("_list_name", "?"),
                "url": task.get("url", "")
            }

    return snapshot

if __name__ == "__main__":
    test_connection()
    print("\n" + "=" * 60)
    print("📸 Probando snapshot...")
    snapshot = get_snapshot()
    print(f"   Snapshot tomado: {snapshot['timestamp']}")
    print(f"   Total tasks capturadas: {len(snapshot['tasks'])}")