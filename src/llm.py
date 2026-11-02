"""Capa de acceso al modelo de lenguaje con degradacion controlada.

- Si existe ANTHROPIC_API_KEY y el SDK instalado, se invoca el modelo configurado.
- Si no, se usa un motor extractivo determinista que respeta el mismo contrato de
  salida (respuesta con citas + abstencion). Esto permite ejecutar y evaluar el
  pipeline completo sin credenciales, requisito para la reproducibilidad academica.
"""
from __future__ import annotations

import os
import re
import textwrap

from .config import CONFIG


def _hay_sdk() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


class ClienteLLM:
    def __init__(self, cfg=CONFIG):
        self.cfg = cfg
        self.modo = "api" if _hay_sdk() else "extractivo"

    def completar(self, mensajes: list[dict]) -> str:
        if self.modo == "api":
            return self._api(mensajes)
        return self._extractivo(mensajes)

    # ------------------------------------------------------------------ API
    def _api(self, mensajes: list[dict]) -> str:
        import anthropic
        cliente = anthropic.Anthropic()
        system = "\n\n".join(m["content"] for m in mensajes if m["role"] == "system")
        usuario = [m for m in mensajes if m["role"] != "system"]
        r = cliente.messages.create(
            model=self.cfg.modelo,
            max_tokens=self.cfg.max_tokens_respuesta,
            temperature=self.cfg.temperatura,
            system=system,
            messages=usuario,
        )
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")

    # ----------------------------------------------------------- EXTRACTIVO
    def _extractivo(self, mensajes: list[dict]) -> str:
        """Sintetiza una respuesta citada a partir de la evidencia, sin alucinar."""
        user = mensajes[-1]["content"]
        m_ev = re.search(r"<evidencia>\n(.*?)\n</evidencia>", user, re.S)
        m_q = re.search(r"<consulta_reformulada>\n(.*?)\n</consulta_reformulada>", user, re.S)
        evidencia = m_ev.group(1).strip() if m_ev else ""
        consulta = (m_q.group(1) if m_q else "").strip()

        if not evidencia or "SIN_EVIDENCIA" in evidencia:
            return ("**Respuesta directa:** No cuento con respaldo documental suficiente "
                    "para responder esto.\n\n**Detalle:**\n- Consulte a la unidad responsable "
                    "del procedimiento o solicite la incorporacion del documento al corpus.\n")

        bloques = [b.strip() for b in evidencia.split("\n---\n") if b.strip()]
        terminos = {t for t in re.findall(r"[a-záéíóúñ]{4,}", consulta.lower())}

        puntuados = []
        for b in bloques:
            cita = re.search(r"\[(.*?)\]", b)
            etiqueta = f"[{cita.group(1)}]" if cita else ""
            cuerpo = re.sub(r"^FRAGMENTO.*?\n", "", b).strip()
            # EP2: se elimina tambien la linea "[cita] titulo > seccion" para que no se
            # fusione con la primera oracion del cuerpo.
            cuerpo = re.sub(r"^\[[^\]]*\][^\n]*\n", "", cuerpo).replace("**", "").strip()
            for oracion in re.split(r"(?<=[.])\s+(?=[A-Z0-9-])|\n(?=\s*(?:- |\d+\. ))", cuerpo):
                oracion = " ".join(oracion.split()).lstrip("- ").strip()
                if len(oracion) < 25 or oracion.startswith("["):
                    continue
                score = sum(1 for t in terminos if t in oracion.lower())
                score += 2 if re.search(r"\b\d+\s*(horas|dias|minutos|meses)\b", oracion, re.I) else 0
                puntuados.append((score, oracion, etiqueta))

        puntuados.sort(key=lambda x: -x[0])
        elegidas = [p for p in puntuados[:4] if p[0] > 0]
        if not elegidas:
            return ("**Respuesta directa:** No cuento con respaldo documental suficiente "
                    "para responder esto.\n\n**Detalle:**\n- La evidencia recuperada no cubre "
                    "la consulta; revise el documento fuente o refine la pregunta.\n")

        principal = elegidas[0]
        detalle = "\n".join(f"- {o} {e}" for _, o, e in elegidas)
        fuentes = sorted({e for _, _, e in elegidas if e})
        return (
            f"**Respuesta directa:** {principal[1]} {principal[2]}\n\n"
            f"**Detalle:**\n{detalle}\n\n"
            f"**Fuentes:** {', '.join(fuentes) if fuentes else 'sin etiqueta'}\n\n"
            "**Advertencias:** respuesta generada en modo extractivo determinista (sin clave "
            "de API); el contenido proviene literalmente de la evidencia recuperada.\n"
        )
