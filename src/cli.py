"""Interfaz de linea de comandos del asistente documental.

Uso:
    python -m src.cli --consulta "En cuantas horas se emite el FCIP?"
    python -m src.cli --interactivo
    python -m src.cli --consulta "..." --json
"""
from __future__ import annotations

import argparse
import json

from .agent import AgenteDocumental


def main() -> None:
    ap = argparse.ArgumentParser(description="Asistente documental CESFAM (RAG)")
    ap.add_argument("--consulta", "-c", help="consulta del funcionario")
    ap.add_argument("--interactivo", "-i", action="store_true", help="modo conversacional")
    ap.add_argument("--json", action="store_true", help="imprime la traza completa en JSON")
    args = ap.parse_args()

    agente = AgenteDocumental()
    print(f"[indice: {len(agente.indice.chunks)} chunks | denso: {agente.indice.backend} "
          f"| llm: {agente.llm.modo}]\n")

    def _responder(q: str) -> None:
        r = agente.responder(q)
        if args.json:
            print(json.dumps({"respuesta": r.texto, "traza": r.traza.to_dict()},
                             ensure_ascii=False, indent=2))
        else:
            print(r.texto)
            print(f"\n--- traza: categoria={r.traza.categoria} "
                  f"fuentes={r.traza.fuentes_consultadas} chunks={r.traza.chunks} "
                  f"precision_citas={r.traza.verificacion.get('precision_citas')} "
                  f"latencia={r.traza.latencia_ms}ms ---\n")

    if args.consulta:
        _responder(args.consulta)
    if args.interactivo or not args.consulta:
        print("Escriba su consulta (o 'salir'):")
        while True:
            try:
                q = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q or q.lower() in {"salir", "exit", "quit"}:
                break
            _responder(q)


if __name__ == "__main__":
    main()
