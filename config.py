"""
Carga y valida las variables de entorno del proyecto.
Si falta alguna variable crítica, falla inmediatamente con un error claro.
"""
import os
from dotenv import load_dotenv

# Carga las variables del archivo .env al entorno del sistema
load_dotenv()

# Variables de ClickUp
CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
CLICKUP_TEAM_ID = os.getenv("CLICKUP_TEAM_ID")

# Carpetas a monitorear (cliente -> folder_id)
# Si en el futuro agregan más clientes, solo añade aquí
FOLDERS = {
    "HAIR BIOLABS": os.getenv("CLICKUP_FOLDER_ID_HAIRBIOLABS"),
    "SKIN+": os.getenv("CLICKUP_FOLDER_ID_SKINPLUS"),
}

# Slack
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Status que cuentan como "tarea completada".
# La comparacion se hace en minusculas, asi que aqui van todos los posibles
# valores que ClickUp devuelve cuando una tarea esta hecha (en cualquier
# lista de cualquier carpeta).
#
# Si en el futuro agregan un nuevo status que cuenta como completado,
# solo añadelo aqui en minusculas.
COMPLETED_STATUSES = {
    "completado",   # HAIR BIOLABS / Diseño Gráfico
    "aprobado",     # HAIR BIOLABS / Producción + SKIN+ / Diseño Gráfico
    "final",        # HAIR BIOLABS / Producción + SKIN+ / Producción
    "approved",     # SKIN+ / Producción
    "finales",      # SKIN+ / Diseño Gráfico
    "hecho",        # SKIN+ / Tareas
}


def is_completed_status(status):
    """Devuelve True si el status (case-insensitive) cuenta como completado."""
    if not status:
        return False
    return status.strip().lower() in COMPLETED_STATUSES


def validate_config():
    """
    Verifica que todas las variables críticas estén presentes.
    Lanza un error claro si falta alguna.
    """
    missing = []

    if not CLICKUP_TOKEN:
        missing.append("CLICKUP_TOKEN")
    if not CLICKUP_TEAM_ID:
        missing.append("CLICKUP_TEAM_ID")
    if not SLACK_WEBHOOK_URL:
        missing.append("SLACK_WEBHOOK_URL")

    for client_name, folder_id in FOLDERS.items():
        if not folder_id:
            missing.append(f"CLICKUP_FOLDER_ID para {client_name}")

    if missing:
        raise EnvironmentError(
            f"Faltan las siguientes variables en .env: {', '.join(missing)}"
        )

    print("Configuracion cargada correctamente")
    print(f"   - Team ID: {CLICKUP_TEAM_ID}")
    print(f"   - Carpetas a monitorear: {len(FOLDERS)}")
    for name in FOLDERS:
        print(f"     - {name}")
    print(f"   - Status completados reconocidos: {sorted(COMPLETED_STATUSES)}")


if __name__ == "__main__":
    validate_config()