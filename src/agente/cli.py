"""Interfaz de linea de comandos del agente de gestion de casos.

Ejemplos:
    python -m src.agente.cli escenario escenarios/E2_ficha_tercero_dos_sesiones.json
    python -m src.agente.cli todos
    python -m src.agente.cli caso --folio OIRS-2026-0900 --fecha 2026-11-02 \
        --texto "Reclamo: me gritaron en el SOME" --datos '{"tipo": "reclamo"}'
    python -m src.agente.cli estado --folio OIRS-2026-0102
    python -m src.agente.cli memoria --buscar "sospecha de cancer sin FCIP"
    python -m src.agente.cli grafo
    python -m src.agente.cli reiniciar
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from ..config import BASE_DIR
from . import calendario, registro
from .config_agente import CONFIG_AGENTE
from .herramientas import memoria, reiniciar_singletons

ESCENARIOS_DIR = BASE_DIR / "escenarios"
EVID_DIR = BASE_DIR / "evidencias" / "escenarios"

ICONO = {"decision": "◆", "tool": "▸", "plan": "▤", "replan": "↻", "evento": "⚡", "memoria": "◎", "resumen": "≡"}


def imprimir_bitacora(bitacora: list[dict], desde: int = 0, salida=sys.stdout) -> None:
    for e in bitacora[desde:]:
        print(f"  {ICONO.get(e.get('tipo'), '·')} [s{e.get('sesion', '?')} {e.get('nodo', ''):<18}] {e.get('detalle', '')}",
              file=salida)


def _agente():
    from .grafo import AgenteCasos

    return AgenteCasos()


def correr_escenario(ruta: Path, agente=None, verbose: bool = True) -> dict:
    esc = json.loads(Path(ruta).read_text(encoding="utf-8"))
    agente = agente or _agente()
    if esc.get("simular_fallo"):
        for h, n in esc["simular_fallo"].items():
            registro.INYECTOR.programar(h, n)
    sesiones = []
    previo = 0
    if verbose:
        print(f"\n=== {esc['id']} | {esc['titulo']} | folio {esc['folio']}")
        if agente.estado(esc["folio"]):
            print("  (aviso: el folio ya tiene checkpoint; las sesiones se agregan al caso existente."
                  " Use 'reiniciar' para partir de cero)")
    for s in esc["sesiones"]:
        final = agente.procesar(esc["folio"], s["texto"], s.get("fecha"), s.get("datos"))
        bit = final.get("bitacora", [])
        nuevas = [e for e in bit if e.get("sesion") == final.get("sesion")]
        if verbose:
            print(f"\n--- sesion {final.get('sesion')} ({s.get('fecha')}): {s['texto'][:90]}")
            imprimir_bitacora(nuevas)
            r = final.get("resumen_sesion", {})
            print(f"  => estado={r.get('estado_caso')} prioridad={r.get('prioridad')} plan=v{r.get('version_plan')} "
                  f"pasos={r.get('pasos')} limite={r.get('fecha_limite')}")
        sesiones.append({"fecha": s.get("fecha"), "resumen": final.get("resumen_sesion"), "bitacora": nuevas})
        previo = len(bit)
    final_estado = agente.estado(esc["folio"])
    caso = registro.obtener_caso(esc["folio"])
    return {"escenario": esc["id"], "titulo": esc["titulo"], "folio": esc["folio"], "demuestra": esc.get("demuestra"),
            "esperado": esc.get("esperado"), "sesiones": sesiones,
            "plan_final": [{k: p[k] for k in ("id", "accion", "prioridad", "estado", "origen", "proposito")}
                           for p in final_estado.get("plan", [])],
            "hechos_finales": {k: v for k, v in final_estado.get("hechos", {}).items() if k not in ("normativa",)},
            "registro_oirs": caso}


def cmd_todos(args) -> None:
    agente = _agente()
    EVID_DIR.mkdir(parents=True, exist_ok=True)
    for ruta in sorted(ESCENARIOS_DIR.glob("E*.json")):
        res = correr_escenario(ruta, agente, verbose=not args.silencioso)
        (EVID_DIR / f"{res['escenario']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEvidencias escritas en {EVID_DIR.relative_to(BASE_DIR)}/")


def main(argv=None) -> None:
    for flujo in (sys.stdout, sys.stderr):   # consola de Windows: evitar UnicodeEncodeError con los iconos
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Agente de gestion de casos CESFAM (EP2)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("escenario", help="ejecuta un escenario JSON (una o varias sesiones)")
    e.add_argument("ruta")
    e.add_argument("--json", action="store_true", help="imprime el resultado completo en JSON")
    t = sub.add_parser("todos", help="ejecuta todos los escenarios y guarda evidencias")
    t.add_argument("--silencioso", action="store_true")
    c = sub.add_parser("caso", help="nuevo caso o nueva sesion de un caso existente (mismo folio)")
    c.add_argument("--folio", required=True)
    c.add_argument("--texto", required=True)
    c.add_argument("--fecha")
    c.add_argument("--datos", default="{}", help="JSON con campos del formulario")
    s = sub.add_parser("estado", help="muestra el estado guardado en el checkpoint de un folio")
    s.add_argument("--folio", required=True)
    m = sub.add_parser("memoria", help="busqueda semantica en la memoria de largo plazo")
    m.add_argument("--buscar", required=True)
    sub.add_parser("grafo", help="imprime el grafo en formato Mermaid")
    sub.add_parser("reiniciar", help="borra runtime/ (registro, checkpoints y memoria)")
    a = ap.parse_args(argv)

    if a.cmd == "reiniciar":
        reiniciar_singletons()
        shutil.rmtree(CONFIG_AGENTE.runtime_dir, ignore_errors=True)
        calendario.limpiar_feriados_extra()
        print("runtime/ eliminado")
    elif a.cmd == "escenario":
        res = correr_escenario(Path(a.ruta), verbose=not a.json)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
    elif a.cmd == "todos":
        cmd_todos(a)
    elif a.cmd == "caso":
        final = _agente().procesar(a.folio, a.texto, a.fecha, json.loads(a.datos))
        imprimir_bitacora([x for x in final.get("bitacora", []) if x.get("sesion") == final.get("sesion")])
        print(json.dumps(final.get("resumen_sesion"), ensure_ascii=False, indent=2))
    elif a.cmd == "estado":
        st = _agente().estado(a.folio)
        if not st:
            print("Sin checkpoint para ese folio.")
            return
        print(f"folio={st.get('folio')} sesiones={st.get('sesion')} estado={st.get('estado_caso')} "
              f"prioridad={st.get('prioridad')} plan=v{st.get('version_plan')}")
        for p in st.get("plan", []):
            print(f"  {p['id']:<4} {p['estado']:<11} p{p['prioridad']} {p['accion']:<26} [{p['origen']}] {p['proposito'][:60]}")
        print("\nbitacora:")
        imprimir_bitacora(st.get("bitacora", []))
    elif a.cmd == "memoria":
        mem = memoria()
        for ns in ("casos", "lecciones"):
            print(f"\n[{ns}]")
            for r in mem.search(ns, a.buscar, k=5, umbral=0.0):
                print(f"  {r['similitud']:.3f}  {r['clave']:<36} {r['texto'][:90]}")
    elif a.cmd == "grafo":
        print(_agente().grafo.get_graph().draw_mermaid())


if __name__ == "__main__":
    main()
