"""
Genera el archivo data.json que consume el dashboard frontend.

Lee:
  - data/last_snapshot.json (estado actual + fechas)
  - data/transitions_log.jsonl (historico de transiciones)

Produce:
  - docs/data.json con la siguiente estructura:

{
  "generated_at": "2026-05-08T08:00:00+00:00",
  "editors":  ["Alejandra Ramirez", "Dayana Caicedo", ...],
  "clients":  ["HAIR BIOLABS", "SKIN+"],
  "lists":    ["Diseño Gráfico", "Producción", ...],
  "completed_tasks": [
    {
      "task_id":      "869d2r7by",
      "name":         "Nueva imagen PDP",
      "client":       "HAIR BIOLABS",
      "list":         "Diseño Gráfico",
      "assignees":    ["Alejandra Ramirez"],
      "date_created": "2026-04-15T10:30:00+00:00",
      "date_done":    "2026-05-01T14:20:00+00:00",
      "lead_time_hours": 388.83,
      "url": "https://app.clickup.com/t/869d2r7by"
    },
    ...
  ],
  "transitions": [
    {
      "ts":       "2026-05-05T07:28:26+00:00",
      "task_id":  "869d212zk",
      "name":     "L46-C199-VX-G",
      "client":   "HAIR BIOLABS",
      "list":     "Producción",
      "category": "en_curso",
      "assignee": "Gonzalo Flores",
      "url":      "https://..."
    },
    ...
  ],
  "currently_assigned": [
    { ...mismo formato que completed_tasks pero sin date_done... }
  ],
  "stats": {
    "total_tasks_in_snapshot": 664,
    "total_completed_with_dates": 8,
    "total_transitions_logged": 29
  }
}
"""
import json
import os
from datetime import datetime, timezone

from config import categorize_status, normalize_editor

SNAPSHOT_FILE = "data/last_snapshot.json"
TRANSITIONS_LOG = "data/transitions_log.jsonl"
OUTPUT_FILE = "docs/data.json"

UNASSIGNED_MARKER = "SIN ASIGNAR"


def _split_assignees(raw):
    """Convierte el string 'A, B, C' en lista, normalizando nombres."""
    if not raw or raw == UNASSIGNED_MARKER:
        return []
    out = []
    for n in raw.split(","):
        cleaned = normalize_editor(n)
        if cleaned and cleaned.upper() != UNASSIGNED_MARKER:
            out.append(cleaned)
    return out


def _hours_between(iso_start, iso_end):
    """Diferencia en horas entre dos fechas ISO. None si alguna falta."""
    if not iso_start or not iso_end:
        return None
    try:
        a = datetime.fromisoformat(iso_start)
        b = datetime.fromisoformat(iso_end)
        if a.tzinfo is None:
            a = a.replace(tzinfo=timezone.utc)
        if b.tzinfo is None:
            b = b.replace(tzinfo=timezone.utc)
        delta = b - a
        return round(delta.total_seconds() / 3600, 2)
    except (ValueError, TypeError):
        return None


def load_snapshot():
    """Carga el snapshot. Devuelve dict vacio si no existe."""
    if not os.path.exists(SNAPSHOT_FILE):
        return {"timestamp": None, "tasks": {}}
    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_transitions():
    """Carga el log de transiciones. Devuelve lista vacia si no existe."""
    if not os.path.exists(TRANSITIONS_LOG):
        return []
    entries = []
    with open(TRANSITIONS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def build_completed_tasks(snapshot):
    """
    Extrae todas las tareas en categoria 'completado' que tengan fechas validas.
    Calcula lead_time_hours = date_done - date_created.
    """
    completed = []
    tasks = snapshot.get("tasks", {})

    for task_id, t in tasks.items():
        category = categorize_status(t.get("status", ""))
        if category != "completado":
            continue

        assignees = _split_assignees(t.get("assignee", ""))
        if not assignees:
            continue

        date_created = t.get("date_created")
        date_done = t.get("date_done")
        lead_time = _hours_between(date_created, date_done)

        completed.append({
            "task_id":         task_id,
            "name":            t.get("name", ""),
            "client":          t.get("client", "?"),
            "list":            t.get("list", "?"),
            "assignees":       assignees,
            "date_created":    date_created,
            "date_done":       date_done,
            "lead_time_hours": lead_time,
            "url":             t.get("url", ""),
        })

    return completed


def build_currently_assigned(snapshot):
    """Tasks actualmente con status que mapea a alguna categoria activa."""
    result = []
    tasks = snapshot.get("tasks", {})

    for task_id, t in tasks.items():
        category = categorize_status(t.get("status", ""))
        if category is None or category == "completado":
            continue

        assignees = _split_assignees(t.get("assignee", ""))
        if not assignees:
            continue

        result.append({
            "task_id":      task_id,
            "name":         t.get("name", ""),
            "client":       t.get("client", "?"),
            "list":         t.get("list", "?"),
            "category":     category,
            "status":       t.get("status", ""),
            "assignees":    assignees,
            "date_created": t.get("date_created"),
            "url":          t.get("url", ""),
        })

    return result


def build_transitions(raw_log):
    """Normaliza y limpia las entradas del log de transiciones."""
    result = []
    for entry in raw_log:
        editor = normalize_editor(entry.get("assignee", ""))
        if not editor or editor.upper() == UNASSIGNED_MARKER:
            continue
        result.append({
            "ts":       entry.get("ts", ""),
            "task_id":  entry.get("task_id", ""),
            "name":     entry.get("name", ""),
            "client":   entry.get("client", "?"),
            "list":     entry.get("list", "?"),
            "category": entry.get("category", ""),
            "assignee": editor,
            "url":      entry.get("url", ""),
        })
    return result


def collect_dimensions(completed, currently_assigned, transitions):
    """Devuelve listas unicas de editores, clientes y lists para los filtros."""
    editors = set()
    clients = set()
    lists = set()

    for t in completed:
        for a in t["assignees"]:
            editors.add(a)
        clients.add(t["client"])
        lists.add(t["list"])

    for t in currently_assigned:
        for a in t["assignees"]:
            editors.add(a)
        clients.add(t["client"])
        lists.add(t["list"])

    for t in transitions:
        editors.add(t["assignee"])
        clients.add(t["client"])
        lists.add(t["list"])

    return {
        "editors": sorted(editors, key=lambda s: s.lower()),
        "clients": sorted(clients),
        "lists":   sorted(lists),
    }


def generate():
    """Pipeline completo: lee, transforma, escribe data.json."""
    print("=" * 60)
    print("Generando data.json para el dashboard")
    print("=" * 60)

    snapshot = load_snapshot()
    raw_log = load_transitions()

    print(f"\nSnapshot: {len(snapshot.get('tasks', {}))} tasks")
    print(f"Log: {len(raw_log)} entradas")

    completed = build_completed_tasks(snapshot)
    currently_assigned = build_currently_assigned(snapshot)
    transitions = build_transitions(raw_log)
    dims = collect_dimensions(completed, currently_assigned, transitions)

    completed_with_dates = sum(1 for t in completed if t["lead_time_hours"] is not None)

    output = {
        "generated_at":       datetime.now(timezone.utc).isoformat(),
        "snapshot_timestamp": snapshot.get("timestamp"),
        "editors":            dims["editors"],
        "clients":            dims["clients"],
        "lists":              dims["lists"],
        "completed_tasks":    completed,
        "currently_assigned": currently_assigned,
        "transitions":        transitions,
        "stats": {
            "total_tasks_in_snapshot":     len(snapshot.get("tasks", {})),
            "total_completed":             len(completed),
            "total_completed_with_dates":  completed_with_dates,
            "total_currently_assigned":    len(currently_assigned),
            "total_transitions_logged":    len(transitions),
            "total_editors":               len(dims["editors"]),
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nResumen:")
    print(f"  Editores unicos:           {output['stats']['total_editors']}")
    print(f"  Tareas completadas:        {output['stats']['total_completed']}")
    print(f"  Con fechas (lead time):    {output['stats']['total_completed_with_dates']}")
    print(f"  Actualmente en flujo:      {output['stats']['total_currently_assigned']}")
    print(f"  Transiciones logueadas:    {output['stats']['total_transitions_logged']}")

    print(f"\n✅ Escrito en {OUTPUT_FILE}")
    return output


if __name__ == "__main__":
    generate()
