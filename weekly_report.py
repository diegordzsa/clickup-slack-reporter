"""
Orquestador del reporte semanal (sabados en la manana).

Flujo:
1. Lee el log append-only de transiciones (data/transitions_log.jsonl).
2. Filtra los ultimos 7 dias.
3. Agrega: por cliente, por editor, por categoria.
4. Calcula ranking de productividad (completados + aprobados, descendente).
5. Manda reporte a Slack.
6. Limpia el log de entradas con mas de 30 dias.

A diferencia del daily, este reporte NO toma snapshot de ClickUp ni guarda
nada nuevo: solo lee del log que el daily fue alimentando.

Reglas de negocio:
- Cada linea del log ya viene con UN editor (las multi-asignadas estan
  expandidas en el log). Sumamos directo sin desduplicar.
- Solo se cuentan las 4 categorias de transicion (en_curso, revision,
  aprobado, completado). 'Asignado' es snapshot, no transicion.
- Si una misma tarea tuvo varias transiciones en la semana
  (ej: en_curso -> revision -> aprobado), cada transicion cuenta. Es lo
  esperado para medir actividad real.
"""
import sys
from datetime import datetime, timedelta, timezone

from config import validate_config, CATEGORY_ORDER, normalize_editor
from slack_client import build_weekly_report_blocks, send_to_slack
from transitions_log import (
    read_log,
    filter_by_days,
    cleanup_old_entries,
    TRACKED_CATEGORIES,
)

# Ventana del reporte: 7 dias hacia atras (sabado pasado a viernes)
REPORT_WINDOW_DAYS = 7

# Retencion del log: borrar entradas con mas de esto al final del weekly
LOG_RETENTION_DAYS = 30


def aggregate_weekly(entries):
    """
    Agrega las entradas del log en la estructura que necesita el reporte.

    Args:
        entries: lista de dicts del log (ya filtrados por fecha).

    Returns:
        {
            "by_client": {
                "HAIR BIOLABS": {
                    "Maria Garcia": {
                        "en_curso": 12, "revision": 8,
                        "aprobado": 9, "completado": 15,
                    },
                    ...
                },
                "SKIN+": {...},
            },
            "ranking": [
                ("Maria Garcia", 15, 9, 24),  # (editor, completados, aprobados, total)
                ("Juan Perez",   10, 8, 18),
                ...
            ],
            "totals": {
                "en_curso": X, "revision": Y, "aprobado": Z, "completado": W,
            },
        }
    """
    # 1. Conteos por cliente -> editor -> categoria
    by_client = {}
    for entry in entries:
        client   = entry.get("client", "?")
        editor   = normalize_editor(entry.get("assignee", "")) or "?"
        category = entry.get("category", "")

        if category not in TRACKED_CATEGORIES:
            continue
        if not editor or editor == "?" or editor == "SIN ASIGNAR":
            continue

        if client not in by_client:
            by_client[client] = {}
        if editor not in by_client[client]:
            by_client[client][editor] = {c: 0 for c in TRACKED_CATEGORIES}
        by_client[client][editor][category] += 1

    # Ordenar editores dentro de cada cliente por total descendente
    for client in by_client:
        sorted_editors = sorted(
            by_client[client].items(),
            key=lambda kv: (
                -sum(kv[1].values()),
                kv[0].lower(),
            ),
        )
        by_client[client] = dict(sorted_editors)

    # 2. Ranking GLOBAL por completados + aprobados, sumando entre clientes
    #    (un mismo editor puede estar en HAIR BIOLABS y SKIN+).
    global_per_editor = {}  # editor -> {completados, aprobados, total}
    for client_data in by_client.values():
        for editor, cats in client_data.items():
            if editor not in global_per_editor:
                global_per_editor[editor] = {
                    "completados": 0,
                    "aprobados":   0,
                    "total":       0,
                }
            global_per_editor[editor]["completados"] += cats.get("completado", 0)
            global_per_editor[editor]["aprobados"]   += cats.get("aprobado", 0)
            global_per_editor[editor]["total"] = (
                global_per_editor[editor]["completados"]
                + global_per_editor[editor]["aprobados"]
            )

    ranking = sorted(
        [
            (editor, d["completados"], d["aprobados"], d["total"])
            for editor, d in global_per_editor.items()
            if d["total"] > 0  # ocultar editores sin completados ni aprobados
        ],
        key=lambda t: (-t[3], t[0].lower()),
    )

    # 3. Totales globales por categoria
    totals = {c: 0 for c in TRACKED_CATEGORIES}
    for client_data in by_client.values():
        for editor_data in client_data.values():
            for cat in TRACKED_CATEGORIES:
                totals[cat] += editor_data.get(cat, 0)

    return {
        "by_client": by_client,
        "ranking":   ranking,
        "totals":    totals,
    }


def main():
    print("=" * 60)
    print("Iniciando reporte semanal de actividad")
    print("=" * 60)

    # Paso 1: validar config (necesitamos SLACK_WEBHOOK_URL al menos)
    try:
        validate_config()
    except EnvironmentError as e:
        print(f"ERROR de configuracion: {e}")
        sys.exit(1)

    # Paso 2: leer log y filtrar ultimos 7 dias
    print(f"\nLeyendo log de transiciones...")
    all_entries = read_log()
    print(f"   Total entradas en el log: {len(all_entries)}")

    weekly_entries = filter_by_days(all_entries, REPORT_WINDOW_DAYS)
    print(f"   Entradas en los ultimos {REPORT_WINDOW_DAYS} dias: {len(weekly_entries)}")

    # Paso 3: agregar
    print("\nAgregando datos del reporte...")
    weekly_data = aggregate_weekly(weekly_entries)
    print(f"   Clientes con actividad: {len(weekly_data['by_client'])}")
    print(f"   Editores en ranking:    {len(weekly_data['ranking'])}")
    print(f"   Totales:")
    for cat, n in weekly_data["totals"].items():
        print(f"     - {cat}: {n}")

    # Paso 4: armar y enviar a Slack
    # Periodo: ahora - 7 dias hasta ahora
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=REPORT_WINDOW_DAYS - 1)

    print("\nEnviando reporte a Slack...")
    blocks = build_weekly_report_blocks(weekly_data, period_start, period_end)
    try:
        send_to_slack(blocks, fallback_text="Reporte semanal de actividad")
    except Exception as e:
        print(f"ERROR al enviar a Slack: {e}")
        # No limpiamos el log si Slack fallo: queremos otra oportunidad
        sys.exit(1)

    # Paso 5: cleanup del log (entradas > 30 dias)
    print(f"\nLimpiando entradas con mas de {LOG_RETENTION_DAYS} dias...")
    try:
        cleanup_old_entries(days=LOG_RETENTION_DAYS)
    except Exception as e:
        # Cleanup fallido no es critico: el log puede ser limpiado el proximo run
        print(f"   Warning: cleanup fallo: {e}")

    print("\n" + "=" * 60)
    print("Reporte semanal completado correctamente")
    print("=" * 60)


if __name__ == "__main__":
    main()
