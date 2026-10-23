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

from config import validate_config, get_active_folders, FOLDER_SECRETS
from clickup_client import get_snapshot, check_token, TokenInvalidError
from slack_client import send_alert
from snapshot_manager import (
    load_previous_snapshot,
    save_snapshot,
    find_transitions,
)
from transitions_log import append_transitions

# Si el snapshot trae menos tareas que esto, algo se rompio: no lo pisamos.
# Un tablero real tiene ~1000 tareas; una caida parcial de la API podria
# devolver 3 y borrarnos el historial bueno.
MIN_TASKS_ESPERADAS = 50


def main():
    print("=" * 60)
    print("Iniciando recoleccion diaria de datos")
    print("=" * 60)

    try:
        proyectos_sin_configurar = validate_config()
    except EnvironmentError as e:
        print(f"ERROR de configuracion: {e}")
        send_alert("Falta configuracion", str(e))
        sys.exit(1)

    # Un proyecto sin secret no aborta la recoleccion, pero tampoco pasa
    # desapercibido: sus tareas no se estarian contando en ningun reporte.
    if proyectos_sin_configurar:
        send_alert(
            "Hay proyectos sin trackear",
            f"Estos proyectos no tienen CLICKUP_FOLDER_ID configurado y "
            f"quedan fuera de todos los reportes: "
            f"{', '.join(proyectos_sin_configurar)}.\n\n"
            f"Agrega su secret en GitHub > Settings > Secrets > Actions.",
            urgente=False,
        )

    # Preflight: si el token murio, decirlo claro y avisar a Slack.
    print("\nVerificando token de ClickUp...")
    try:
        check_token()
        print("   Token valido")
    except TokenInvalidError as e:
        print(f"ERROR: {e}")
        send_alert("Token de ClickUp vencido", str(e))
        sys.exit(1)
    except Exception as e:
        print(f"ERROR al verificar el token: {e}")
        send_alert("No se pudo contactar a ClickUp", str(e))
        sys.exit(1)

    print("\nTomando snapshot actual de ClickUp...")
    try:
        current = get_snapshot()
        print(f"   {len(current['tasks'])} tasks capturadas")
    except TokenInvalidError as e:
        print(f"ERROR: {e}")
        send_alert("Token de ClickUp vencido", str(e))
        sys.exit(1)
    except Exception as e:
        print(f"ERROR al tomar snapshot: {e}")
        send_alert("Fallo al bajar datos de ClickUp", str(e))
        sys.exit(1)

    fallidas = current.pop("fallidas", {})
    activas, _ = get_active_folders()
    if fallidas and len(fallidas) == len(activas):
        detalle = "\n".join(f"{c}: {err}" for c, (_, err) in fallidas.items())
        print("ERROR: no se pudo bajar ninguna carpeta")
        send_alert("Fallo al bajar datos de ClickUp", detalle)
        sys.exit(1)

    print("\nCargando snapshot anterior...")
    previous = load_previous_snapshot()

    if fallidas:
        # Las tareas de las carpetas caidas se copian del snapshot anterior.
        # Si las dejaramos fuera, el dia que la carpeta vuelva sus tareas
        # parecerian "nuevas" y se perderian sus transiciones.
        if previous:
            for task_id, data in previous.get("tasks", {}).items():
                if data.get("client") in fallidas:
                    current["tasks"].setdefault(task_id, data)

        lineas = [
            f"- {c} (folder {fid}, secret {FOLDER_SECRETS[c]}): {err}"
            for c, (fid, err) in fallidas.items()
        ]
        send_alert(
            "Hay carpetas de ClickUp que no se pudieron leer",
            "\n".join(lineas) + "\n\n"
            "El resto de proyectos se recolecto normal; estos quedan con los "
            "datos del ultimo dia bueno.\n"
            "Un 404 'Not found' significa que la carpeta se borro, se movio o "
            "se archivo en ClickUp, o que el token ya no tiene acceso. "
            "Busca el ID nuevo (python discover_clickup.py) y actualiza el "
            "secret en GitHub > Settings > Secrets > Actions.",
        )

    # Guarda de integridad: nunca pisar el snapshot bueno con uno vacio.
    if len(current["tasks"]) < MIN_TASKS_ESPERADAS:
        msg = (
            f"El snapshot trajo solo {len(current['tasks'])} tareas "
            f"(esperadas >= {MIN_TASKS_ESPERADAS}). No se guardo para no "
            f"corromper el historial. Revisa permisos del token o si "
            f"movieron/archivaron carpetas en ClickUp."
        )
        print(f"ERROR: {msg}")
        send_alert("Snapshot sospechosamente vacio", msg)
        sys.exit(1)

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
