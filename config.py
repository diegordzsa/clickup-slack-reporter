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

# Status que cuenta como "creativo entregado"
DELIVERED_STATUS = "REALIZADO"


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

    print("✅ Configuración cargada correctamente")
    print(f"   - Team ID: {CLICKUP_TEAM_ID}")
    print(f"   - Carpetas a monitorear: {len(FOLDERS)}")
    for name in FOLDERS:
        print(f"     • {name}")


if __name__ == "__main__":
    # Si corres este archivo directamente, ejecuta la validación
    validate_config()