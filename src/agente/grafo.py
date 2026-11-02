"""Orquestacion del agente con LangGraph (IL2.1 - IL2.3).

Grafo de estados (ver docs/orquestacion.png):

    START -> ingreso -> recuperar_contexto -> planificar -> ejecutar -> evaluar
                                                  ^             ^          |
                                                  |  replanificar|  continuar
                                                  +-------------+----------+
                                                                           | cerrar
                                                                        cierre -> END

- ingreso            anonimiza (guardrail EP1), clasifica o, si el caso ya existe en el
                     checkpoint, interpreta el mensaje nuevo como evento de la sesion.
- recuperar_contexto memoria de largo plazo: casos y lecciones semanticamente similares.
- planificar         plan inicial (plantilla + memoria) y replanificacion por eventos.
- ejecutar           elige el siguiente paso (prioridad + dependencias) e invoca la tool.
- evaluar            convierte el resultado en eventos y decide la siguiente arista.
- cierre             compacta la memoria de trabajo y consolida la memoria de largo plazo.

El estado completo se persiste por `thread_id = folio` con el checkpointer, por lo que
un caso puede atravesar varias sesiones (dias) sin perder continuidad.
"""
from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .. import guardrails
from . import calendario, planificador
from .config_agente import CONFIG_AGENTE, ConfigAgente
from .herramientas import CATALOGO, FAMILIA, memoria
from .memoria import RESET, compactar_bitacora, crear_checkpointer, reducer_bitacora

NIVELES = ["baja", "media", "alta", "critica"]


class EstadoCaso(TypedDict, total=False):
    folio: str
    mensajes: Annotated[list[dict], operator.add]     # entradas de cada sesion (append)
    sesion: int
    fecha_actual: str
    texto: str                                        # texto anonimizado acumulado
    datos: dict                                       # campos estructurados del formulario
    pii: dict
    clasificacion: dict
    prioridad: str
    plan: list[dict]
    version_plan: int
    ultimo_paso: str
    resultados: dict
    hechos: dict                                      # memoria de trabajo consolidada
    eventos_pendientes: list[dict]
    eventos_historial: list[dict]
    estado_caso: str
    esperando: str
    medidas: list[str]
    memoria_recuperada: dict
    reintentos: dict
    iteraciones: int
    bitacora: Annotated[list[dict], reducer_bitacora]  # memoria episodica de corto plazo
    resumen_contexto: str
    resumen_sesion: dict


def _log(estado, nodo, tipo, detalle):
    return {"sesion": estado.get("sesion", 1), "fecha": estado.get("fecha_actual", ""),
            "nodo": nodo, "tipo": tipo, "detalle": detalle}


def _max_nivel(a: str, b: str) -> str:
    return max(a or "baja", b or "baja", key=lambda n: NIVELES.index(n) if n in NIVELES else 0)


# ============================================================================ nodos


def nodo_ingreso(estado: EstadoCaso) -> dict:
    msg = estado["mensajes"][-1]
    fecha = msg.get("fecha") or date.today().isoformat()
    pii = guardrails.anonimizar(msg.get("texto", ""))
    datos = dict(estado.get("datos", {}))
    datos.update(msg.get("datos", {}))
    hechos = dict(estado.get("hechos", {}))
    for f in hechos.get("feriados_extra", []):         # condiciones persistidas del caso
        calendario.agregar_feriado(f)

    base = {"fecha_actual": fecha, "datos": datos, "iteraciones": 0,
            "sesion": estado.get("sesion", 0) + 1, "pii": pii.hallazgos}

    if not estado.get("plan"):                          # ---- caso nuevo
        c = planificador.clasificar(pii.texto, datos)
        hechos.update({"fecha_ingreso": fecha, "fecha_solicitud_completa": fecha})
        log = [_log({**estado, **base}, "ingreso", "decision",
                    f"caso nuevo clasificado como '{c['tipo']}' banderas={c['banderas']} "
                    f"PII anonimizada={ {k: v for k, v in pii.hallazgos.items() if v} }")]
        return {**base, "texto": pii.texto, "clasificacion": c, "hechos": hechos, "prioridad": "media",
                "estado_caso": "abierto", "esperando": "", "medidas": [], "resultados": {}, "reintentos": {},
                "eventos_pendientes": [], "eventos_historial": [], "version_plan": 0, "bitacora": log}

    # ---- caso existente: el checkpoint restauro el estado; el mensaje es un evento
    eventos = []
    nuevos = msg.get("datos", {})
    if "antecedentes" in nuevos:
        eventos.append({"tipo": "antecedentes_recibidos", "detalle": f"antecedentes: {nuevos['antecedentes']}"})
    if "resultado_llamada" in nuevos:
        eventos.append({"tipo": "resultado_llamada", "valor": nuevos["resultado_llamada"],
                        "detalle": f"resultado de la llamada: {nuevos['resultado_llamada']}"})
    if "feriado_nuevo" in nuevos:
        calendario.agregar_feriado(nuevos["feriado_nuevo"])
        hechos["feriados_extra"] = sorted(set(hechos.get("feriados_extra", [])) | {nuevos["feriado_nuevo"]})
        eventos.append({"tipo": "feriado_agregado", "valor": nuevos["feriado_nuevo"],
                        "detalle": f"se decreta feriado el {nuevos['feriado_nuevo']}"})
    texto = estado.get("texto", "") + ("\n" + pii.texto if pii.texto else "")
    log = [_log({**estado, **base}, "ingreso", "decision",
                f"sesion {base['sesion']}: se retoma el caso desde el checkpoint (estado previo "
                f"'{estado.get('estado_caso')}', plan v{estado.get('version_plan')}, "
                f"{len(estado.get('bitacora', []))} entradas en bitacora); eventos={[e['tipo'] for e in eventos]}")]
    return {**base, "texto": texto, "hechos": hechos, "eventos_pendientes": eventos, "bitacora": log}


def nodo_recuperar_contexto(estado: EstadoCaso) -> dict:
    if estado.get("sesion", 1) > 1:                     # solo al abrir el caso
        return {}
    m = memoria()
    consulta = f"{estado['clasificacion']['tipo']}: {estado['texto']}"
    rec = {"casos": m.search("casos", consulta, excluir=estado["folio"]),
           "lecciones": m.search("lecciones", consulta, excluir=estado["folio"])}
    det = (f"memoria largo plazo: {len(rec['casos'])} casos y {len(rec['lecciones'])} lecciones similares"
           + (f" (mejor: {rec['casos'][0]['clave']} sim={rec['casos'][0]['similitud']})" if rec["casos"] else ""))
    hechos = dict(estado.get("hechos", {}))
    hechos["casos_similares"] = [c["clave"] for c in rec["casos"]]
    return {"memoria_recuperada": rec, "hechos": hechos, "bitacora": [_log(estado, "recuperar_contexto", "memoria", det)]}


def nodo_planificar(estado: EstadoCaso) -> dict:
    upd: dict[str, Any] = {}
    log = []
    plan = estado.get("plan") or []
    version = estado.get("version_plan", 0)
    if not plan:
        plan, notas = planificador.plan_inicial(estado["clasificacion"], estado.get("datos", {}),
                                                estado.get("memoria_recuperada"))
        version = 1
        log.append(_log(estado, "planificar", "plan", f"plan v1: {'; '.join(notas)} -> "
                        + " > ".join(f"{p['id']}:{p['accion']}(p{p['prioridad']})" for p in plan)))
    hechos = dict(estado.get("hechos", {}))
    clasif = dict(estado.get("clasificacion", {}))
    historial = list(estado.get("eventos_historial", []))
    medidas = list(estado.get("medidas", []))
    prioridad = estado.get("prioridad", "media")
    st = dict(estado)
    for ev in estado.get("eventos_pendientes", []):
        plan, cambios, u = planificador.replanificar(plan, ev, {**st, "plan": plan})
        version += 1
        historial.append({**ev, "sesion": estado.get("sesion"), "fecha": estado.get("fecha_actual")})
        log.append(_log(estado, "planificar", "evento", f"{ev['tipo']}: {ev['detalle']}"))
        log.append(_log(estado, "planificar", "replan", f"plan v{version} por '{ev['tipo']}': " + " | ".join(cambios)))
        hechos.update(u.get("hechos", {}))
        medidas += [m for m in u.get("medidas", []) if m not in medidas]
        if "prioridad" in u:
            prioridad = _max_nivel(prioridad, u["prioridad"])
        if ev["tipo"] in ("incumplimiento_ges", "sin_respaldo", "escalamiento_inmediato"):
            clasif["banderas"] = sorted(set(clasif.get("banderas", [])) | {ev["tipo"]})
        clasif["banderas"] = sorted(set(clasif.get("banderas", [])) | set(u.get("banderas_extra", [])))
        for k in ("estado_caso", "esperando"):
            if k in u:
                upd[k] = u[k]
        if u.get("ges"):
            hechos["ges"] = True
    upd.update({"plan": plan, "version_plan": version, "eventos_pendientes": [], "eventos_historial": historial,
                "hechos": hechos, "clasificacion": clasif, "medidas": medidas, "prioridad": prioridad, "bitacora": log})
    return upd


def _resolver(valor, estado: dict):
    if isinstance(valor, dict):
        return {k: _resolver(v, estado) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_resolver(v, estado) for v in valor]
    if not (isinstance(valor, str) and valor.startswith("$")):
        return valor
    h, d = estado.get("hechos", {}), estado.get("datos", {})
    if valor.startswith("$ctx:"):
        return contexto_redaccion(estado, valor[5:])
    if valor.startswith("$h."):
        return h.get(valor[3:], "")
    if valor.startswith("$d."):
        clave = valor[3:]
        defecto = [] if clave == "antecedentes" else 0 if clave == "edad" else ""
        return d.get(clave, defecto)
    return {"$folio": estado.get("folio"), "$fecha": estado.get("fecha_actual"), "$texto": estado.get("texto", ""),
            "$tipo": estado.get("clasificacion", {}).get("tipo"),
            "$banderas": estado.get("clasificacion", {}).get("banderas", []),
            "$prioridad": estado.get("prioridad", "media"), "$estado_caso": estado.get("estado_caso", "abierto"),
            }.get(valor, valor)


def contexto_redaccion(estado: dict, tipo_doc: str) -> dict:
    """Arma el contexto del documento a partir de la memoria de trabajo del caso."""
    h = estado.get("hechos", {})
    normativa = [{"respuesta_directa": n.get("respuesta_directa", ""), "citas": n.get("citas", [])}
                 for n in h.get("normativa", []) if n.get("respaldo")]
    citas = sorted({c for n in normativa for c in n["citas"]})
    req = h.get("requisitos", {})
    antecedentes = []
    if h.get("cumplimiento_fcip"):
        cf = h["cumplimiento_fcip"]
        antecedentes.append(f"Verificacion de plazo FCIP: {cf.get('estado')} (limite {cf.get('fecha_limite', '-')}).")
    if h.get("casos_similares"):
        antecedentes.append(f"Casos similares revisados: {', '.join(h['casos_similares'])}.")
    return {
        "tipo": estado.get("clasificacion", {}).get("tipo"), "sintesis": estado.get("texto", "")[:600],
        "fecha_ingreso": h.get("fecha_ingreso", ""), "fecha_limite": h.get("fecha_limite_respuesta", ""),
        "fecha_solicitud_completa": h.get("fecha_solicitud_completa", ""),
        "normativa": normativa, "citas": citas, "medidas": estado.get("medidas", []),
        "antecedentes": " ".join(antecedentes) or None, "ges": bool(h.get("ges")),
        "faltantes": req.get("faltantes", []), "fundamento": req.get("fundamento", ""),
        "unidad": "Direccion (unidad responsable por asignar)", "prioridad": estado.get("prioridad"),
        "destinatarios": ["Direccion", "Calidad y Seguridad del Paciente"],
        "motivos": [e["detalle"] for e in estado.get("eventos_historial", [])] or ["Reclamo de alta gravedad"],
    }


def nodo_ejecutar(estado: EstadoCaso) -> dict:
    cfg = CONFIG_AGENTE
    plan = [dict(p) for p in estado["plan"]]
    paso = planificador.siguiente_paso(plan)
    if paso is None:
        return {"ultimo_paso": ""}
    args = _resolver(paso["args"], estado)
    herramienta = CATALOGO[paso["accion"]]
    reintentos = dict(estado.get("reintentos", {}))
    try:
        resultado = herramienta.invoke(args)
        paso_estado = "hecho"
    except Exception as e:  # la falla no rompe el grafo: se convierte en evento
        resultado = {"_error": f"{type(e).__name__}: {e}"}
        reintentos[paso["id"]] = reintentos.get(paso["id"], 0) + 1
        paso_estado = "fallido"
    for p in plan:
        if p["id"] == paso["id"]:
            p["estado"] = paso_estado

    hechos = dict(estado.get("hechos", {}))
    upd: dict[str, Any] = {}
    if paso_estado == "hecho":
        for clave, origen in paso.get("guardar", {}).items():
            if origen == "*":
                hechos[clave] = resultado
            elif origen == "+":
                hechos[clave] = hechos.get(clave, []) + [resultado]
            else:
                hechos[clave] = resultado.get(origen)
        if paso["accion"] == "calcular_plazo" and "fecha_limite_respuesta" in paso.get("guardar", {}):
            hechos["inicio_plazo_respuesta"] = args["fecha_inicio"]
            hechos["dias_plazo_respuesta"] = args["dias"]
        if paso["accion"] == "evaluar_prioridad":
            upd["prioridad"] = _max_nivel(estado.get("prioridad", "media"), resultado["nivel"])
        if paso["accion"] == "actualizar_estado_caso":
            upd["estado_caso"] = resultado["estado"]
    resultados = dict(estado.get("resultados", {}))
    resultados[paso["id"]] = resultado
    resumen = {k: resultado[k] for k in list(resultado)[:4] if k not in ("respuesta", "caso")} if isinstance(resultado, dict) else resultado
    log = [_log(estado, "ejecutar", "tool",
                f"{paso['id']} [{FAMILIA[paso['accion']]}] {paso['accion']} -> {paso_estado}: {resumen}")]
    return {**upd, "plan": plan, "hechos": hechos, "resultados": resultados, "reintentos": reintentos,
            "ultimo_paso": paso["id"], "iteraciones": estado.get("iteraciones", 0) + 1, "bitacora": log}


def nodo_evaluar(estado: EstadoCaso) -> dict:
    cfg = CONFIG_AGENTE
    pid = estado.get("ultimo_paso")
    if not pid:
        return {}
    paso = next(p for p in estado["plan"] if p["id"] == pid)
    eventos = planificador.detectar_eventos(paso, estado["resultados"].get(pid, {}),
                                            {**estado, "_max_reintentos": cfg.max_reintentos})
    if not eventos:
        return {}
    return {"eventos_pendientes": eventos,
            "bitacora": [_log(estado, "evaluar", "decision",
                              f"condicion detectada tras {pid}: {[e['tipo'] for e in eventos]} -> replanificar")]}


def ruta_evaluar(estado: EstadoCaso) -> str:
    cfg = CONFIG_AGENTE
    if estado.get("iteraciones", 0) >= cfg.max_iteraciones:
        return "cerrar"
    if estado.get("eventos_pendientes"):
        return "replanificar"
    if planificador.siguiente_paso(estado.get("plan", [])) is not None:
        return "continuar"
    return "cerrar"


FINALES = {"respondido", "cerrado", "derivado", "escalado"}


def nodo_cierre(estado: EstadoCaso) -> dict:
    cfg = CONFIG_AGENTE
    plan = estado.get("plan", [])
    resumen = {
        "folio": estado["folio"], "sesion": estado.get("sesion"), "estado_caso": estado.get("estado_caso"),
        "prioridad": estado.get("prioridad"), "tipo": estado["clasificacion"]["tipo"],
        "banderas": estado["clasificacion"].get("banderas", []), "version_plan": estado.get("version_plan"),
        "pasos": {s: sum(1 for p in plan if p["estado"] == s) for s in ("hecho", "pendiente", "suspendido", "omitido", "fallido")},
        "eventos": [e["tipo"] for e in estado.get("eventos_historial", [])],
        "fecha_limite": estado.get("hechos", {}).get("fecha_limite_respuesta"),
        "iteraciones_sesion": estado.get("iteraciones"),
    }
    if estado.get("iteraciones", 0) >= cfg.max_iteraciones:
        resumen["advertencia"] = "se alcanzo el tope de iteraciones; requiere revision humana"
    log = [_log(estado, "cierre", "decision",
                f"fin de sesion {estado.get('sesion')}: estado '{estado.get('estado_caso')}', "
                f"pasos {resumen['pasos']}")]
    upd: dict[str, Any] = {"resumen_sesion": resumen}

    # ---- memoria de largo plazo: solo casos que llegan a un estado final
    if estado.get("estado_caso") in FINALES:
        m = memoria()
        texto = f"{resumen['tipo']}: {estado.get('texto', '')}"
        m.put("casos", estado["folio"], texto, {
            "folio": estado["folio"], "tipo": resumen["tipo"], "estado": resumen["estado_caso"],
            "eventos": resumen["eventos"], "prioridad": resumen["prioridad"], "sesiones": estado.get("sesion"),
            "medidas": estado.get("medidas", []),
        })
        for e in estado.get("eventos_historial", []):
            if e["tipo"] in ("incumplimiento_ges", "escalamiento_inmediato", "sin_respaldo", "herramienta_no_disponible"):
                m.put("lecciones", f"{estado['folio']}:{e['tipo']}", f"{resumen['tipo']}: {estado.get('texto', '')} "
                      f"| leccion: {e['detalle']}", {"folio": estado["folio"], "evento": e["tipo"], "tipo": resumen["tipo"]})
        log.append(_log(estado, "cierre", "memoria", f"memoria largo plazo actualizada (casos={m.contar('casos')}, "
                                                     f"lecciones={m.contar('lecciones')})"))

    # ---- memoria de corto plazo: compactacion de la bitacora (ventana de contexto)
    bit = list(estado.get("bitacora", [])) + log
    comp = compactar_bitacora(bit, cfg)
    if comp:
        nueva, txt = comp
        upd["bitacora"] = [{RESET: True}] + nueva
        upd["resumen_contexto"] = (estado.get("resumen_contexto", "") + "\n" + txt).strip()
    else:
        upd["bitacora"] = log
    return upd


# ======================================================================= ensamblado


def construir_grafo(checkpointer=None):
    g = StateGraph(EstadoCaso)
    g.add_node("ingreso", nodo_ingreso)
    g.add_node("recuperar_contexto", nodo_recuperar_contexto)
    g.add_node("planificar", nodo_planificar)
    g.add_node("ejecutar", nodo_ejecutar)
    g.add_node("evaluar", nodo_evaluar)
    g.add_node("cierre", nodo_cierre)
    g.add_edge(START, "ingreso")
    g.add_edge("ingreso", "recuperar_contexto")
    g.add_edge("recuperar_contexto", "planificar")
    g.add_edge("planificar", "ejecutar")
    g.add_edge("ejecutar", "evaluar")
    g.add_conditional_edges("evaluar", ruta_evaluar,
                            {"replanificar": "planificar", "continuar": "ejecutar", "cerrar": "cierre"})
    g.add_edge("cierre", END)
    return g.compile(checkpointer=checkpointer if checkpointer is not None else crear_checkpointer())


class AgenteCasos:
    """Fachada de uso: una instancia mantiene el grafo y su checkpointer."""

    def __init__(self, checkpointer=None, cfg: ConfigAgente = CONFIG_AGENTE):
        self.cfg = cfg
        self.grafo = construir_grafo(checkpointer)

    def _config(self, folio: str) -> dict:
        return {"configurable": {"thread_id": folio}, "recursion_limit": self.cfg.recursion_limit}

    def procesar(self, folio: str, texto: str, fecha: str | None = None, datos: dict | None = None) -> dict:
        entrada = {"folio": folio, "mensajes": [{"fecha": fecha, "texto": texto, "datos": datos or {}}]}
        return self.grafo.invoke(entrada, self._config(folio))

    def estado(self, folio: str) -> dict:
        return self.grafo.get_state(self._config(folio)).values
