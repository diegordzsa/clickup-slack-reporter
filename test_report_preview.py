"""
Test: simula el reporte completo y lo muestra en consola sin mandarlo.
Útil para revisar el contenido antes de mandar a Slack.
"""
from clickup_client import get_snapshot
from snapshot_manager import (
    load_previous_snapshot,
    compare_snapshots,
    group_changes_by_client_and_assignee
)
from slack_client import build_daily_report_blocks, send_to_slack
import json


# Tomar snapshot actual
print("📸 Tomando snapshot actual...")
current = get_snapshot()

# Cargar snapshot anterior
previous = load_previous_snapshot()

if previous is None:
    print("⚠️ No hay snapshot anterior, no se puede generar reporte aún.")
    exit()

# Comparar
result = compare_snapshots(previous, current)
grouped = group_changes_by_client_and_assignee(result)

total_changes = len(result["status_changes"])
total_new = len(result["new_tasks"])

print(f"\n📊 Resumen:")
print(f"   {total_changes} cambios de status")
print(f"   {total_new} tasks nuevas")
print(f"   {len(grouped)} clientes con actividad\n")

# Construir blocks
blocks = build_daily_report_blocks(grouped, total_changes, total_new)

print("=" * 60)
print("VISTA PREVIA DE LOS BLOCKS DE SLACK:")
print("=" * 60)
print(json.dumps(blocks, indent=2, ensure_ascii=False))
print("=" * 60)

# Preguntar si mandar a Slack
respuesta = input("\n¿Mandar este reporte a Slack? (s/n): ")
if respuesta.lower() == "s":
    send_to_slack(blocks, fallback_text="Reporte diario de actividad")
else:
    print("Cancelado, no se envió nada.")