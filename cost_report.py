"""
Reporte semanal de rentabilidad por editor: cuanto cuesta cada concepto
aprobado que entrega cada editor de video.

Flujo:
1. Lee los pagos del secret EDITOR_PAGOS (JSON). Nunca del repo: el repo es
   publico y los montos son privados.
2. Lee el log de transiciones (data/transitions_log.jsonl) que alimenta el daily.
3. Cuenta conceptos entregados por editor en la semana (lunes a domingo UTC).
4. Coste por concepto = coste semanal / conceptos.
5. Manda el reporte a Slack (o lo muestra en pantalla con --vista-previa).

Reglas de negocio (confirmadas):
- Concepto entregado = tarea de una lista "Produccion*" que llego a APROBADO
  en la semana, o que llego a FINAL/TESTADO sin haber pasado antes por
  APROBADO (el daily mira ClickUp 1 vez al dia y no ve los saltos rapidos).
  Cada (tarea, editor) cuenta una sola vez, en la semana de su primera entrega.
- Solo salen los editores con pago cargado. Los que tienen conceptos pero no
  pago van en una nota aparte.
- Pago fijo mensual se prorratea: monto * 12 / 52.

IMPORTANTE: los logs de GitHub Actions son publicos. Este script no imprime
montos salvo en --vista-previa (pensado para correr en local).

Formato de EDITOR_PAGOS:
    {
      "moneda": "USD",
      "editores": {
        "Gonzalo Flores": {"tipo": "fijo", "monto": 800, "periodo": "mensual"},
        "Olga Vasquez":   {"tipo": "fijo", "monto": 200, "periodo": "semanal"},
        "Dayana Caicedo": {"tipo": "hora"}   # o con "tarifa" y "horas"
      }
    }

Uso:
    python cost_report.py                                  # semana pasada, envia
    python cost_report.py --semana 2026-11-09              # semana concreta
    python cost_report.py --semana 2026-11-09 --vista-previa
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from config import _normalize, normalize_editor
from slack_client import send_to_slack, send_alert, _format_date_es
from transitions_log import read_log, filter_by_date_range
from weekly_report import check_data_freshness, _last_week_range

SEMANAS_POR_MES = 52 / 12


class PagosError(Exception):
    """EDITOR_PAGOS falta o esta mal escrito."""


def load_pagos():
    """
    Lee y valida EDITOR_PAGOS. Devuelve (moneda, {editor_normalizado: pago}).
    Los mensajes de error nunca incluyen montos.
    """
    raw = os.getenv("EDITOR_PAGOS", "").strip()
    if not raw:
        raise PagosError(
            "Falta el secret EDITOR_PAGOS. Crealo en GitHub > Settings > "
            "Secrets > Actions con los pagos de cada editor."
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PagosError(
            f"EDITOR_PAGOS no es un JSON valido (linea {e.lineno}, columna "
            f"{e.colno}). Revisa comas, comillas y llaves."
        )

    editores = data.get("editores") if isinstance(data, dict) else None
    if not isinstance(editores, dict) or not editores:
        raise PagosError('EDITOR_PAGOS debe tener una seccion "editores" con al menos uno.')

    pagos = {}
    for nombre, p in editores.items():
        tipo = (p or {}).get("tipo")
        try:
            if tipo == "fijo":
                monto = float(p["monto"])
                periodo = p.get("periodo", "mensual")
                if periodo not in ("mensual", "semanal"):
                    raise PagosError(
                        f'{nombre}: "periodo" debe ser "mensual" o "semanal".'
                    )
                coste = monto / SEMANAS_POR_MES if periodo == "mensual" else monto
                pagos[normalize_editor(nombre)] = {"nombre": nombre, "tipo": "fijo", "horas": None, "coste": coste}
            elif tipo == "hora":
                # Sin "horas" ni "tarifa": sale con asterisco, solo sus
                # conceptos, sin coste (asi esta Dayana por ahora).
                if "horas" not in p and "tarifa" not in p:
                    horas = coste = None
                else:
                    horas = float(p["horas"])
                    coste = horas * float(p["tarifa"])
                pagos[normalize_editor(nombre)] = {"nombre": nombre, "tipo": "hora", "horas": horas, "coste": coste}
            else:
                raise PagosError(f'{nombre}: "tipo" debe ser "fijo" o "hora".')
        except (KeyError, TypeError, ValueError):
            campos = '"monto" y "periodo"' if tipo == "fijo" else '"tarifa" y "horas"'
            raise PagosError(f"{nombre}: faltan o estan mal {campos} (deben ser numeros).")

    return data.get("moneda", ""), pagos


def _week_range(semana):
    """(lunes 00:00, domingo 23:59:59) UTC. `semana` es cualquier fecha de esa semana."""
    if not semana:
        return _last_week_range()
    try:
        dia = datetime.strptime(semana, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise SystemExit(f"--semana debe ser una fecha AAAA-MM-DD (llego {semana!r})")
    lunes = dia - timedelta(days=dia.weekday())
    return lunes, lunes + timedelta(days=6, hours=23, minutes=59, seconds=59)


def _es_produccion(entry):
    return _normalize(entry.get("list", "")).startswith("produccion")


def count_concepts(log, start, end):
    """
    Devuelve {editor: n_conceptos} de la semana.

    Un concepto se cuenta en la semana de su PRIMERA entrega (primer
    'aprobado' o 'completado' en todo el log). Asi un 'completado' despues de
    un 'aprobado', o una re-aprobacion por retrabajo, no se cuentan dos veces.
    """
    primera_entrega = {}
    for e in log:
        if e.get("category") not in ("aprobado", "completado") or not _es_produccion(e):
            continue
        editor = normalize_editor(e.get("assignee"))
        if not editor:
            continue
        key = (e.get("task_id"), editor)
        if key not in primera_entrega or e["ts"] < primera_entrega[key]["ts"]:
            primera_entrega[key] = e

    conteo = {}
    for (_, editor), e in primera_entrega.items():
        if filter_by_date_range([e], start, end):
            conteo[editor] = conteo.get(editor, 0) + 1
    return conteo


def build_rows(pagos, conteo):
    """
    Filas ordenadas: primero los mas baratos por concepto, luego los de pago
    por horas sin coste cargado, al final los de 0 conceptos.
    """
    rows = []
    for editor, p in pagos.items():
        n = conteo.get(editor, 0)
        rows.append({
            "editor": p["nombre"],
            "tipo": p["tipo"],
            "horas": p["horas"],
            "coste": p["coste"],
            "conceptos": n,
            "por_concepto": p["coste"] / n if n and p["coste"] is not None else None,
        })

    def orden(r):
        if r["por_concepto"] is not None:
            return (0, r["por_concepto"], r["editor"])
        return (1 if r["conceptos"] else 2, 0, r["editor"])

    rows.sort(key=orden)
    sin_pago = sorted(
        ((ed, n) for ed, n in conteo.items() if ed not in pagos),
        key=lambda x: -x[1],
    )
    return rows, sin_pago


SIMBOLOS_MONEDA = {"EUR": "€", "USD": "$", "MXN": "$", "COP": "$"}
_simbolo = "$"


def _money(x):
    return f"{_simbolo}{x:,.2f}"


def build_blocks(rows, sin_pago, moneda, start, end):
    global _simbolo
    _simbolo = SIMBOLOS_MONEDA.get((moneda or "").upper(), "$")
    w = max([len("Editor")] + [len(r["editor"]) for r in rows])
    lineas = [
        f"{'Editor':<{w}}  Pago  Horas  {'Coste sem.':>11}  Aprob.  Coste/concepto",
        "-" * (w + 52),
    ]
    por_horas = [r for r in rows if r["coste"] is None]
    w = max(w, *(len(r["editor"]) + 1 for r in por_horas)) if por_horas else w
    for r in rows:
        horas = f"{r['horas']:g}" if r["horas"] is not None else "-"
        if r["coste"] is None:
            nombre, coste, pc = r["editor"] + "*", "*", "* por horas"
        else:
            nombre, coste = r["editor"], _money(r["coste"])
            pc = _money(r["por_concepto"]) if r["por_concepto"] is not None else "SIN ENTREGAS"
        lineas.append(
            f"{nombre:<{w}}  {r['tipo']:<4}  {horas:>5}  {coste:>11}  "
            f"{r['conceptos']:>6}  {pc:>14}"
        )

    # Los de pago por horas sin coste no entran al total ni al promedio.
    con_coste = [r for r in rows if r["coste"] is not None]
    total = sum(r["coste"] for r in con_coste)
    total_n = sum(r["conceptos"] for r in con_coste)
    resumen = f"*Total:* {_money(total)} · {total_n} conceptos"
    if total_n:
        resumen += f" · promedio {_money(total / total_n)} por concepto"

    periodo = f"{_format_date_es(start)} al {_format_date_es(end)}"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "emoji": True,
         "text": ":moneybag: Rentabilidad por editor"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
         "text": f"Semana del {periodo}" + (f" · montos en {moneda}" if moneda else "")}]},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": "```" + "\n".join(lineas) + "```"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": resumen}},
    ]

    ceros = [r["editor"] for r in rows if r["conceptos"] == 0]
    notas = []
    if por_horas:
        notas.append(
            f":asterisk: *Trabaja por horas:* {', '.join(r['editor'] for r in por_horas)}. "
            "Se muestran sus conceptos, pero no se calcula su coste ni entra en el total."
        )
    if ceros:
        notas.append(f":warning: *Sin conceptos aprobados esta semana:* {', '.join(ceros)}")
    if sin_pago:
        notas.append(
            ":information_source: *Con aprobados pero sin pago cargado:* "
            + ", ".join(f"{ed} ({n})" for ed, n in sin_pago)
        )
    if notas:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(notas)}})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
        "_Concepto = tarea de una lista Producción que llegó a APROBADO, o a "
        "FINAL/TESTADO sin pasar por APROBADO. Pago mensual prorrateado ×12/52._"}]})
    return blocks


def _print_preview(blocks):
    """Muestra el mensaje como texto plano aproximado a como se ve en Slack."""
    for b in blocks:
        if b["type"] == "header":
            print(b["text"]["text"])
        elif b["type"] == "section":
            print(b["text"]["text"].replace("```", ""))
        elif b["type"] == "context":
            print(b["elements"][0]["text"])
        print()


def main():
    parser = argparse.ArgumentParser(description="Reporte semanal de coste por concepto")
    parser.add_argument("--semana", help="Cualquier fecha de la semana (AAAA-MM-DD). Default: la semana pasada.")
    parser.add_argument("--vista-previa", action="store_true", help="Muestra el mensaje y NO lo envia a Slack.")
    args = parser.parse_args()

    start, end = _week_range(args.semana)
    print(f"Semana: {start.date()} a {end.date()}")

    try:
        moneda, pagos = load_pagos()
    except PagosError as e:
        print(f"ERROR: {e}")
        if not args.vista_previa:
            send_alert("Reporte de rentabilidad: pagos mal configurados", str(e))
        sys.exit(1)
    print(f"Editores con pago cargado: {len(pagos)}")

    ok, msg = check_data_freshness()
    print(msg)
    if not ok:
        if not args.vista_previa:
            send_alert("Reporte de rentabilidad sin datos frescos", msg)
        sys.exit(1)

    log = read_log()
    primera = min((e["ts"] for e in log), default=None)
    if primera is None or datetime.fromisoformat(primera) > start + timedelta(days=1):
        msg = (
            f"El registro de cambios empieza el {primera[:10] if primera else '(vacio)'} y "
            f"no cubre la semana del {start.date()}: solo guarda 30 dias."
        )
        print(f"ERROR: {msg}")
        if not args.vista_previa:
            send_alert("Reporte de rentabilidad: semana fuera del registro", msg)
        sys.exit(1)

    conteo = count_concepts(log, start, end)
    rows, sin_pago = build_rows(pagos, conteo)
    blocks = build_blocks(rows, sin_pago, moneda, start, end)

    # Solo conteos en el log (los logs de Actions son publicos).
    print(f"Conceptos por editor: {dict(sorted(conteo.items()))}")

    if args.vista_previa:
        print("\n" + "=" * 60 + "\nVISTA PREVIA (no se envio a Slack)\n" + "=" * 60 + "\n")
        _print_preview(blocks)
        return

    send_to_slack(blocks, fallback_text="Reporte semanal de rentabilidad por editor")


if __name__ == "__main__":
    main()
