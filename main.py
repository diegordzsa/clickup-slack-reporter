"""
Orquestador principal del reporte diario de tareas completadas.

Flujo:
1. Toma snapshot actual de ClickUp
2. Carga snapshot anterior
3. Busca tareas que pasaron de NO completado a completado entre los dos
4. Agrupa por cliente y editor (asignees)
5. Manda reporte a Slack
6. Guarda snapshot actual como nuevo "anterior"

Reglas de negocio:
- Tareas SIN ASIGNAR que se completan se IGNORAN.
- Tareas con varios assignees suman a CADA uno (aparecen repetidas).
- "Completado" depende del status, definido en config.COMPLETED_STATUSES.
"""
import sys
from config import validate_config
from clickup_client import get_snapshot
from snapshot_manager import (
    load_previous_snapshot,
    save_snapshot,
    find_completed_tasks,
    group_completed_by_client_and_editor,
)
from slack_client import build_daily_report_blocks, send_to_slack


def main():
    print("=" * 60)
    print("Iniciando reporte diario de tareas completadas")
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

    # Paso 4: detectar tareas completadas
    print("\nDetectando tareas completadas...")
    completed = find_completed_tasks(previous, current)
    total_completed = len(completed)
    print(f"   {total_completed} tareas pasaron a completadas")

    # Paso 5: agrupar y enviar a Slack
    grouped = group_completed_by_client_and_editor(completed)
    blocks = build_daily_report_blocks(grouped, total_completed)

    print("\nEnviando reporte a Slack...")
    try:
        send_to_slack(blocks, fallback_text="Reporte diario de tareas completadas")
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