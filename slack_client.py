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

DASHBOARD_URL = "https://diegordzsa.github.io/clickup-slack-reporter/"


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
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":bar_chart: <{DASHBOARD_URL}|Ver reporte visual>"}],
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

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f":bar_chart: <{DASHBOARD_URL}|Ver reporte visual>"}],
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


def build_weekly_report_blocks(weekly_data, period_start, period_end):
    """
    Construye los blocks de Slack para el reporte semanal.

    Estructura del mensaje:
        Reporte semanal - 26 abril al 02 mayo 2026

        :trophy: Ranking general (completados + aprobados)
           1. Maria Garcia - 24 (15 completados, 9 aprobados)
           2. Juan Perez   - 18 (10 completados, 8 aprobados)
           ...

        :lotion_bottle: HAIR BIOLABS
        ─────────────
        :bust_in_silhouette: Maria Garcia
        :arrows_counterclockwise: En curso: 12
        :eyes: En revision: 8
        :white_check_mark: Aprobados: 9
        :checkered_flag: Completados: 15

        :sparkles: SKIN+
        ... (igual)

        ─────────────
        Totales semana: X en curso, Y revision, Z aprobados, W completados

    Args:
        weekly_data: dict con la estructura:
            {
                "by_client": {client: {editor: {category: count}}},
                "ranking":   [(editor, completados, aprobados, total), ...],
                "totals":    {category: total_count},
            }
        period_start, period_end: datetime de inicio y fin del periodo cubierto.

    Returns:
        Lista de blocks lista para enviar a Slack.
    """
    blocks = []

    # Header con rango de fechas
    period_str = f"{_format_date_es(period_start)} al {_format_date_es(period_end)}"
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"Reporte semanal - {period_str}",
            "emoji": True,
        },
    })

    by_client = weekly_data.get("by_client", {})
    ranking   = weekly_data.get("ranking", [])
    totals    = weekly_data.get("totals", {})

    # Caso sin actividad
    if not by_client and not ranking:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_No hubo transiciones registradas en los ultimos 7 dias._",
            },
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":bar_chart: <{DASHBOARD_URL}|Ver reporte visual>"}],
        })
        return blocks

    # ----- Bloque de RANKING -----
    if ranking:
        blocks.append({"type": "divider"})
        ranking_lines = ["*:trophy: Ranking de productividad (completados + aprobados)*"]
        for i, (editor, completados, aprobados, total) in enumerate(ranking, start=1):
            medal = ""
            if i == 1:
                medal = ":first_place_medal: "
            elif i == 2:
                medal = ":second_place_medal: "
            elif i == 3:
                medal = ":third_place_medal: "
            ranking_lines.append(
                f"{medal}*{i}. {editor}* - {total} "
                f"_({completados} completados, {aprobados} aprobados)_"
            )
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join(ranking_lines),
            },
        })

    # ----- Desglose por cliente y editor -----
    for client, editors in by_client.items():
        # Filtrar editores sin actividad (todas las categorias en 0)
        active_editors = [
            (editor, cats) for editor, cats in editors.items()
            if any(cats.get(c, 0) > 0 for c in CATEGORY_ORDER if c != "asignado")
        ]
        if not active_editors:
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

        for editor, cats in active_editors:
            section_text = _build_weekly_editor_section(editor, cats)
            if section_text is None:
                continue
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": section_text,
                },
            })

    # ----- Totales semanales -----
    blocks.append({"type": "divider"})
    totals_line = (
        f"*:bar_chart: Totales de la semana*\n"
        f"   :arrows_counterclockwise: En curso: {totals.get('en_curso', 0)}\n"
        f"   :eyes: En revision: {totals.get('revision', 0)}\n"
        f"   :white_check_mark: Aprobados: {totals.get('aprobado', 0)}\n"
        f"   :checkered_flag: Completados: {totals.get('completado', 0)}"
    )
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": totals_line,
        },
    })

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f":bar_chart: <{DASHBOARD_URL}|Ver reporte visual>"}],
    })

    # Defensa contra el limite de 50 bloques
    if len(blocks) > MAX_BLOCKS_PER_MESSAGE:
        blocks = blocks[: MAX_BLOCKS_PER_MESSAGE - 1]
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_...(reporte truncado por limite de Slack de 50 bloques)_",
            },
        })

    return blocks


def _build_weekly_editor_section(editor, cats):
    """
    Construye el texto de la seccion de un editor para el reporte semanal.
    Solo muestra categorias de transicion (no incluye 'asignado').
    Devuelve None si todas las categorias estan en 0.
    """
    transition_cats = [c for c in CATEGORY_ORDER if c != "asignado"]
    if all(cats.get(c, 0) == 0 for c in transition_cats):
        return None

    lines = [f"*:bust_in_silhouette: {editor}*"]
    for cat in transition_cats:
        count = cats.get(cat, 0)
        if count == 0:
            continue
        emoji = CATEGORY_EMOJIS[cat]
        # Quitamos el "hoy" del label diario para el contexto semanal
        label = CATEGORY_LABELS[cat].replace(" hoy", "")
        lines.append(f"{emoji} *{label}: {count}*")

    return "\n".join(lines)


def _format_date_es(dt):
    """Formatea un datetime como '28 abril 2026' en espanol."""
    formatted = dt.strftime("%d %B %Y")
    months_es = {
        "January": "enero", "February": "febrero", "March": "marzo",
        "April":   "abril",  "May":      "mayo",    "June":  "junio",
        "July":    "julio",  "August":   "agosto",  "September": "septiembre",
        "October": "octubre", "November": "noviembre", "December": "diciembre",
    }
    for en, es in months_es.items():
        formatted = formatted.replace(en, es)
    return formatted


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
