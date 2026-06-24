"""
Recolector diario de datos de ClickUp.
Flujo:
1. Toma snapshot actual de ClickUp.
2. Carga snapshot anterior.
3. Detecta transiciones y las appendea al log (alimenta el reporte semanal).
4. Guarda snapshot actual como nuevo "anterior".

No envia notificaciones a Slack; el unico canal de comunicacion es el
reporte semanal (weekly_report.py).
"""
import sys

from config import validate_config
from clickup_client import get_snapshot
from snapshot_manager import (
    load_previous_snapshot,
    save_snapshot,
    find_transitions,
)
from transitions_log import append_transitions


def main():
    print("=" * 60)
    print("Iniciando recoleccion diaria de datos")
    print("=" * 60)

    try:
        validate_config()
    except EnvironmentError as e:
        print(f"ERROR de configuracion: {e}")
        sys.exit(1)

    print("\nTomando snapshot actual de ClickUp...")
    try:
        current = get_snapshot()
        print(f"   {len(current['tasks'])} tasks capturadas")
    except Exception as e:
        print(f"ERROR al tomar snapshot: {e}")
        sys.exit(1)

    print("\nCargando snapshot anterior...")
    previous = load_previous_snapshot()

    if previous is None:
        print("   Primera ejecucion: no hay snapshot anterior.")
        print("   Guardando snapshot actual y saliendo.")
        save_snapshot(current)
        print("\nListo. El proximo run podra detectar transiciones.")
        return

    print(f"   Snapshot anterior: {previous['timestamp']}")

    print("\nDetectando transiciones y appendeando al log...")
    try:
        transitions = find_transitions(previous, current)
        append_transitions(transitions)
    except Exception as e:
        print(f"   Warning: error al appendear al log: {e}")

    print("\nGuardando snapshot actual...")
    save_snapshot(current)

    print("\n" + "=" * 60)
    print("Recoleccion diaria completada correctamente")
    print("=" * 60)


if __name__ == "__main__":
    main()
