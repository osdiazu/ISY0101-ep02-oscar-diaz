"""Control de contexto y proteccion de datos (Ley 21.719 y politica interna PRO-006).

Antes de que cualquier texto salga hacia el modelo de lenguaje se aplica una capa de
deteccion y enmascaramiento de datos personales. Tambien se validan la longitud del
contexto y el alcance tematico de la consulta.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}\s*[-‐]\s*[\dkK]\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
TELEFONO = re.compile(r"(?:\+56\s?)?(?:9\s?\d{4}\s?\d{4}|\b2\s?\d{3}\s?\d{4}\b)")
FICHA = re.compile(r"\b(?:ficha|n[ºo°]\s?ficha)\s*[:#]?\s*\d{4,}\b", re.IGNORECASE)
NOMBRE = re.compile(
    r"\b(?:paciente|sr\.?|sra\.?|don|do[nñ]a)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})"
)

TEMAS_FUERA_DE_ALCANCE = (
    "diagnostico", "diagnóstico", "que tengo", "qué tengo", "receta para mi",
    "dosis que debo tomar", "me puede recetar", "dosis", "que le indico",
    "tratamiento para el paciente", "interpretar este examen",
)


@dataclass
class ResultadoPII:
    texto: str
    hallazgos: dict
    bloqueado: bool = False
    motivo: str = ""

    @property
    def hubo_pii(self) -> bool:
        return any(self.hallazgos.values())


def anonimizar(texto: str) -> ResultadoPII:
    hallazgos = {"rut": 0, "email": 0, "telefono": 0, "ficha": 0, "nombre": 0}
    out = texto

    def _sub(patron, etiqueta, clave, grupo=0):
        nonlocal out
        encontrados = patron.findall(out)
        hallazgos[clave] += len(encontrados)
        if grupo:
            return patron.sub(lambda m: m.group(0).replace(m.group(grupo), etiqueta), out)
        return patron.sub(etiqueta, out)

    out = _sub(RUT, "[RUT_ANONIMIZADO]", "rut")
    out = _sub(EMAIL, "[EMAIL_ANONIMIZADO]", "email")
    out = _sub(TELEFONO, "[TELEFONO_ANONIMIZADO]", "telefono")
    out = _sub(FICHA, "[FICHA_ANONIMIZADA]", "ficha")
    out = _sub(NOMBRE, "[NOMBRE_ANONIMIZADO]", "nombre", grupo=1)
    return ResultadoPII(texto=out, hallazgos=hallazgos)


def validar_alcance(consulta: str) -> tuple[bool, str]:
    """El asistente es documental: no entrega consejo clinico individual."""
    q = consulta.lower()
    for t in TEMAS_FUERA_DE_ALCANCE:
        if t in q:
            return False, (
                "La consulta solicita orientacion clinica individual. El asistente "
                "responde unicamente sobre protocolos, procedimientos y normativa; "
                "derive al profesional tratante."
            )
    return True, ""


def recortar_contexto(bloques: list[str], max_chars: int) -> list[str]:
    """Control de ventana de contexto: conserva el orden de relevancia y trunca."""
    salida, usado = [], 0
    for b in bloques:
        if usado + len(b) > max_chars:
            restante = max_chars - usado
            if restante > 300:
                salida.append(b[:restante] + "\n[...truncado por control de contexto]")
            break
        salida.append(b)
        usado += len(b)
    return salida
