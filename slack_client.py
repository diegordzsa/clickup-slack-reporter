"""
Cliente para mandar mensajes a Slack via Incoming Webhook.
Usa Block Kit para que el mensaje se vea profesional y estructurado.
Documentacion de Block Kit: https://api.slack.com/block-kit
"""
import requests
from datetime import datetime

from config import (
    SLACK_WEBHOOK_URL,
    CATEGORY_ORDER,
    CATEGORY_LABELS,
    CATEGORY_EMOJIS,
)

# Emojis por cliente para el header de cada seccion
CLIENT_EMOJIS = {
    "HAIR BIOLABS": ":lotion_bottle:",
    "SKIN+":        ":sparkles:",
}

# Truncar listas largas: si una categoria tiene mas de esto, mostramos solo
# las primeras N y agregamos "... y X mas".
MAX_TASKS_PER_CATEGORY = 5

# Limites duros de Slack
MAX_BLOCKS_PER_MESSAGE = 50
MAX_CHARS_PER_SECTION = 2900  # margen sobre el limite real de 3000


def send_to_slack(blocks, fallback_text="Reporte diario de actividad"):
    """Manda un mensaje a Slack usando blocks (Block Kit)."""
    payload = {
        "text": fallback_text,
        "blocks": blocks,
    }

    response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=15)

    if response.status_code != 200:
        raise Exception(
            f"Error al enviar a Slack: {response.status_code} - {response.text}"
        )

    print("Mensaje enviado a Slack correctamente")


def _format_today_es():
    """Devuelve la fecha de hoy en formato '28 abril 2026'."""
    today = datetime.now().strftime("%d %B %Y")
    months_es = {
        "January": "enero", "February": "febrero", "March": "marzo",
        "April":   "abril",  "May":      "mayo",    "June":  "junio",
        "July":    "julio",  "August":   "agosto",  "September": "septiembre",
        "October": "octubre", "November": "noviembre", "December": "diciembre",
    }
    for en, es in months_es.items():
        today = today.replace(en, es)
    return today


def _format_task_line(task):
    """Formatea una tarea como bullet point con link clickeable y nombre de lista."""
    name = task.get("name", "Sin nombre")
    url = task.get("url", "")
    list_name = task.get("list", "")

    name_part = f"<{url}|{name}>" if url else name
    list_part = f" _({list_name})_" if list_name else ""

    return f"   - {name_part}{list_part}"


def _build_editor_section(editor, categories):
    """
    Construye el texto de la seccion de un editor con sus categorias NO vacias.
    Las categorias con 0 tareas se omiten completamente.
    Si el editor no tiene NADA en ninguna categoria, devuelve None
    (el caller debe omitir al editor del reporte).
    """
    # Si todas las categorias estan vacias, este editor no se reporta
    if all(len(categories.get(cat, [])) == 0 for cat in CATEGORY_ORDER):
        return None

    lines = [f"*:bust_in_silhouette: {editor}*"]

    for cat in CATEGORY_ORDER:
        tasks = categories.get(cat, [])
        count = len(tasks)

        # Skipear categorias vacias completamente
        if count == 0:
            continue

        emoji = CATEGORY_EMOJIS[cat]
        label = CATEGORY_LABELS[cat]

        # Linea de encabezado de categoria
        lines.append(f"\n{emoji} *{label}: {count}*")

        # Truncar si hay mas de MAX_TASKS_PER_CATEGORY
        tasks_to_show = tasks[:MAX_TASKS_PER_CATEGORY]
        for task in tasks_to_show:
            lines.append(_format_task_line(task))

        if count > MAX_TASKS_PER_CATEGORY:
            remaining = count - MAX_TASKS_PER_CATEGORY
            lines.append(f"   _... y {remaining} mas_")

    text = "\n".join(lines)

    # Slack limita 3000 chars por section, truncamos defensivamente
    if len(text) > MAX_CHARS_PER_SECTION:
        text = text[:MAX_CHARS_PER_SECTION] + "\n_...(seccion truncada por limite de Slack)_"

    return text


def build_daily_report_blocks(report, totals):
    """
    Construye los blocks de Slack para el reporte diario.

    Estructura del mensaje:
        Reporte diario - 28 abril 2026

        :lotion_bottle: HAIR BIOLABS
        ─────────────
        :bust_in_silhouette: Maria Garcia
        :pushpin: Asignados: 5
           - <url|Tarea 1> (Lista X)
           - <url|Tarea 2> (Lista Y)
           ...
        :arrows_counterclockwise: En curso hoy: 2
           - <url|Tarea A> (Lista X)
        :eyes: En revision hoy: 1
           - <url|Tarea B> (Lista Y)
        :white_check_mark: Aprobados hoy: 3
           - <url|Tarea C> (Lista X)
        :checkered_flag: Completados hoy: 2
           - <url|Tarea D> (Lista Y)

        :sparkles: SKIN+
        ... (igual)

        ─────────────
        Total: X asignados, Y en curso, Z en revision, W aprobados, V completados

    Args:
        report: dict cliente -> editor -> categoria -> lista de tareas
                (devuelto por snapshot_manager.build_report)
        totals: dict categoria -> total agregado
                (devuelto por snapshot_manager.compute_totals)

    Returns:
        Lista de blocks lista para enviar a Slack.
    """
    today_str = _format_today_es()
    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"Reporte diario - {today_str}",
            "emoji": True,
        },
    })

    # Caso sin actividad alguna (ningun editor en ninguna categoria)
    if not report:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_No hay editores con actividad ni tareas asignadas._",
            },
        })
        return blocks

    # Una seccion por cliente. Filtramos editores vacios primero;
    # si un cliente se queda sin editores con actividad, lo omitimos entero.
    any_client_rendered = False
    for client, editors in report.items():
        # Construir secciones de editores con actividad
        editor_sections = []
        for editor, categories in editors.items():
            section_text = _build_editor_section(editor, categories)
            if section_text is None:
                continue  # editor sin nada que reportar, se omite
            editor_sections.append(section_text)

        # Si todos los editores del cliente estan vacios, omitir cliente
        if not editor_sections:
            continue

        emoji = CLIENT_EMOJIS.get(client, ":file_folder:")
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{emoji} {client}*",
            },
        })

        for section_text in editor_sections:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": section_text,
                },
            })

        any_client_rendered = True

    # Si despues del filtrado no quedo NADA que mostrar, mensaje de vacio
    if not any_client_rendered:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_No hubo actividad en las ultimas 24 horas ni hay tareas asignadas._",
            },
        })
        return blocks

    # Totales finales
    blocks.append({"type": "divider"})

    totals_line = (
        f"*:bar_chart: Totales del reporte*\n"
        f"   :pushpin: Asignados: {totals.get('asignado', 0)}\n"
        f"   :arrows_counterclockwise: En curso hoy: {totals.get('en_curso', 0)}\n"
        f"   :eyes: En revision hoy: {totals.get('revision', 0)}\n"
        f"   :white_check_mark: Aprobados hoy: {totals.get('aprobado', 0)}\n"
        f"   :checkered_flag: Completados hoy: {totals.get('completado', 0)}"
    )

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": totals_line,
        },
    })

    # Si nos pasamos del limite de blocks, truncamos al final
    if len(blocks) > MAX_BLOCKS_PER_MESSAGE:
        # Reservamos 1 block para el aviso de truncado
        blocks = blocks[: MAX_BLOCKS_PER_MESSAGE - 1]
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_...(reporte truncado por limite de Slack de 50 bloques)_",
            },
        })

    return blocks


def send_test_message():
    """Manda un mensaje de prueba simple para validar que el webhook funciona."""
    test_blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Test del bot de reportes",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Si ves este mensaje, el webhook esta configurado correctamente.",
            },
        },
    ]
    send_to_slack(test_blocks, fallback_text="Test del bot de reportes")


if __name__ == "__main__":
    print("Enviando mensaje de prueba a Slack...")
    send_test_message()