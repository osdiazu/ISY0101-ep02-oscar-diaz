"""Herramientas del agente (IL2.1), expuestas como `langchain_core.tools`.

Se agrupan en tres familias, cada una con un contrato de entrada/salida tipado:

CONSULTA       buscar_normativa, consultar_caso, buscar_casos_similares
RAZONAMIENTO   calcular_plazo, verificar_cumplimiento, evaluar_prioridad,
               verificar_requisitos_ficha
ESCRITURA      registrar_caso, crear_tarea, redactar_documento,
               actualizar_estado_caso

Todas devuelven diccionarios serializables (se guardan en el checkpoint del grafo).
Las herramientas de escritura pasan por el `INYECTOR` de fallas para poder demostrar
reintentos y replanificacion ante errores de infraestructura.
"""
from __future__ import annotations

import re
from datetime import date

from langchain_core.tools import tool

from . import calendario, registro
from .memoria import MemoriaLargoPlazo

# ------------------------------------------------------------------ singletons
_RAG = None
_MEMORIA: MemoriaLargoPlazo | None = None


def rag():
    """Asistente documental de la EP1 (recuperacion hibrida BM25 + denso + RRF)."""
    global _RAG
    if _RAG is None:
        from ..agent import AgenteDocumental

        _RAG = AgenteDocumental()
    return _RAG


def memoria() -> MemoriaLargoPlazo:
    global _MEMORIA
    if _MEMORIA is None:
        _MEMORIA = MemoriaLargoPlazo()
    return _MEMORIA


def reiniciar_singletons() -> None:
    global _MEMORIA
    if _MEMORIA is not None:
        _MEMORIA.cerrar()
    _MEMORIA = None


# ====================================================================== CONSULTA


@tool
def buscar_normativa(consulta: str) -> dict:
    """Busca en protocolos internos del CESFAM y normativa chilena (RAG de la EP1).
    Devuelve la respuesta citada, los documentos usados y si hubo respaldo suficiente."""
    r = rag().responder(consulta)
    t = r.traza
    directa = re.search(r"\*\*Respuesta directa:\*\*\s*(.+)", r.texto)
    citas = sorted(set(re.findall(r"\[([A-Z]{2,5}-[A-Z0-9]+ \|[^\]]*)\]", r.texto)))
    return {
        "respaldo": not t.abstenido and t.categoria != "fuera_de_alcance",
        "respuesta_directa": directa.group(1).strip() if directa else "",
        "respuesta": r.texto,
        "citas": [f"[{c}]" for c in citas],
        "documentos": sorted({c.split(" |")[0] for c in citas}),
        "categoria": t.categoria,
        "chunks": t.chunks,
        "max_bm25": t.verificacion.get("max_bm25"),
        "precision_citas": t.verificacion.get("precision_citas"),
    }


@tool
def consultar_caso(folio: str) -> dict:
    """Consulta en el sistema OIRS el estado, tareas y documentos de un folio."""
    caso = registro.obtener_caso(folio)
    return {"encontrado": caso is not None, "caso": caso or {}}


@tool
def buscar_casos_similares(descripcion: str) -> dict:
    """Recupera de la memoria de largo plazo casos resueltos y lecciones similares."""
    m = memoria()
    return {
        "casos": m.search("casos", descripcion),
        "lecciones": m.search("lecciones", descripcion),
    }


# ================================================================== RAZONAMIENTO


@tool
def calcular_plazo(fecha_inicio: str, dias: int, tipo: str = "habiles") -> dict:
    """Calcula la fecha limite sumando dias habiles (sin fines de semana ni feriados)
    o corridos a una fecha ISO (AAAA-MM-DD)."""
    limite = calendario.sumar_dias(fecha_inicio, dias, tipo)
    return {"fecha_inicio": fecha_inicio, "dias": dias, "tipo": tipo, "fecha_limite": limite}


@tool
def verificar_cumplimiento(fecha_hito: str, dias_plazo: int, fecha_referencia: str,
                           fecha_cumplimiento: str = "") -> dict:
    """Determina si un plazo en dias habiles se cumplio, esta en curso o esta vencido.
    `fecha_cumplimiento` vacia significa que la accion aun no se realiza."""
    if not fecha_hito:
        return {"estado": "sin_datos", "detalle": "No se informo la fecha del hito; no es posible verificar."}
    limite = calendario.sumar_dias(fecha_hito, dias_plazo)
    if fecha_cumplimiento:
        ok = fecha_cumplimiento <= limite
        return {"estado": "cumplido" if ok else "cumplido_fuera_de_plazo", "fecha_limite": limite,
                "dias_habiles_de_atraso": max(0, calendario.dias_habiles_entre(limite, fecha_cumplimiento))}
    if fecha_referencia > limite:
        return {"estado": "incumplido", "fecha_limite": limite,
                "dias_habiles_de_atraso": calendario.dias_habiles_entre(limite, fecha_referencia)}
    return {"estado": "en_plazo", "fecha_limite": limite,
            "dias_habiles_restantes": calendario.dias_habiles_entre(fecha_referencia, limite)}


PESOS_BANDERA = {"negligencia": 5, "trato": 4, "ges": 3, "incumplimiento_ges": 4,
                 "mayor_80": 2, "discapacidad": 2, "embarazo": 2, "sin_contacto": 1}


@tool
def evaluar_prioridad(tipo: str, banderas: list[str], fecha_referencia: str,
                      fecha_limite: str = "", edad: int = 0) -> dict:
    """Calcula la prioridad del caso (critica/alta/media/baja) con puntaje explicable,
    segun tipo, banderas de riesgo, holgura del plazo y criterios de PRO-007 (sec. 4)."""
    razones, puntos = [], {"reclamo": 2, "solicitud_ficha": 1, "rescate_nsp": 2, "consulta": 0}.get(tipo, 0)
    razones.append(f"base por tipo '{tipo}' = {puntos}")
    banderas = list(banderas)
    if edad >= 80 and "mayor_80" not in banderas:
        banderas.append("mayor_80")
    for b in banderas:
        if b in PESOS_BANDERA:
            puntos += PESOS_BANDERA[b]
            razones.append(f"+{PESOS_BANDERA[b]} por '{b}'")
    if fecha_limite:
        holgura = calendario.dias_habiles_entre(fecha_referencia, fecha_limite)
        if holgura <= 3:
            puntos += 2
            razones.append(f"+2 por holgura de {holgura} dias habiles")
    nivel = "critica" if puntos >= 7 else "alta" if puntos >= 5 else "media" if puntos >= 3 else "baja"
    return {"nivel": nivel, "puntaje": puntos, "razones": razones}


REQUISITOS_FICHA = {
    "titular": ["cedula_identidad"],
    "representante_legal": ["cedula_identidad", "acredita_representacion"],
    "tercero": ["cedula_identidad", "mandato_notarial"],
    "tribunal": ["oficio_judicial"],
}


@tool
def verificar_requisitos_ficha(solicitante: str, antecedentes: list[str]) -> dict:
    """Verifica si quien pide copia de ficha clinica cumple los requisitos de PRO-006
    (sec. 2) y lista los antecedentes que faltan."""
    req = REQUISITOS_FICHA.get(solicitante)
    if req is None:
        return {"cumple": False, "faltantes": ["calidad_de_solicitante_no_reconocida"],
                "fundamento": "PRO-006 sec. 2 solo admite titular, representante legal, tercero con mandato o tribunal."}
    faltan = [r for r in req if r not in antecedentes]
    return {"cumple": not faltan, "faltantes": faltan, "requeridos": req,
            "fundamento": "PRO-006 v2.2, sec. 2 'Quien puede solicitar copia'."}


# ====================================================================== ESCRITURA


@tool
def registrar_caso(folio: str, tipo: str, fecha_ingreso: str, resumen: str,
                   prioridad: str = "media", fecha_limite: str = "") -> dict:
    """Registra o actualiza el caso en el sistema OIRS (escritura transaccional)."""
    registro.INYECTOR.verificar("registrar_caso")
    caso = registro.upsert_caso(folio, tipo=tipo, estado="abierto", prioridad=prioridad,
                                fecha_ingreso=fecha_ingreso, fecha_limite=fecha_limite or None,
                                resumen=resumen, actualizado=fecha_ingreso)
    return {"ok": True, "caso": caso}


@tool
def crear_tarea(folio: str, unidad: str, descripcion: str, fecha_limite: str,
                prioridad: str, fecha: str) -> dict:
    """Crea una tarea de derivacion o seguimiento para una unidad del CESFAM."""
    registro.INYECTOR.verificar("crear_tarea")
    tid = registro.insertar_tarea(folio, unidad, descripcion, fecha_limite, prioridad, fecha)
    return {"ok": True, "tarea_id": tid, "unidad": unidad, "fecha_limite": fecha_limite}


@tool
def actualizar_estado_caso(folio: str, estado: str, fecha: str, nota: str = "",
                           prioridad: str = "", cerrar_tareas_con: str = "") -> dict:
    """Cambia el estado del caso (abierto, pendiente_antecedentes, en_seguimiento,
    derivado, escalado, respondido, cerrado) y opcionalmente cierra tareas."""
    registro.INYECTOR.verificar("actualizar_estado_caso")
    cerradas = registro.cerrar_tareas(folio, cerrar_tareas_con) if cerrar_tareas_con else 0
    caso = registro.upsert_caso(folio, estado=estado, actualizado=fecha, prioridad=prioridad or None)
    registro.registrar_evento(folio, fecha, {"estado": estado, "nota": nota})
    return {"ok": True, "estado": estado, "tareas_cerradas": cerradas, "caso": caso}


@tool
def redactar_documento(folio: str, tipo_documento: str, fecha: str, contexto: dict) -> dict:
    """Redacta y archiva un documento del caso (respuesta OIRS, solicitud de
    antecedentes, acuse de derivacion o minuta de escalamiento)."""
    registro.INYECTOR.verificar("redactar_documento")
    plantilla = PLANTILLAS.get(tipo_documento)
    if plantilla is None:
        raise ValueError(f"tipo de documento no soportado: {tipo_documento}")
    contenido = plantilla(folio, fecha, contexto)
    ruta = registro.guardar_documento(folio, tipo_documento, contenido, fecha)
    return {"ok": True, "ruta": ruta, "tipo_documento": tipo_documento, "caracteres": len(contenido)}


# ------------------------------------------------------------ plantillas de redaccion


def _fmt(f: str) -> str:
    return date.fromisoformat(f).strftime("%d-%m-%Y") if f else "(sin fecha)"


def _fundamentos(ctx: dict) -> str:
    lineas = []
    for n in ctx.get("normativa", []):
        if n.get("respuesta_directa"):
            lineas.append(f"- {n['respuesta_directa']}")
    return "\n".join(lineas) or "- (sin fundamento documental recuperado)"


def _respuesta_oirs(folio, fecha, ctx) -> str:
    medidas = "\n".join(f"- {m}" for m in ctx.get("medidas", [])) or "- Sin medidas adicionales."
    apelacion = ("Si no esta conforme con esta respuesta, puede recurrir a la Superintendencia de Salud "
                 "o a la Direccion del Servicio de Salud, adjuntando el folio de esta respuesta.")
    if ctx.get("ges"):
        apelacion += (" Por tratarse de una garantia explicita en salud (GES), puede reclamar su "
                      "cumplimiento ante su asegurador (FONASA o Isapre) y ante la Superintendencia de Salud.")
    return f"""# Respuesta a solicitud ciudadana - Folio {folio}

**Fecha de ingreso:** {_fmt(ctx.get('fecha_ingreso', ''))}  |  **Fecha de respuesta:** {_fmt(fecha)}  |  **Plazo comprometido:** {_fmt(ctx.get('fecha_limite', ''))}

## 1. Identificacion
Folio {folio}, tipo de solicitud: {ctx.get('tipo', 'reclamo')}.

## 2. Sintesis de lo planteado
{ctx.get('sintesis', '')}

## 3. Antecedentes recabados
{ctx.get('antecedentes', 'Se revisaron los registros del caso y la documentacion institucional vigente.')}

## 4. Respuesta de fondo y fundamento
{_fundamentos(ctx)}

## 5. Medidas adoptadas y responsable
{medidas}

## 6. Via de apelacion
{apelacion}

---
*Borrador generado por el Agente de Gestion de Casos CESFAM para revision y firma de la
jefatura OIRS. Fuentes: {', '.join(ctx.get('citas', [])) or 'sin citas'}.*
"""


def _solicitud_antecedentes(folio, fecha, ctx) -> str:
    falt = "\n".join(f"- {f.replace('_', ' ')}" for f in ctx.get("faltantes", []))
    return f"""# Solicitud de antecedentes - Folio {folio}

**Fecha:** {_fmt(fecha)}

Para dar curso a su solicitud de copia de ficha clinica, y conforme a la politica interna
de proteccion de datos (PRO-006, seccion 2), necesitamos que presente los siguientes
antecedentes:

{falt}

El plazo de entrega de 5 dias habiles comenzara a contar desde la recepcion de la
solicitud formal completa.

*Fundamento: {ctx.get('fundamento', 'PRO-006')}*
"""


def _acuse_derivacion(folio, fecha, ctx) -> str:
    return f"""# Acuse de recibo y derivacion - Folio {folio}

**Fecha:** {_fmt(fecha)}  |  **Plazo de respuesta:** {_fmt(ctx.get('fecha_limite', ''))}

Hemos recibido su consulta. La documentacion institucional disponible no contiene
respaldo suficiente para responderla de forma verificable, por lo que fue derivada a
**{ctx.get('unidad', 'la unidad responsable')}**, que le respondera dentro del plazo indicado.

*El asistente se abstuvo de responder sin respaldo documental (politica de abstencion).*
"""


def _minuta_escalamiento(folio, fecha, ctx) -> str:
    motivos = "\n".join(f"- {m}" for m in ctx.get("motivos", []))
    return f"""# Minuta de escalamiento - Folio {folio}

**Fecha:** {_fmt(fecha)}  |  **Prioridad:** {ctx.get('prioridad', 'alta').upper()}
**Destinatarios:** {', '.join(ctx.get('destinatarios', []))}

## Motivo
{motivos}

## Fundamento
{_fundamentos(ctx)}

## Accion requerida
{ctx.get('accion', 'Revisar el caso y adoptar medidas el mismo dia.')}
"""


def _respuesta_ficha(folio, fecha, ctx) -> str:
    return f"""# Respuesta a solicitud de copia de ficha clinica - Folio {folio}

**Fecha:** {_fmt(fecha)}

Su solicitud cumple los requisitos de PRO-006. La copia se entregara a mas tardar el
**{_fmt(ctx.get('fecha_limite', ''))}** (5 dias habiles desde la solicitud formal completa del
{_fmt(ctx.get('fecha_solicitud_completa', ''))}), en formato digital cifrado o impreso con cargo de retiro.

## Fundamento
{_fundamentos(ctx)}
"""


def _respuesta_consulta(folio, fecha, ctx) -> str:
    return f"""# Respuesta a consulta - Folio {folio}

**Fecha:** {_fmt(fecha)}  |  **Plazo comprometido:** {_fmt(ctx.get('fecha_limite', ''))}

## Respuesta
{_fundamentos(ctx)}

*Fuentes: {', '.join(ctx.get('citas', []))}*
"""


PLANTILLAS = {
    "respuesta_oirs": _respuesta_oirs,
    "solicitud_antecedentes": _solicitud_antecedentes,
    "acuse_derivacion": _acuse_derivacion,
    "minuta_escalamiento": _minuta_escalamiento,
    "respuesta_ficha": _respuesta_ficha,
    "respuesta_consulta": _respuesta_consulta,
}

# ================================================================ catalogo de tools

CATALOGO = {t.name: t for t in [
    buscar_normativa, consultar_caso, buscar_casos_similares,
    calcular_plazo, verificar_cumplimiento, evaluar_prioridad, verificar_requisitos_ficha,
    registrar_caso, crear_tarea, actualizar_estado_caso, redactar_documento,
]}

FAMILIA = {
    "buscar_normativa": "consulta", "consultar_caso": "consulta", "buscar_casos_similares": "consulta",
    "calcular_plazo": "razonamiento", "verificar_cumplimiento": "razonamiento",
    "evaluar_prioridad": "razonamiento", "verificar_requisitos_ficha": "razonamiento",
    "registrar_caso": "escritura", "crear_tarea": "escritura",
    "actualizar_estado_caso": "escritura", "redactar_documento": "escritura",
}
