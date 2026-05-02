"""
Append-only log de transiciones para alimentar el reporte semanal.

Cada vez que el daily detecta transiciones (en_curso, revision, aprobado,
completado), las appendea aqui en formato JSONL (una linea = una transicion).

El reporte semanal lee este archivo, filtra los ultimos 7 dias y agrega
los conteos. Al final del weekly, se limpia el log de entradas con mas
de 30 dias para que no crezca indefinidamente.

Formato de cada linea:
{
    "ts":       "2026-05-02T05:17:00+00:00",   # ISO 8601 UTC
    "task_id":  "abc123",
    "name":     "Tarea X",
    "client":   "HAIR BIOLABS",
    "list":     "Diseno Grafico",
    "category": "completado",
    "assignee": "Maria Garcia",                # un editor por linea
    "url":      "https://app.clickup.com/..."
}

NOTA: una tarea multi-asignada genera UNA LINEA POR EDITOR. Esto preserva
la regla de negocio "tareas multi-asignadas suman a cada editor".
"""
import json
import os
from datetime import datetime, timedelta, timezone

LOG_FILE = "data/transitions_log.jsonl"

# Solo trackeamos las 4 categorias de transicion. "asignado" es snapshot,
# no transicion, asi que no entra al log.
TRACKED_CATEGORIES = ["en_curso", "revision", "aprobado", "completado"]


def append_transitions(transitions, timestamp=None):
    """
    Appendea las transiciones detectadas al log.

    Args:
        transitions: dict {category: [task_dict, ...]} tal como lo devuelve
                     snapshot_manager.find_transitions().
        timestamp:   datetime opcional. Si no se pasa, usa now() en UTC.

    Cada task con N assignees genera N lineas (una por editor).
    Solo se appendean las categorias en TRACKED_CATEGORIES.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    ts_iso = timestamp.isoformat()

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    lines_written = 0
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        for category in TRACKED_CATEGORIES:
            for task in transitions.get(category, []):
                assignees = task.get("assignees", [])
                if not assignees:
                    continue

                for editor in assignees:
                    entry = {
                        "ts":       ts_iso,
                        "task_id":  task.get("task_id", ""),
                        "name":     task.get("name", ""),
                        "client":   task.get("client", ""),
                        "list":     task.get("list", ""),
                        "category": category,
                        "assignee": editor,
                        "url":      task.get("url", ""),
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    lines_written += 1

    print(f"Log de transiciones: {lines_written} lineas appendeadas a {LOG_FILE}")
    return lines_written


def read_log():
    """
    Lee todas las entradas del log. Devuelve lista de dicts.
    Si el archivo no existe, devuelve lista vacia.
    Tolera lineas mal formadas (las skipea con warning).
    """
    if not os.path.exists(LOG_FILE):
        return []

    entries = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  Warning: linea {i} mal formada en {LOG_FILE}: {e}")
                continue

    return entries


def filter_by_days(entries, days):
    """
    Devuelve solo las entradas con timestamp dentro de los ultimos `days` dias.
    Compara con datetime.now(UTC).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = []
    for entry in entries:
        ts_str = entry.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            continue
        # Si el timestamp es naive, asumimos UTC
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= cutoff:
            result.append(entry)
    return result


def cleanup_old_entries(days=30):
    """
    Reescribe el log eliminando entradas con mas de `days` dias.
    Devuelve cuantas entradas quedaron y cuantas se borraron.
    """
    if not os.path.exists(LOG_FILE):
        return 0, 0

    all_entries = read_log()
    kept = filter_by_days(all_entries, days)
    removed = len(all_entries) - len(kept)

    if removed == 0:
        print(f"Cleanup: nada que limpiar ({len(all_entries)} entradas, todas <= {days}d).")
        return len(kept), 0

    # Reescribir el archivo solo con las entradas que sobreviven
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        for entry in kept:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Cleanup: {removed} entradas borradas (>{days}d), {len(kept)} conservadas.")
    return len(kept), removed


if __name__ == "__main__":
    # Smoke test rapido
    entries = read_log()
    print(f"Total entradas en el log: {len(entries)}")
    last_7 = filter_by_days(entries, 7)
    print(f"Entradas en los ultimos 7 dias: {len(last_7)}")
