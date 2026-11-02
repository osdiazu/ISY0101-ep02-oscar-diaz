"""Estudio de ablacion: aporte de cada componente del recuperador (IL1.4).

Compara tres configuraciones sobre el mismo set dorado:
  A) solo recuperador lexico (BM25)
  B) solo recuperador semantico (denso)
  C) hibrido con Reciprocal Rank Fusion (configuracion productiva)
"""
from __future__ import annotations

import json
import statistics

import numpy as np

from .agent import AgenteDocumental
from .config import EVIDENCIAS_DIR
from .evaluate import SET_DORADO
from .index import tokenizar

CASOS = [(p, d) for p, d, _ in SET_DORADO if d]


def _rank_docs(idx, consulta: str, modo: str, fuentes: set[str], k: int) -> list[str]:
    if modo == "hibrido":
        return [c.doc_id for c, _, _ in idx.buscar(consulta, fuentes)[:k]]
    q = tokenizar(consulta)
    scores = idx.bm25.score(q) if modo == "lexico" else idx.matriz @ idx._vector_consulta(consulta)
    permitidos = [i for i, c in enumerate(idx.chunks) if c.fuente in fuentes]
    orden = sorted(permitidos, key=lambda i: -scores[i])[:k]
    return [idx.chunks[i].doc_id for i in orden]


def ejecutar(k: int = 4) -> dict:
    agente = AgenteDocumental()
    idx = agente.indice
    salida = {}
    for modo in ("lexico", "semantico", "hibrido"):
        hits, rr, prec = [], [], []
        for pregunta, esperado in CASOS:
            ruta = agente.enrutar(pregunta)
            docs = _rank_docs(idx, ruta["reformulacion"], modo, set(ruta["fuentes"]), k)
            hits.append(int(esperado in docs))
            rr.append(1.0 / (docs.index(esperado) + 1) if esperado in docs else 0.0)
            # densidad de evidencia util: cuantos de los k chunks pertenecen al
            # documento correcto (mide ruido enviado a la ventana de contexto)
            prec.append(sum(1 for d in docs if d == esperado) / max(len(docs), 1))
        salida[modo] = {
            f"recall@{k}": round(statistics.mean(hits), 3),
            "mrr": round(statistics.mean(rr), 3),
            f"precision_chunks@{k}": round(statistics.mean(prec), 3),
            "n": len(CASOS),
        }
    EVIDENCIAS_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCIAS_DIR / "ablacion_recuperador.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    return salida


if __name__ == "__main__":
    print(json.dumps(ejecutar(), ensure_ascii=False, indent=2))
