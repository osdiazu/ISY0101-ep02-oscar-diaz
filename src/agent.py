"""Agente orquestador del asistente documental (IL1.3).

Flujo:
  consulta -> guardrail PII/alcance -> router de intencion -> herramientas de
  recuperacion (interna / externa) -> fusion y control de contexto -> generacion
  con citas -> verificacion de fidelidad -> traza auditable.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date

from . import guardrails
from .config import CONFIG, RAGConfig
from .index import IndiceHibrido, construir_indice
from .llm import ClienteLLM
from .prompts import PROMPT_VERSION, SYSTEM_ROUTER, construir_mensajes

SIGLAS = {
    "ges": "Garantias Explicitas en Salud (GES)",
    "sic": "solicitud de interconsulta (SIC)",
    "oirs": "Oficina de Informaciones, Reclamos y Sugerencias (OIRS)",
    "sapu": "Servicio de Atencion Primaria de Urgencia (SAPU)",
    "nsp": "inasistencia del paciente (NSP)",
    "fcip": "Formulario de Constancia de Informacion al Paciente GES (FCIP)",
    "some": "Servicio de Orientacion Medica y Estadistica (SOME)",
}

PISTAS_EXTERNO = ("ley", "superintendencia", "normativa", "derecho", "minsal",
                  "fiscaliza", "sancion", "reclamo ante", "legal")
PISTAS_INTERNO = ("protocolo", "procedimiento", "circular", "interno", "aqui",
                  "cesfam", "quien firma", "formulario", "registro", "agenda",
                  "farmacia", "oirs", "sapu")


@dataclass
class Traza:
    consulta_original: str
    consulta_anonimizada: str
    pii_detectada: dict
    categoria: str
    reformulacion: str
    fuentes_consultadas: list
    chunks: list = field(default_factory=list)
    scores: list = field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    modo_llm: str = ""
    latencia_ms: int = 0
    abstenido: bool = False
    verificacion: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "consulta_original": self.consulta_original,
            "consulta_anonimizada": self.consulta_anonimizada,
            "pii_detectada": self.pii_detectada,
            "categoria": self.categoria,
            "reformulacion": self.reformulacion,
            "fuentes_consultadas": self.fuentes_consultadas,
            "chunks_recuperados": self.chunks,
            "scores": self.scores,
            "prompt_version": self.prompt_version,
            "modo_llm": self.modo_llm,
            "latencia_ms": self.latencia_ms,
            "abstenido": self.abstenido,
            "verificacion": self.verificacion,
        }


@dataclass
class Respuesta:
    texto: str
    traza: Traza


class AgenteDocumental:
    def __init__(self, indice: IndiceHibrido | None = None, cfg: RAGConfig = CONFIG):
        self.cfg = cfg
        self.indice = indice or construir_indice(cfg)
        self.llm = ClienteLLM(cfg)

    # ------------------------------------------------------------- ROUTER
    def enrutar(self, consulta: str) -> dict:
        """Router heuristico deterministico; con API disponible se delega al LLM."""
        if self.llm.modo == "api":
            try:
                salida = self.llm.completar([
                    {"role": "system", "content": SYSTEM_ROUTER},
                    {"role": "user", "content": consulta},
                ])
                return json.loads(re.search(r"\{.*\}", salida, re.S).group(0))
            except Exception:
                pass  # degradacion a heuristica

        q = consulta.lower()
        ok, _ = guardrails.validar_alcance(consulta)
        if not ok:
            return {"categoria": "fuera_de_alcance", "fuentes": [],
                    "reformulacion": consulta, "justificacion": "consejo clinico individual"}
        ext = any(p in q for p in PISTAS_EXTERNO)
        inte = any(p in q for p in PISTAS_INTERNO)
        if ext and inte:
            cat, fuentes = "mixto", ["interno", "externo"]
        elif ext:
            cat, fuentes = "externo", ["externo", "interno"]
        else:
            cat, fuentes = "interno", ["interno", "externo"] if self.cfg.incluir_externos_por_defecto else ["interno"]

        reform = consulta
        for sigla, expansion in SIGLAS.items():
            if re.search(rf"\b{sigla}\b", reform, re.I):
                reform = re.sub(rf"\b{sigla}\b", expansion, reform, flags=re.I)
        return {"categoria": cat, "fuentes": fuentes, "reformulacion": reform,
                "justificacion": "clasificacion lexica por pistas de dominio"}

    # -------------------------------------------------------- RECUPERACION
    def recuperar(self, consulta: str, fuentes: list[str]):
        resultados = self.indice.buscar(consulta, fuentes=set(fuentes) if fuentes else None)
        return resultados[: self.cfg.top_k_final]

    @staticmethod
    def formatear_evidencia(resultados) -> str:
        bloques = []
        for n, (c, score, det) in enumerate(resultados, 1):
            vigencia = f"vigente {c.vigencia_desde} a {c.vigencia_hasta}" if c.vigencia_hasta else "fuente externa"
            bloques.append(
                f"FRAGMENTO {n} | fuente={c.fuente} | {vigencia} | score={score:.4f}\n"
                f"{c.cita()} {c.titulo} > {c.seccion}\n{c.texto}"
            )
        return "\n---\n".join(bloques)

    # ------------------------------------------------------- VERIFICACION
    @staticmethod
    def verificar_citas(texto: str, resultados) -> dict:
        etiquetas_validas = {c.cita() for c, _, _ in resultados}
        ids_validos = {c.doc_id for c, _, _ in resultados}
        citadas = set(re.findall(r"\[[^\]\n]{3,90}\]", texto))
        inventadas = [
            e for e in citadas
            if e not in etiquetas_validas and not any(i in e for i in ids_validos)
            and "ANONIMIZADO" not in e and "truncado" not in e
        ]
        return {
            "citas_emitidas": len(citadas),
            "citas_validas": len(citadas) - len(inventadas),
            "citas_invalidas": inventadas,
            "precision_citas": (len(citadas) - len(inventadas)) / len(citadas) if citadas else 0.0,
        }

    # ----------------------------------------------------------- PIPELINE
    def responder(self, consulta: str) -> Respuesta:
        t0 = time.time()
        pii = guardrails.anonimizar(consulta) if self.cfg.anonimizar_consulta else guardrails.ResultadoPII(consulta, {})
        q = pii.texto

        ruta = self.enrutar(q)
        traza = Traza(
            consulta_original=consulta,
            consulta_anonimizada=q,
            pii_detectada=pii.hallazgos,
            categoria=ruta["categoria"],
            reformulacion=ruta["reformulacion"],
            fuentes_consultadas=ruta["fuentes"],
            modo_llm=self.llm.modo,
        )

        if ruta["categoria"] == "fuera_de_alcance":
            traza.abstenido = True
            traza.latencia_ms = int((time.time() - t0) * 1000)
            _, motivo = guardrails.validar_alcance(consulta)
            return Respuesta(
                "**Respuesta directa:** Esta consulta esta fuera del alcance del asistente.\n\n"
                f"**Detalle:**\n- {motivo or 'Solo se responden consultas documentales y normativas.'}\n",
                traza,
            )

        resultados = self.recuperar(ruta["reformulacion"], ruta["fuentes"])
        traza.chunks = [c.chunk_id for c, _, _ in resultados]
        traza.scores = [round(s, 5) for _, s, _ in resultados]

        # Gate de confianza: sin anclaje lexico suficiente el agente se abstiene
        # en lugar de forzar una respuesta sobre evidencia debil (anti-alucinacion).
        max_bm25 = max((d["bm25"] for _, _, d in resultados), default=0.0)
        traza.verificacion["max_bm25"] = round(max_bm25, 3)
        if not resultados or max_bm25 < self.cfg.umbral_bm25:
            evidencia = "SIN_EVIDENCIA"
        else:
            bloques = self.formatear_evidencia(resultados).split("\n---\n")
            evidencia = "\n---\n".join(guardrails.recortar_contexto(bloques, self.cfg.max_chars_contexto))

        mensajes = construir_mensajes(q, ruta["reformulacion"], evidencia, date.today().isoformat())
        texto = self.llm.completar(mensajes)

        traza.verificacion = self.verificar_citas(texto, resultados)
        traza.abstenido = "No cuento con respaldo documental suficiente" in texto
        traza.latencia_ms = int((time.time() - t0) * 1000)
        return Respuesta(texto, traza)


if __name__ == "__main__":
    a = AgenteDocumental()
    r = a.responder("En cuanto tiempo hay que emitir el FCIP cuando hay sospecha GES?")
    print(r.texto)
    print(json.dumps(r.traza.to_dict(), ensure_ascii=False, indent=2))
