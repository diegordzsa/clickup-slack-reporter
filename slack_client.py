"""
Cliente para mandar mensajes a Slack via Incoming Webhook.
Usa Block Kit para que el mensaje se vea profesional y estructurado.
Documentacion de Block Kit: https://api.slack.com/block-kit
"""
import requests
from datetime import datetime
from config import SLACK_WEBHOOK_URL


# Emojis por cliente para el header de cada seccion
CLIENT_EMOJIS = {
    "HAIR BIOLABS": ":lotion_bottle:",
    "SKIN+": ":sparkles:",
}


def send_to_slack(blocks, fallback_text="Reporte diario de tareas completadas"):
    """Manda un mensaje a Slack usando blocks (Block Kit)."""
    payload = {
        "text": fallback_text,
        "blocks": blocks
    }

    response = requests.post(SLACK_WEBHOOK_URL, json=payload)

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
        "April": "abril", "May": "mayo", "June": "junio",
        "July": "julio", "August": "agosto", "September": "septiembre",
        "October": "octubre", "November": "noviembre", "December": "diciembre"
    }
    for en, es in months_es.items():
        today = today.replace(en, es)
    return today


def build_daily_report_blocks(grouped_completed, total_completed):
    """
    Construye los blocks de Slack para el reporte diario.

    Estructura del mensaje:

      Reporte diario - 28 abril 2026

      :lotion_bottle: HAIR BIOLABS
      ─────────────
      :bust_in_silhouette: Alejandra Ramirez - 3 tareas completadas
         - <url|Nombre tarea> _(Diseño Gráfico)_
         - <url|Nombre tarea> _(Diseño Gráfico)_
         - <url|Nombre tarea> _(Producción)_

      :bust_in_silhouette: Juan Perez - 1 tarea completada
         - <url|Nombre tarea> _(Producción)_

      :sparkles: SKIN+
      ─────────────
      ... (igual)

      ─────────────
      Total: 4 tareas completadas hoy

    Args:
        grouped_completed: dict cliente -> editor -> lista de tareas
                          (devuelto por group_completed_by_client_and_editor)
        total_completed: total absoluto de tareas completadas (no suma de
                        assignees, sino conteo unico de tareas)

    Returns:
        Lista de blocks para enviar a Slack.
    """
    today_str = _format_today_es()
    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"Reporte diario - {today_str}",
            "emoji": True
        }
    })

    # Caso sin actividad
    if total_completed == 0:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_No se completaron tareas en las ultimas 24 horas._"
            }
        })
        return blocks

    # Una seccion por cliente
    for client, editors in grouped_completed.items():
        emoji = CLIENT_EMOJIS.get(client, ":file_folder:")

        blocks.append({"type": "divider"})

        # Titulo del cliente
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{emoji} {client}*"
            }
        })

        # Por cada editor: linea de conteo + lista de tareas
        for editor, tasks in editors.items():
            count = len(tasks)
            label = "tarea completada" if count == 1 else "tareas completadas"

            editor_block = f"*:bust_in_silhouette: {editor}* - {count} {label}\n"

            for t in tasks:
                # Si hay URL, hacemos el nombre clickeable
                name = t.get("name", "Sin nombre")
                url = t.get("url", "")
                list_name = t.get("list", "")

                if url:
                    name_part = f"<{url}|{name}>"
                else:
                    name_part = name

                if list_name:
                    editor_block += f"   - {name_part}  _({list_name})_\n"
                else:
                    editor_block += f"   - {name_part}\n"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": editor_block.rstrip()
                }
            })

    # Total al final
    blocks.append({"type": "divider"})

    label = "tarea completada" if total_completed == 1 else "tareas completadas"
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*:bar_chart: Total: {total_completed} {label} hoy*"
        }
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
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Si ves este mensaje, el webhook esta configurado correctamente."
            }
        }
    ]

    send_to_slack(test_blocks, fallback_text="Test del bot de reportes")


if __name__ == "__main__":
    print("Enviando mensaje de prueba a Slack...")
    send_test_message()