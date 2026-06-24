"""
Carga y valida las variables de entorno del proyecto.
Define el sistema de categorias de status y helpers para clasificar.
Si falta alguna variable critica, falla inmediatamente con un error claro.
"""
import os
import re
import unicodedata
from dotenv import load_dotenv

# Carga las variables del archivo .env al entorno del sistema
load_dotenv()

# Variables de ClickUp
CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
CLICKUP_TEAM_ID = os.getenv("CLICKUP_TEAM_ID")

# Carpetas a monitorear (cliente -> folder_id)
FOLDERS = {
    "HAIR BIOLABS": os.getenv("CLICKUP_FOLDER_ID_HAIRBIOLABS"),
    "SKIN+":        os.getenv("CLICKUP_FOLDER_ID_SKINPLUS"),
}

# Slack
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# ---------------------------------------------------------------------------
# Sistema de categorias de status
# ---------------------------------------------------------------------------
# Cobertura de los 6 mapeos enviados:
# - HAIR BIOLABS / Diseno Grafico:   ASIGNADO, EN PROGRESO, COMPLETADO
# - HAIR BIOLABS / Produccion:       ASSIGNED, EN CURSO, REVISION, APROBADO, FINAL
# - SKIN+ / Produccion (SKIN):       ASSIGNED, EN CURSO, REVISION, APPROVED, FINAL
# - SKIN+ / Diseno Grafico:          ASIGNADO, EN CURSO, REVISION, APROBADO, FINALES
# - SKIN+ / Tareas:                  ASIGNADO, REVISAR, HECHO
STATUS_CATEGORIES = {
    "asignado":   ["asignado", "assigned"],
    "en_curso":   ["en progreso", "en curso"],
    "revision":   ["revision", "revisar"],
    "aprobado":   ["aprobado", "approved"],
    "completado": ["completado", "final", "finales", "hecho", "complete"],
}

# Status que ignoramos completamente (no entran en ninguna metrica)
IGNORED_STATUSES = ["to do", "draft", "borrador", "pendiente", "archivado", "leer", "testado"]

# Orden en que aparecen las categorias en el reporte
CATEGORY_ORDER = ["asignado", "en_curso", "revision", "aprobado", "completado"]

# Labels visibles en el reporte de Slack
CATEGORY_LABELS = {
    "asignado":   "Asignados",
    "en_curso":   "En curso hoy",
    "revision":   "En revision hoy",
    "aprobado":   "Aprobados hoy",
    "completado": "Completados hoy",
}

# Emojis por categoria (formato Slack :name:)
CATEGORY_EMOJIS = {
    "asignado":   ":pushpin:",
    "en_curso":   ":arrows_counterclockwise:",
    "revision":   ":eyes:",
    "aprobado":   ":white_check_mark:",
    "completado": ":checkered_flag:",
}

# Semaforo de productividad semanal (completados + aprobados)
SEMAFORO_THRESHOLDS = {"green": 9, "yellow": 4, "red": 1}
SEMAFORO_EMOJIS = {
    "green":  ":large_green_circle:",
    "yellow": ":large_yellow_circle:",
    "red":    ":red_circle:",
    "none":   ":white_circle:",
}


def get_semaforo(count):
    if count >= SEMAFORO_THRESHOLDS["green"]:
        return SEMAFORO_EMOJIS["green"]
    elif count >= SEMAFORO_THRESHOLDS["yellow"]:
        return SEMAFORO_EMOJIS["yellow"]
    elif count >= SEMAFORO_THRESHOLDS["red"]:
        return SEMAFORO_EMOJIS["red"]
    return SEMAFORO_EMOJIS["none"]


# Compatibilidad hacia atras: scripts viejos siguen importando esto.
COMPLETED_STATUSES = set(STATUS_CATEGORIES["completado"])


def _normalize(text):
    """Normaliza texto para matching: lowercase, sin acentos, sin espacios extra."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return no_accents.strip().lower()


def normalize_editor(name):
    """
    Normaliza el nombre de un editor para que variantes de capitalizacion
    cuenten como la misma persona en agregaciones.

    Casos reales detectados en data:
      - "MIchel Isla Gordillo"   <-> "Michel Isla Gordillo"
      - "  Alejandra  Ramirez "  <-> "Alejandra Ramirez"

    Estrategia:
      1. Strip de espacios.
      2. Colapsar espacios multiples a uno solo.
      3. Title case por palabra (respetando acentos).
      4. Conserva el nombre de display (no lowercase) para que se vea bien.

    Devuelve string vacio si entra vacio o None.
    """
    if not name:
        return ""

    cleaned = re.sub(r"\s+", " ", name).strip()
    if not cleaned:
        return ""

    # Title case sensible a unicode (str.title() rompe con apostrofes y acentos
    # en algunos casos, pero para nombres latinos basicos funciona bien).
    return " ".join(word.capitalize() for word in cleaned.split(" "))


def categorize_status(status_name):
    """
    Devuelve la categoria a la que pertenece un status, o None si esta
    en ignorados o no matchea ninguna categoria conocida.
    Case-insensitive y tolerante a acentos.

    Ejemplos:
        categorize_status("REVISION")  -> "revision"
        categorize_status("APROBADO")  -> "aprobado"
        categorize_status("Approved")  -> "aprobado"
        categorize_status("DRAFT")     -> None (ignorado)
        categorize_status("xyz")       -> None (no matchea)
    """
    if not status_name:
        return None

    normalized = _normalize(status_name)

    if normalized in IGNORED_STATUSES:
        return None

    for category, status_list in STATUS_CATEGORIES.items():
        if normalized in [_normalize(s) for s in status_list]:
            return category

    return None


def is_completed_status(status):
    """
    Mantiene compatibilidad: True si el status cuenta como 'completado'.
    Ahora se basa en el sistema de categorias.
    """
    return categorize_status(status) == "completado"


def validate_config():
    """Verifica que todas las variables criticas esten presentes."""
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
    print(f"  - Team ID: {CLICKUP_TEAM_ID}")
    print(f"  - Carpetas a monitorear: {len(FOLDERS)}")
    for name in FOLDERS:
        print(f"    - {name}")
    print(f"  - Categorias de status: {list(STATUS_CATEGORIES.keys())}")


if __name__ == "__main__":
    validate_config()

    # Smoke tests del categorizador
    print("\nSmoke tests categorize_status:")
    test_cases = [
        ("ASIGNADO",     "asignado"),
        ("Assigned",     "asignado"),
        ("EN PROGRESO",  "en_curso"),
        ("EN CURSO",     "en_curso"),
        ("REVISION",     "revision"),
        ("REVISAR",      "revision"),
        ("APROBADO",     "aprobado"),
        ("APPROVED",     "aprobado"),
        ("COMPLETADO",   "completado"),
        ("FINAL",        "completado"),
        ("FINALES",      "completado"),
        ("HECHO",        "completado"),
        ("complete",     "completado"),
        ("DRAFT",        None),
        ("BORRADOR",     None),
        ("TO DO",        None),
        ("PENDIENTE",    None),
        ("ARCHIVADO",    None),
        ("TESTADO",      None),
        ("xyz random",   None),
        ("",             None),
        (None,           None),
    ]
    failures = 0
    for status, expected in test_cases:
        got = categorize_status(status)
        ok = "OK " if got == expected else "FAIL"
        if got != expected:
            failures += 1
        print(f"  {ok}  categorize_status({status!r:20}) -> {got!r:14} (esperado {expected!r})")
    print(f"\n{len(test_cases) - failures}/{len(test_cases)} pasaron")

    # Smoke tests de normalize_editor
    print("\nSmoke tests normalize_editor:")
    name_cases = [
        ("MIchel Isla Gordillo",   "Michel Isla Gordillo"),
        ("michel isla gordillo",   "Michel Isla Gordillo"),
        ("  Alejandra  Ramirez ",  "Alejandra Ramirez"),
        ("ALEJANDRA RAMIREZ",      "Alejandra Ramirez"),
        ("Gonzalo Millán",         "Gonzalo Millán"),
        ("",                       ""),
        (None,                     ""),
    ]
    for inp, expected in name_cases:
        got = normalize_editor(inp)
        ok = "OK " if got == expected else "FAIL"
        print(f"  {ok}  normalize_editor({inp!r:30}) -> {got!r}")
