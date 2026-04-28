"""
Cliente para mandar mensajes a Slack via Incoming Webhook.
Usa Block Kit para que el mensaje se vea profesional y estructurado.
Documentacion de Block Kit: https://api.slack.com/block-kit
"""
import requests
from datetime import datetime
from config import SLACK_WEBHOOK_URL


def send_to_slack(blocks, fallback_text="Reporte diario de actividad"):
    """
    Manda un mensaje a Slack usando blocks (Block Kit).
    """
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


def build_daily_report_blocks(grouped_activity, total_changes, total_new):
    """
    Construye los blocks de Slack para el reporte diario.
    """
    today = datetime.now().strftime("%d %B %Y")

    months_es = {
        "January": "enero", "February": "febrero", "March": "marzo",
        "April": "abril", "May": "mayo", "June": "junio",
        "July": "julio", "August": "agosto", "September": "septiembre",
        "October": "octubre", "November": "noviembre", "December": "diciembre"
    }
    for en, es in months_es.items():
        today = today.replace(en, es)

    blocks = []

    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"Reporte diario - {today}",
            "emoji": True
        }
    })

    if total_changes == 0 and total_new == 0:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_No se registro actividad en las ultimas 24 horas._"
            }
        })
        return blocks

    client_emojis = {
        "HAIR BIOLABS": ":lotion_bottle:",
        "SKIN+": ":sparkles:"
    }

    for client, editors in grouped_activity.items():
        emoji = client_emojis.get(client, ":file_folder:")

        blocks.append({"type": "divider"})

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{emoji} {client}*"
            }
        })

        for editor, activity in editors.items():
            editor_text = f"*:bust_in_silhouette: {editor}*\n"

            for ch in activity["status_changes"]:
                editor_text += (
                    f"   - _{ch['name']}_ -> "
                    f"`{ch['old_status']}` :arrow_right: `{ch['new_status']}`\n"
                )

            for nt in activity["new_tasks"]:
                editor_text += (
                    f"   - :new: _{nt['name']}_ "
                    f"(creada como `{nt['status']}`)\n"
                )

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": editor_text
                }
            })

    blocks.append({"type": "divider"})

    active_editors = set()
    for client_data in grouped_activity.values():
        for editor in client_data.keys():
            active_editors.add(editor)

    summary = (
        f"*:bar_chart: Resumen del dia:*\n"
        f"   - {total_changes} cambios de status\n"
        f"   - {total_new} tasks nuevas creadas\n"
        f"   - {len(active_editors)} editores activos"
    )

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": summary
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