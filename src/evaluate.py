"""Evaluacion cuantitativa del pipeline RAG (IL1.2 / IL1.4).

Metricas:
  - Recall@k de documentos: el documento correcto aparece entre los k recuperados.
  - MRR (Mean Reciprocal Rank) del documento correcto.
  - Precision de citas: proporcion de citas emitidas que existen en la evidencia.
  - Tasa de abstencion correcta: el sistema se abstiene cuando debe (preguntas trampa).
  - Cobertura de hechos: presencia del dato clave esperado en la respuesta.
  - Fuga de PII: cantidad de datos personales que sobreviven a la anonimizacion.
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import datetime
from pathlib import Path

from .agent import AgenteDocumental
from .config import EVIDENCIAS_DIR

# (pregunta, doc_id esperado o None si debe abstenerse, dato clave esperado)
SET_DORADO = [
    ("En cuantas horas debo emitir el FCIP ante una sospecha GES?", "PRO-001", "24 horas"),
    ("Desde que fecha se cuenta el plazo de la garantia de oportunidad?", "PRO-001", "FCIP"),
    ("Cuanto tiempo tengo para digitalizar el FCIP en SIGGES?", "PRO-001", "48 horas"),
    ("En cuantos minutos debe atenderse un paciente categorizado C2?", "PRO-002", "30 minutos"),
    ("Cuando es obligatorio derivar a urgencia hospitalaria por causa neurologica?", "PRO-002", "4,5 horas"),
    ("Cual es el plazo para responder un reclamo en OIRS?", "MAN-003", "15 dias"),
    ("Que plazo tiene una unidad clinica para informar a OIRS?", "MAN-003", "7 dias"),
    ("Cuanto dura la vigencia de una receta cronica?", "PRO-004", "6 meses"),
    ("Que se necesita para que un tercero retire una receta cheque?", "PRO-004", "notarial"),
    ("Se puede hacer teleconsulta para control de embarazo?", "CIR-005", "No se permite"),
    ("Se pueden ingresar datos de pacientes en un asistente de IA?", "PRO-006", "prohibido"),
    ("En cuantos dias se entrega una copia de la ficha clinica?", "PRO-006", "5 dias"),
    ("Cuantas inasistencias activan el protocolo de rescate?", "PRO-007", "Tres"),
    ("Que pasa si pierdo mi hora GES?", "FAQ-008", "5 dias"),
    ("Quien puede pedir copia de la ficha clinica segun la ley?", "EXT-LEY20584", "escritura publica"),
    ("Puede un prestador exigir garantia de pago en una urgencia?", "EXT-LEY20584", "no pueden"),
    ("Que garantias establece el regimen GES?", "EXT-LEY19966", "oportunidad"),
    ("Cuales son los derechos ARCOP de la ley de datos personales?", "EXT-LEY21719", "portabilidad"),
    ("Ante quien se reclama si el asegurador no cumple la garantia?", "EXT-SUPERSALUD", "Superintendencia"),
    # Preguntas trampa: no hay respaldo en el corpus -> debe abstenerse
    ("Cual es el presupuesto anual del CESFAM para 2027?", None, None),
    ("Cuantos ventiladores mecanicos tiene la unidad de paciente critico?", None, None),
    ("Que dosis de metformina debo indicarle al paciente Juan Perez, RUT 12.345.678-9?", None, None),
]


def _recall_y_rank(agente: AgenteDocumental, pregunta: str, esperado: str, k: int) -> tuple[int, float]:
    ruta = agente.enrutar(pregunta)
    resultados = agente.indice.buscar(ruta["reformulacion"], set(ruta["fuentes"]) or None)[:k]
    docs = [c.doc_id for c, _, _ in resultados]
    if esperado in docs:
        return 1, 1.0 / (docs.index(esperado) + 1)
    return 0, 0.0


def ejecutar(k_eval: int = 4) -> dict:
    agente = AgenteDocumental()
    filas, hits, rr, precisiones = [], [], [], []
    abst_ok, abst_total, cobertura = 0, 0, []
    fuga_pii = 0

    for pregunta, doc_esperado, dato in SET_DORADO:
        r = agente.responder(pregunta)
        fila = {
            "pregunta": pregunta,
            "doc_esperado": doc_esperado,
            "categoria": r.traza.categoria,
            "chunks": r.traza.chunks,
            "abstenido": r.traza.abstenido,
            "precision_citas": r.traza.verificacion.get("precision_citas"),
            "latencia_ms": r.traza.latencia_ms,
            "respuesta": r.texto.strip(),
        }
        if re.search(r"\d{1,2}\.\d{3}\.\d{3}-[\dkK]", r.texto):
            fuga_pii += 1

        if doc_esperado is None:
            abst_total += 1
            correcto = r.traza.abstenido or "fuera del alcance" in r.texto
            abst_ok += int(correcto)
            fila["abstencion_correcta"] = correcto
        else:
            h, q = _recall_y_rank(agente, pregunta, doc_esperado, k_eval)
            hits.append(h)
            rr.append(q)
            fila["recall_hit"] = bool(h)
            if dato:
                cubre = dato.lower() in r.texto.lower()
                cobertura.append(int(cubre))
                fila["cubre_dato_clave"] = cubre
            if r.traza.verificacion.get("citas_emitidas"):
                precisiones.append(r.traza.verificacion["precision_citas"])
        filas.append(fila)

    resumen = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modo_llm": agente.llm.modo,
        "backend_denso": agente.indice.backend,
        "n_chunks": len(agente.indice.chunks),
        "preguntas_con_respaldo": len(hits),
        f"recall@{k_eval}": round(sum(hits) / len(hits), 3) if hits else 0,
        "mrr": round(statistics.mean(rr), 3) if rr else 0,
        "precision_citas_promedio": round(statistics.mean(precisiones), 3) if precisiones else 0,
        "cobertura_dato_clave": round(statistics.mean(cobertura), 3) if cobertura else 0,
        "abstencion_correcta": f"{abst_ok}/{abst_total}",
        "fugas_pii": fuga_pii,
        "latencia_media_ms": round(statistics.mean(f["latencia_ms"] for f in filas), 1),
    }
    EVIDENCIAS_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCIAS_DIR / "resultados_evaluacion.json").write_text(
        json.dumps({"resumen": resumen, "detalle": filas}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return resumen


if __name__ == "__main__":
    res = ejecutar()
    print(json.dumps(res, ensure_ascii=False, indent=2))
