"""
Exporta los entregables de un mes para el panel de productividad por persona
(Google Sheet: pestanas Datos / Personas / Costes / Ganadores / Panel).

SOLO LECTURA: lee ClickUp y el log del bot, escribe CSVs. No cambia nada en
ClickUp ni en el repo.

Fuentes (acordadas con Alberto, nov-2026): Produccion y Diseno Grafico de
todas las marcas + listas de CRO. Los IDs salen de discover_clickup.py.

Como se decide la FECHA DE ENTREGA de cada tarea (la API de ClickUp de este
plan no da historial de estados, error TIS_027):
  1. "bot": primera vez que el log del daily la vio llegar a aprobado/
     completado. Es la mas fiable (listas de Produccion y Diseno desde 12-oct).
  2. "date_done": fecha en que ClickUp la cerro.
  3. "date_updated": ultima modificacion. Aproximada; se marca para revisar.
Se queda la mas temprana de las disponibles.

Rondas de correccion: vueltas revision -> en curso vistas por el bot (1 vez al
dia). Aproximadas y POR VALIDAR: el equipo aun no confirmo como marca las
correcciones. En listas de CRO no hay dato (el bot no las revisa).

Uso:
    python monthly_panel.py --mes 2026-11
    python monthly_panel.py --mes 2026-11 --salida C:/ruta/carpeta
"""
import argparse
import csv
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from clickup_client import get_tasks_from_list
from config import categorize_status, normalize_editor
from transitions_log import read_log

# (marca, lista, rol, list_id)
FUENTES = [
    ("HAIR ES",        "Producción",            "video",   "901209497686"),
    ("HAIR USA-MEX",   "Producción USA",        "video",   "901219356107"),
    ("ZENDI",          "Producción ZENDI",      "video",   "901209505714"),
    ("Lyssoderma",     "Producción",            "video",   "901218113018"),
    ("Lyssoderma",     "Producción (LATAM)",    "video",   "901223074152"),
    ("Lyssoderma EN",  "Producción/ SKIN",      "video",   "901219088954"),
    ("HAIR ES",        "Diseño Gráfico",        "diseño",  "901209452266"),
    ("ZENDI",          "Diseño Gráfico",        "diseño",  "901210218089"),
    ("Lyssoderma",     "Diseño Gráfico",        "diseño",  "901218113017"),
    ("Lyssoderma EN",  "Diseño Gráfico",        "diseño",  "901219088953"),
    ("HAIR ES",        "CRO/FUNNELS · Tareas",  "cro",     "901211480134"),
    ("HAIR ES",        "Test CRO",              "cro",     "901218666632"),
    ("HAIR USA-MEX",   "CRO Tasks USA",         "cro",     "901215105306"),
    ("HAIR USA-MEX",   "Hipótesis Testando USA", "cro",    "901217782159"),
    ("Lyssoderma",     "Sprint CRO (Active Sprint)", "cro", "901218113058"),
    ("ZENDI",          "Landings PDP, Listicle", "cro",    "901219470261"),
]

# Estados de "entregado" que solo existen en listas de CRO y el bot no mapea.
ENTREGADO_EXTRA = {"done", "winner", "losser"}

PESO_VARIANTE = 0.3
# Variantes (hooks, versiones cortas, formatos) se detectan por el nombre.
# POR VALIDAR con Alfonso: la lista sale marcada en la columna "tipo".
RE_VARIANTE = re.compile(r"\bITER\s*\d*\b|\bhooks?\b|\bvariante|\bversi[oó]n corta", re.I)
RE_CONCEPTO = re.compile(r"\bL(\d+)\s*-\s*C(\d+)\b", re.I)


def _ms(v):
    if not v:
        return None
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _iso(ts):
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _entregado(status):
    s = (status or "").strip().lower()
    return categorize_status(s) in ("aprobado", "completado") or s in ENTREGADO_EXTRA


def _historial_bot():
    """
    Del log del daily: {(task_id, editor): primera_entrega} y
    {(task_id, editor): rondas} (vueltas revision -> en curso).
    """
    primera, rondas = {}, defaultdict(int)
    ultimo = {}
    for e in sorted(read_log(), key=lambda x: x.get("ts", "")):
        key = (e.get("task_id"), normalize_editor(e.get("assignee")))
        cat = e.get("category")
        if cat in ("aprobado", "completado") and key not in primera:
            primera[key] = _iso(e["ts"])
        if cat == "en_curso" and ultimo.get(key) == "revision":
            rondas[key] += 1
        ultimo[key] = cat
    return primera, rondas


def _mes_range(mes):
    inicio = datetime.strptime(mes, "%Y-%m").replace(tzinfo=timezone.utc)
    fin = (inicio + timedelta(days=32)).replace(day=1)
    return inicio, fin


def _tipo(rol, nombre):
    if rol == "video":
        return ("variante", PESO_VARIANTE) if RE_VARIANTE.search(nombre) else ("video", 1.0)
    if rol == "diseño":
        return "estatico", 1.0
    return "cro", 1.0


def exportar(mes):
    inicio, fin = _mes_range(mes)
    primera_bot, rondas_bot = _historial_bot()

    filas, hallazgos = [], []
    actividad = defaultdict(lambda: {"marcas": set(), "roles": set(), "ultima": None})

    for marca, lista, rol, list_id in FUENTES:
        tareas = get_tasks_from_list(list_id, include_closed=True)
        print(f"  {marca:<14} {lista:<28} {len(tareas):>4} tareas")

        for t in tareas:
            nombre = t.get("name", "")
            status = t.get("status", {}).get("status", "")
            asignados = [normalize_editor(a.get("username")) for a in t.get("assignees", [])]
            updated = _ms(t.get("date_updated"))

            for p in asignados:
                a = actividad[p]
                a["marcas"].add(marca)
                a["roles"].add(rol)
                if updated and (a["ultima"] is None or updated > a["ultima"]):
                    a["ultima"] = updated

            if not _entregado(status):
                continue
            if not asignados:
                if updated and inicio <= updated < fin:
                    hallazgos.append(("tarea entregada sin asignar", marca, lista, nombre, t.get("url", "")))
                continue

            tipo, peso = _tipo(rol, nombre)
            due = _ms(t.get("due_date"))
            m = RE_CONCEPTO.search(nombre)
            concepto = f"L{m.group(1)}-C{m.group(2)}" if m else ""

            for persona in asignados:
                key = (t["id"], persona)
                candidatas = [
                    (primera_bot.get(key), "bot"),
                    (_ms(t.get("date_done")), "date_done"),
                ]
                candidatas = [c for c in candidatas if c[0]]
                if not candidatas and updated:
                    candidatas = [(updated, "date_updated")]
                if not candidatas:
                    continue
                entrega, fuente = min(candidatas, key=lambda c: c[0])
                if not (inicio <= entrega < fin):
                    continue

                if due is None:
                    a_tiempo = "sin fecha"
                else:
                    # La fecha limite de ClickUp vale para todo ese dia.
                    a_tiempo = "si" if entrega.date() <= due.date() else "no"

                filas.append({
                    "persona": persona,
                    "rol": rol,
                    "marca": marca,
                    "lista": lista,
                    "tarea": nombre,
                    "url": t.get("url", ""),
                    "tipo": tipo,
                    "peso": peso,
                    "estado": status,
                    "fecha_entrega": entrega.date().isoformat(),
                    "fuente_fecha": fuente,
                    "fecha_limite": due.date().isoformat() if due else "",
                    "a_tiempo": a_tiempo,
                    "rondas": rondas_bot.get(key, 0) if rol != "cro" else "",
                    "concepto": concepto,
                })

    filas.sort(key=lambda r: (r["persona"], r["fecha_entrega"]))
    personas = [
        {
            "persona": p,
            "roles": ", ".join(sorted(a["roles"])),
            "marcas": ", ".join(sorted(a["marcas"])),
            "ultima_actividad": a["ultima"].date().isoformat() if a["ultima"] else "",
            "entregables_mes": sum(1 for f in filas if f["persona"] == p),
        }
        for p, a in actividad.items()
        if a["ultima"] and a["ultima"] >= inicio - timedelta(days=31)
    ]
    personas.sort(key=lambda r: -r["entregables_mes"])
    return filas, personas, hallazgos


def _escribir(path, filas, campos):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def main():
    parser = argparse.ArgumentParser(description="Export mensual para el panel de productividad")
    parser.add_argument("--mes", required=True, help="AAAA-MM, ej. 2026-11")
    parser.add_argument("--salida", default=os.path.join(tempfile.gettempdir(), "panel_productividad"),
                        help="Carpeta de salida (fuera del repo: el repo es publico)")
    args = parser.parse_args()

    print(f"Exportando entregables de {args.mes}...")
    filas, personas, hallazgos = exportar(args.mes)

    os.makedirs(args.salida, exist_ok=True)
    datos = os.path.join(args.salida, f"Datos_{args.mes}.csv")
    pers = os.path.join(args.salida, f"Personas_{args.mes}.csv")
    hall = os.path.join(args.salida, f"Hallazgos_{args.mes}.csv")
    _escribir(datos, filas, list(filas[0].keys()) if filas else ["persona"])
    _escribir(pers, personas, ["persona", "roles", "marcas", "ultima_actividad", "entregables_mes"])
    _escribir(hall, [dict(zip(["hallazgo", "marca", "lista", "tarea", "url"], h)) for h in hallazgos],
              ["hallazgo", "marca", "lista", "tarea", "url"])

    print(f"\n{len(filas)} entregables · {len(personas)} personas activas · {len(hallazgos)} hallazgos")
    print(f"  {datos}\n  {pers}\n  {hall}")


if __name__ == "__main__":
    main()
