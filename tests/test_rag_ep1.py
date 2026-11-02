"""Pruebas de software del asistente documental CESFAM."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import guardrails  # noqa: E402
from src.agent import AgenteDocumental  # noqa: E402
from src.index import BM25, construir_indice, tokenizar  # noqa: E402
from src.ingest import cargar_corpus  # noqa: E402


@pytest.fixture(scope="module")
def agente():
    return AgenteDocumental()


# --------------------------------------------------------------- INGESTA
def test_corpus_carga_ambas_fuentes():
    chunks = cargar_corpus()
    assert len(chunks) > 20
    assert {"interno", "externo"} == {c.fuente for c in chunks}


def test_chunks_conservan_trazabilidad():
    for c in cargar_corpus():
        assert c.doc_id and c.titulo and c.seccion
        assert c.chunk_id.startswith(c.doc_id)
        assert c.cita().startswith("[") and c.cita().endswith("]")


def test_chunk_respeta_tamano_maximo():
    assert all(len(c.texto) <= 1100 for c in cargar_corpus())


# ------------------------------------------------------------ RECUPERACION
def test_bm25_prioriza_documento_correcto():
    idx = construir_indice()
    top = idx.buscar("plazo de emision del FCIP por sospecha GES")[0][0]
    assert top.doc_id == "PRO-001"


def test_filtro_por_fuente(agente):
    solo_ext = agente.indice.buscar("derechos del paciente", fuentes={"externo"})
    assert all(c.fuente == "externo" for c, _, _ in solo_ext)


def test_bm25_scores_no_negativos():
    b = BM25([tokenizar("plazo de quince dias habiles"), tokenizar("receta cheque notarial")])
    assert (b.score(tokenizar("plazo habiles")) >= 0).all()


# ---------------------------------------------------------------- GUARDRAILS
@pytest.mark.parametrize("texto,clave", [
    ("El paciente 12.345.678-9 pregunta por su hora", "rut"),
    ("Contactar a juan.perez@correo.cl", "email"),
    ("Llamar al +56 9 8765 4321", "telefono"),
    ("Revisar ficha 998877", "ficha"),
    ("Consulta del paciente Juan Perez Soto", "nombre"),
])
def test_anonimizacion_detecta_pii(texto, clave):
    r = guardrails.anonimizar(texto)
    assert r.hallazgos[clave] >= 1
    assert "ANONIMIZA" in r.texto


def test_anonimizacion_no_altera_texto_limpio():
    t = "Cual es el plazo para responder un reclamo OIRS?"
    assert guardrails.anonimizar(t).texto == t


def test_recorte_de_contexto():
    bloques = ["x" * 2000, "y" * 2000, "z" * 2000]
    assert sum(len(b) for b in guardrails.recortar_contexto(bloques, 3000)) <= 3100


def test_fuera_de_alcance_clinico():
    ok, motivo = guardrails.validar_alcance("Que dosis debo indicar?")
    assert not ok and motivo


# --------------------------------------------------------------- AGENTE
def test_router_expande_siglas(agente):
    r = agente.enrutar("Que pasa con el FCIP en una sospecha GES?")
    assert "Formulario de Constancia" in r["reformulacion"]
    assert r["categoria"] in {"interno", "mixto", "externo"}


def test_router_detecta_normativa_externa(agente):
    r = agente.enrutar("Que dice la ley sobre el acceso a la ficha clinica?")
    assert "externo" in r["fuentes"]


def test_respuesta_incluye_citas_validas(agente):
    r = agente.responder("En cuantas horas se emite el FCIP ante sospecha GES?")
    assert r.traza.verificacion["citas_invalidas"] == []
    assert r.traza.verificacion["precision_citas"] == 1.0
    assert "24 horas" in r.texto


def test_agente_se_abstiene_sin_evidencia(agente):
    r = agente.responder("Cual es el presupuesto anual del CESFAM para 2027?")
    assert r.traza.abstenido


def test_agente_no_filtra_pii_en_la_respuesta(agente):
    r = agente.responder("El paciente 12.345.678-9 pregunta el plazo del reclamo OIRS")
    assert not re.search(r"\d{1,2}\.\d{3}\.\d{3}-[\dkK]", r.texto)
    assert r.traza.pii_detectada["rut"] == 1


def test_traza_es_serializable(agente):
    r = agente.responder("Cuanto dura la vigencia de una receta cronica?")
    d = r.traza.to_dict()
    assert d["prompt_version"] and d["chunks_recuperados"] and d["latencia_ms"] >= 0


def test_evidencia_respeta_top_k(agente):
    r = agente.responder("Plazo de respuesta de un reclamo OIRS")
    assert len(r.traza.chunks) <= agente.cfg.top_k_final
