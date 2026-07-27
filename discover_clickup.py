"""
Script de descubrimiento (SOLO LECTURA): recorre todo el team de ClickUp y
lista spaces -> folders -> lists con sus IDs, cuantas tasks tienen, que
statuses usan y quien esta asignado.

Sirve para dos cosas:
1. Sacar los IDs reales de los proyectos nuevos (HAIR BIOLABS MX, Lyssoderma,
   Proyecto Espana, ZENDI, Lyssoderma English) para poder trackearlos.
2. Ver que status usa cada proyecto, porque cada uno puede tener su propio
   flujo y hay que mapearlos en STATUS_CATEGORIES antes de que el reporte
   sirva de algo.

No escribe nada en ClickUp ni en el repo. Solo imprime.

Uso:
    python discover_clickup.py            # resumen (rapido)
    python discover_clickup.py --full     # + statuses y assignees por list
"""
import sys
from collections import Counter

import requests

from config import CLICKUP_TOKEN, CLICKUP_TEAM_ID, categorize_status

BASE_URL = "https://api.clickup.com/api/v2"
HEADERS = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}

FULL = "--full" in sys.argv


def _get(path, **params):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params or None)
    if r.status_code != 200:
        raise Exception(f"{path} -> {r.status_code}: {r.text[:200]}")
    return r.json()


def get_spaces():
    return _get(f"/team/{CLICKUP_TEAM_ID}/space", archived="false").get("spaces", [])


def get_folders(space_id):
    return _get(f"/space/{space_id}/folder", archived="false").get("folders", [])


def get_folderless_lists(space_id):
    return _get(f"/space/{space_id}/list", archived="false").get("lists", [])


def get_tasks(list_id):
    """Todas las tasks de una list, paginado."""
    out, page = [], 0
    while True:
        data = _get(f"/list/{list_id}/task", page=page,
                    include_closed="true", subtasks="true")
        tasks = data.get("tasks", [])
        if not tasks:
            break
        out.extend(tasks)
        if data.get("last_page", False):
            break
        page += 1
    return out


def scan_list(lst, indent):
    """Imprime una list y devuelve (n_tasks, Counter statuses, Counter assignees)."""
    name, lid = lst.get("name", "?"), lst["id"]
    try:
        tasks = get_tasks(lid)
    except Exception as e:
        print(f"{indent}- [list] {name}  (id={lid})  ERROR: {e}")
        return 0, Counter(), Counter()

    statuses, assignees = Counter(), Counter()
    for t in tasks:
        statuses[t.get("status", {}).get("status", "SIN_STATUS")] += 1
        aa = t.get("assignees", [])
        if not aa:
            assignees["SIN ASIGNAR"] += 1
        for a in aa:
            assignees[a.get("username", "?")] += 1

    print(f"{indent}- [list] {name:<28} id={lid:<12} tasks={len(tasks)}")
    if FULL and statuses:
        for s, n in statuses.most_common():
            cat = categorize_status(s)
            flag = "  <-- SIN MAPEAR" if cat is None else f"  -> {cat}"
            print(f"{indent}     status {s!r:24} n={n:<5}{flag}")
    return len(tasks), statuses, assignees


def main():
    if not CLICKUP_TOKEN or not CLICKUP_TEAM_ID:
        print("ERROR: falta CLICKUP_TOKEN o CLICKUP_TEAM_ID en el .env")
        sys.exit(1)

    print("=" * 78)
    print(f"DESCUBRIMIENTO DE CLICKUP — team {CLICKUP_TEAM_ID}")
    print("=" * 78)

    global_statuses, global_assignees = Counter(), Counter()
    resumen = []

    for space in get_spaces():
        sname, sid = space.get("name", "?"), space["id"]
        print(f"\n[SPACE] {sname}   id={sid}")
        total = 0

        for folder in get_folders(sid):
            fname, fid = folder.get("name", "?"), folder["id"]
            print(f"   [folder] {fname:<26} id={fid}")
            for lst in folder.get("lists", []):
                n, st, asg = scan_list(lst, "      ")
                total += n
                global_statuses.update(st)
                global_assignees.update(asg)

        folderless = get_folderless_lists(sid)
        if folderless:
            print(f"   (lists sueltas, sin folder)")
            for lst in folderless:
                n, st, asg = scan_list(lst, "      ")
                total += n
                global_statuses.update(st)
                global_assignees.update(asg)

        print(f"   TOTAL space: {total} tasks")
        resumen.append((sname, sid, total))

    print("\n" + "=" * 78)
    print("RESUMEN — copia estos IDs para configurar el tracking")
    print("=" * 78)
    for sname, sid, total in resumen:
        print(f"   {sname:<28} space_id={sid:<12} {total} tasks")

    print("\n" + "=" * 78)
    print("STATUSES EN TODO EL TEAM (revisar los SIN MAPEAR)")
    print("=" * 78)
    for s, n in global_statuses.most_common():
        cat = categorize_status(s)
        flag = "SIN MAPEAR  <---" if cat is None else cat
        print(f"   {s!r:28} n={n:<6} {flag}")

    print("\n" + "=" * 78)
    print("PERSONAS CON TAREAS ASIGNADAS EN TODO EL TEAM")
    print("=" * 78)
    for a, n in global_assignees.most_common():
        print(f"   {a:<34} {n}")


if __name__ == "__main__":
    main()
