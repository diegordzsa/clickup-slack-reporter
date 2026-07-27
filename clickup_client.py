"""
Cliente para interactuar con la API de ClickUp.
Documentación oficial: https://clickup.com/api
"""
import time

import requests
from config import (
    CLICKUP_TOKEN,
    CLICKUP_TEAM_ID,
    FOLDERS,
    get_active_folders,
    is_excluded_list,
)

# URL base de la API de ClickUp v2
BASE_URL = "https://api.clickup.com/api/v2"

# Headers de autenticación que se mandan en cada request
HEADERS = {
    "Authorization": CLICKUP_TOKEN,
    "Content-Type": "application/json"
}

# Reintentos ante errores transitorios (rate limit y caidas de ClickUp)
MAX_RETRIES = 4
RETRY_STATUSES = {429, 500, 502, 503, 504}


class TokenInvalidError(Exception):
    """El token de ClickUp es invalido o expiro (401). No se reintenta."""


def request_with_retry(url, params=None, timeout=30):
    """
    GET a la API de ClickUp con reintentos ante errores transitorios.

    - 401  -> TokenInvalidError inmediato (reintentar no sirve de nada).
    - 429 / 5xx -> backoff exponencial (2s, 4s, 8s...).
    - Errores de red -> mismo backoff.

    Este wrapper existe porque el sistema estuvo 18 dias fallando en silencio
    por un token vencido: ahora el motivo sale explicito en el log.
    """
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        except requests.RequestException as e:
            last_error = f"error de red: {e}"
        else:
            if response.status_code == 200:
                return response.json()

            if response.status_code == 401:
                raise TokenInvalidError(
                    "El token de ClickUp es invalido o expiro (401). "
                    "Generalo de nuevo en ClickUp (Settings > Apps > API Token) "
                    "y actualiza el secret CLICKUP_TOKEN en GitHub."
                )

            if response.status_code not in RETRY_STATUSES:
                raise Exception(
                    f"Error {response.status_code} en {url}: {response.text[:200]}"
                )

            last_error = f"HTTP {response.status_code}: {response.text[:120]}"

        if attempt < MAX_RETRIES - 1:
            wait = 2 ** (attempt + 1)
            print(f"   Reintento {attempt + 1}/{MAX_RETRIES - 1} en {wait}s ({last_error})")
            time.sleep(wait)

    raise Exception(f"Fallo tras {MAX_RETRIES} intentos en {url}: {last_error}")


def check_token():
    """
    Verifica que el token sirva ANTES de intentar bajar nada.
    Falla rapido y con un mensaje que se entiende.
    """
    request_with_retry(f"{BASE_URL}/team/{CLICKUP_TEAM_ID}/space",
                       params={"archived": "false"})
    return True


def get_tasks_from_folder(folder_id, include_closed=True):
    """
    Trae todas las tasks de una carpeta específica de ClickUp.
    """
    all_tasks = []

    data = request_with_retry(f"{BASE_URL}/folder/{folder_id}/list")
    lists = data.get("lists", [])

    for lst in lists:
        list_id = lst["id"]
        list_name = lst["name"]

        # Las listas excluidas (ej: "Ideas creativas") no entran a metricas
        if is_excluded_list(list_name):
            continue

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
        data = request_with_retry(
            f"{BASE_URL}/list/{list_id}/task",
            params={
                "page": page,
                "include_closed": str(include_closed).lower(),
                "subtasks": "true",
            },
        )

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

    activas, _ = get_active_folders()

    for client_name, folder_id in activas.items():
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
