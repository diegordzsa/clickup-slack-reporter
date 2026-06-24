"""
Test: simula el reporte semanal y lo muestra en consola sin mandarlo.
Util para revisar el contenido antes de mandar a Slack.
"""
import json

from transitions_log import read_log, filter_by_date_range
from weekly_report import aggregate_weekly, _last_week_range
from slack_client import build_weekly_report_blocks

print("Leyendo log de transiciones...")
all_entries = read_log()

period_start, period_end = _last_week_range()
print(f"   Periodo: {period_start.strftime('%Y-%m-%d')} (lunes) a {period_end.strftime('%Y-%m-%d')} (domingo)")

weekly_entries = filter_by_date_range(all_entries, period_start, period_end)
print(f"   Total entradas en el log: {len(all_entries)}")
print(f"   Entradas en el periodo: {len(weekly_entries)}")

weekly_data = aggregate_weekly(weekly_entries)

blocks = build_weekly_report_blocks(weekly_data, period_start, period_end)

print("=" * 60)
print("VISTA PREVIA DE LOS BLOCKS DE SLACK:")
print("=" * 60)
print(json.dumps(blocks, indent=2, ensure_ascii=False))
print("=" * 60)
