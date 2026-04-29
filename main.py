"""
Orquestador principal del reporte diario.
Flujo:
1. Toma snapshot actual de ClickUp.
2. Carga snapshot anterior.
3. Construye reporte: snapshot de "asignados" + transiciones de las
   ultimas 24h (en_curso, revision, aprobado, completado), agrupado
   por cliente y editor.
4. Manda reporte a Slack SIEMPRE (aunque no haya transiciones, para que
   se vea la carga actual de asignados).
5. Guarda snapshot actual como nuevo "anterior".

Reglas de negocio:
- Tareas SIN ASIGNAR se ignoran completamente.
- Tareas con varios assignees suman a CADA uno (aparecen repetidas).
- "Asignados" es snapshot del estado actual; el resto son transiciones.
- Categorias y mapeo de status definidos en config.STATUS_CATEGORIES.
"""
import sys

from config import validate_config
from clickup_client import get_snapshot
from snapshot_manager import (
    load_previous_snapshot,
    save_snapshot,
    build_report,
    compute_totals,
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
        print("   No se enviara reporte (no hay base para detectar transiciones).")
        print("   Guardando snapshot actual y saliendo.")
        save_snapshot(current)
        print("\nListo. El proximo run podra generar reporte.")
        return

    print(f"   Snapshot anterior: {previous['timestamp']}")

    # Paso 4: construir reporte (snapshot asignados + transiciones 24h)
    print("\nConstruyendo reporte...")
    report = build_report(previous, current)
    totals = compute_totals(report)

    print(f"   Editores con actividad: {sum(len(e) for e in report.values())}")
    print(f"   Totales por categoria:")
    for cat, n in totals.items():
        print(f"     - {cat}: {n}")

    # Paso 5: enviar a Slack (siempre, aunque este vacio)
    print("\nEnviando reporte a Slack...")
    blocks = build_daily_report_blocks(report, totals)
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