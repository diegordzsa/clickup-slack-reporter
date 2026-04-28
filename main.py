"""
Orquestador principal del reporte diario.
Flujo:
1. Toma snapshot actual de ClickUp
2. Carga snapshot anterior
3. Compara y detecta cambios + tasks nuevas
4. Si hay actividad, manda reporte a Slack
5. Guarda snapshot actual como nuevo "anterior"
"""
import sys
from config import validate_config
from clickup_client import get_snapshot
from snapshot_manager import (
    load_previous_snapshot,
    save_snapshot,
    compare_snapshots,
    group_changes_by_client_and_assignee
)
from slack_client import build_daily_report_blocks, send_to_slack


def main():
    print("=" * 60)
    print("Iniciando reporte diario de actividad")
    print("=" * 60)

    # Paso 1: validar configuracion
    try:
        validate_config()
    except EnvironmentError as e:
        print(f"ERROR de configuracion: {e}")
        sys.exit(1)

    # Paso 2: tomar snapshot actual
    print("\nTomando snapshot actual de ClickUp...")
    try:
        current = get_snapshot()
        print(f"   {len(current['tasks'])} tasks capturadas")
    except Exception as e:
        print(f"ERROR al tomar snapshot: {e}")
        sys.exit(1)

    # Paso 3: cargar snapshot anterior
    print("\nCargando snapshot anterior...")
    previous = load_previous_snapshot()

    if previous is None:
        print("   Primera ejecucion: no hay snapshot anterior.")
        print("   Guardando snapshot actual y saliendo.")
        save_snapshot(current)
        print("\nListo. El proximo run podra generar reporte.")
        return

    print(f"   Snapshot anterior: {previous['timestamp']}")

    # Paso 4: comparar
    print("\nComparando snapshots...")
    result = compare_snapshots(previous, current)
    total_changes = len(result["status_changes"])
    total_new = len(result["new_tasks"])
    print(f"   {total_changes} cambios de status")
    print(f"   {total_new} tasks nuevas")

    # Paso 5: enviar a Slack
    grouped = group_changes_by_client_and_assignee(result)
    blocks = build_daily_report_blocks(grouped, total_changes, total_new)

    print("\nEnviando reporte a Slack...")
    try:
        send_to_slack(blocks, fallback_text="Reporte diario de actividad")
    except Exception as e:
        print(f"ERROR al enviar a Slack: {e}")
        # Aun asi guardamos el snapshot para no perder el estado
        save_snapshot(current)
        sys.exit(1)

    # Paso 6: guardar snapshot actual como nuevo anterior
    print("\nGuardando snapshot actual...")
    save_snapshot(current)

    print("\n" + "=" * 60)
    print("Reporte completado correctamente")
    print("=" * 60)


if __name__ == "__main__":
    main()