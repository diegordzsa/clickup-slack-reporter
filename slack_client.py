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
    get_semaforo,
)

CLIENT_EMOJIS = {
    "HAIR BIOLABS": ":lotion_bottle:",
    "SKIN+":        ":sparkles:",
}

MAX_BLOCKS_PER_MESSAGE = 50
MAX_CHARS_PER_SECTION = 2900

DASHBOARD_URL = "https://diegordzsa.github.io/clickup-slack-reporter/"


def send_to_slack(blocks, fallback_text="Reporte semanal de actividad"):
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


def build_weekly_report_blocks(weekly_data, period_start, period_end):
    """
    Construye los blocks de Slack para el reporte semanal.

    Incluye semaforo de productividad por editor:
        :large_green_circle:  9+ completados+aprobados
        :large_yellow_circle: 4-8
        :red_circle:          1-3
        :white_circle:        0
    """
    blocks = []

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

    # ----- Leyenda del semaforo -----
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                "*Semaforo de productividad (completados + aprobados):*\n"
                ":large_green_circle: 9+  |  "
                ":large_yellow_circle: 4-8  |  "
                ":red_circle: 1-3  |  "
                ":white_circle: 0"
            ),
        },
    })

    # ----- Bloque de RANKING con semaforo -----
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
            semaforo = get_semaforo(total)
            ranking_lines.append(
                f"{semaforo} {medal}*{i}. {editor}* - {total} "
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
    Incluye semaforo basado en completados + aprobados.
    """
    transition_cats = [c for c in CATEGORY_ORDER if c != "asignado"]
    if all(cats.get(c, 0) == 0 for c in transition_cats):
        return None

    productivity = cats.get("completado", 0) + cats.get("aprobado", 0)
    semaforo = get_semaforo(productivity)

    lines = [f"{semaforo} *:bust_in_silhouette: {editor}*"]
    for cat in transition_cats:
        count = cats.get(cat, 0)
        if count == 0:
            continue
        emoji = CATEGORY_EMOJIS[cat]
        label = CATEGORY_LABELS[cat].replace(" hoy", "")
        lines.append(f"{emoji} *{label}: {count}*")

    return "\n".join(lines)


def _format_date_es(dt):
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
