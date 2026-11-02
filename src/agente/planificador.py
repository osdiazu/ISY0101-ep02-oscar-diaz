"""Planificacion y toma de decisiones (IL2.3).

Esquema de planificacion
------------------------
Un plan es una lista de pasos. Cada paso declara:

    id          identificador estable (p. ej. "R2")
    accion      herramienta del CATALOGO que ejecuta
    args        argumentos; los valores "$..." se resuelven contra el estado en tiempo
                de ejecucion ($folio, $fecha, $texto, $tipo, $banderas, $prioridad,
                $h.<hecho>, $d.<dato>, $ctx:<tipo_documento>)
    prioridad   0 = critica, 1 = alta, 2 = normal, 3 = baja
    depende_de  ids que deben estar resueltos (hecho u omitido) antes de ejecutar
    guardar     mapeo {hecho: clave_del_resultado} para consolidar en memoria de trabajo
    proposito   por que existe el paso (trazabilidad de la decision)
    origen      plantilla | memoria | replan:<evento>
    estado      pendiente | hecho | fallido | omitido | suspendido

Seleccion del siguiente paso: entre los pendientes cuyas dependencias estan resueltas,
el de menor `prioridad`; a igual prioridad, el que aparece primero (orden topologico
estable). Asi una escalacion critica insertada por replanificacion se ejecuta antes
que la redaccion de la respuesta, aunque se haya agregado despues.

Toma de decisiones adaptativa
-----------------------------
`detectar_eventos` lee el resultado de cada herramienta y emite eventos (condiciones
cambiantes); `replanificar` transforma el plan en respuesta a cada evento: inserta
pasos, suspende o reactiva ramas, eleva prioridades o cambia el estado del caso.
Las reglas son deterministas y auditables: en un contexto de salud publica se
privilegia que el flujo sea explicable y reproducible por sobre que lo improvise el LLM.
"""
from __future__ import annotations

import re

UNIDAD = {
    "reclamo": "OIRS / Participacion Social",
    "solicitud_ficha": "Oficial de Datos / Archivo de fichas",
    "rescate_nsp": "SOME / Equipo de sector",
    "consulta": "OIRS",
}

PATRONES = {
    "ges": r"\bges\b|fcip|garant[ií]a|\bauge\b|sigges",
    "trato": r"maltrat|\btrato\b|grit|vejatori|humill|groser|descort",
    "negligencia": r"negligen|da[ñn]o f[ií]sico|lesi[oó]n|error m[eé]dico",
    "ficha": r"copia de (la )?ficha|ficha cl[ií]nica|historial cl[ií]nico",
    "nsp": r"inasistenc|\bnsp\b|no (se )?(present|asist)|rescate",
    "reclamo": r"reclam|queja|molest|disconform|denunci",
}


# ================================================================== CLASIFICACION


def clasificar(texto: str, datos: dict) -> dict:
    """Clasifica el caso por tipo y banderas de riesgo (texto ya anonimizado)."""
    t = texto.lower()
    hits = {k: bool(re.search(p, t)) for k, p in PATRONES.items()}
    banderas = [b for b in ("ges", "trato", "negligencia") if hits[b]]
    if datos.get("edad", 0) >= 80:
        banderas.append("mayor_80")
    for b in ("discapacidad", "embarazo"):
        if datos.get(b):
            banderas.append(b)
    tipo = datos.get("tipo")
    if not tipo:
        if hits["ficha"]:
            tipo = "solicitud_ficha"
        elif hits["nsp"]:
            tipo = "rescate_nsp"
        elif hits["reclamo"] or hits["trato"] or hits["negligencia"]:
            tipo = "reclamo"
        else:
            tipo = "consulta"
    return {"tipo": tipo, "banderas": banderas, "unidad": UNIDAD.get(tipo, "OIRS"),
            "justificacion": "reglas lexicas sobre texto anonimizado + datos estructurados del formulario",
            "senales": [k for k, v in hits.items() if v]}


# ======================================================================= PLANES


def P(id, accion, args, prioridad=2, depende_de=(), guardar=None, proposito="", origen="plantilla", **extra):
    paso = {"id": id, "accion": accion, "args": args, "prioridad": prioridad,
            "depende_de": list(depende_de), "guardar": guardar or {}, "proposito": proposito,
            "origen": origen, "estado": "pendiente"}
    paso.update(extra)
    return paso


def _registrar(id="R1"):
    return P(id, "registrar_caso", {"folio": "$folio", "tipo": "$tipo", "fecha_ingreso": "$h.fecha_ingreso",
                                    "resumen": "$texto", "prioridad": "$prioridad"}, 1,
             proposito="Dejar el caso trazable en el sistema OIRS antes de cualquier otra accion")


def _prioridad(id, deps, limite="$h.fecha_limite_respuesta"):
    return P(id, "evaluar_prioridad", {"tipo": "$tipo", "banderas": "$banderas", "fecha_referencia": "$fecha",
                                       "fecha_limite": limite, "edad": "$d.edad"}, 1, deps,
             guardar={"prioridad_detalle": "*"}, proposito="Priorizar segun riesgo y holgura del plazo")


def _plan_reclamo(c: dict, datos: dict) -> list[dict]:
    plan = [
        _registrar(),
        P("R2", "calcular_plazo", {"fecha_inicio": "$h.fecha_ingreso", "dias": 15, "tipo": "habiles"}, 1,
          guardar={"fecha_limite_respuesta": "fecha_limite"},
          proposito="Plazo de respuesta a reclamo: 15 dias habiles (MAN-003 sec. 2)"),
        _prioridad("R3", ["R2"]),
        P("R4", "buscar_normativa", {"consulta": "plazo de respuesta de un reclamo en dias habiles desde el ingreso"}, 2,
          guardar={"normativa": "+"}, proposito="Fundamento de la respuesta"),
    ]
    if {"trato", "negligencia"} & set(c["banderas"]):
        plan.append(P("T1", "buscar_normativa",
                      {"consulta": "escalamiento de reclamos por trato vejatorio, presunta negligencia o dano fisico"},
                      1, guardar={"normativa": "+"}, etiqueta="escalamiento",
                      proposito="Verificar si el reclamo exige escalamiento (MAN-003 sec. 5)"))
    if "ges" in c["banderas"]:
        plan += _pasos_ges(origen="plantilla")
    deps = [p["id"] for p in plan if p["accion"] in ("buscar_normativa", "verificar_cumplimiento")]
    plan += [
        P("R5", "redactar_documento", {"folio": "$folio", "tipo_documento": "respuesta_oirs", "fecha": "$fecha",
                                       "contexto": "$ctx:respuesta_oirs"}, 3, ["R2"] + deps,
          proposito="Borrador de respuesta con la estructura de MAN-003 sec. 3"),
        P("R6", "actualizar_estado_caso", {"folio": "$folio", "estado": "respondido", "fecha": "$fecha",
                                           "prioridad": "$prioridad", "nota": "borrador de respuesta emitido"}, 3, ["R5"],
          proposito="Cerrar el ciclo del agente: queda para firma de jefatura"),
    ]
    return plan


def _pasos_ges(origen: str) -> list[dict]:
    return [
        P("G1", "buscar_normativa", {"consulta": "plazo de emision del FCIP ante sospecha GES"}, 1,
          guardar={"normativa": "+"}, origen=origen, proposito="Regla operativa GES (PRO-001 sec. 2)"),
        P("G2", "verificar_cumplimiento", {"fecha_hito": "$d.fecha_sospecha", "dias_plazo": 1,
                                           "fecha_referencia": "$fecha", "fecha_cumplimiento": "$d.fecha_fcip"},
          1, ["G1"], guardar={"cumplimiento_fcip": "*"}, etiqueta="fcip", origen=origen,
          proposito="Verificar que el FCIP se emitio dentro de 24 horas habiles (1 dia habil)"),
    ]


def _plan_ficha(c: dict, datos: dict) -> list[dict]:
    return [
        _registrar(),
        P("F2", "buscar_normativa", {"consulta": "quien puede solicitar copia de la ficha clinica y plazo de entrega"}, 1,
          guardar={"normativa": "+"}, proposito="Requisitos de acceso a ficha (PRO-006)"),
        P("F3", "verificar_requisitos_ficha", {"solicitante": "$d.solicitante", "antecedentes": "$d.antecedentes"}, 1,
          ["F2"], guardar={"requisitos": "*"}, proposito="Validar calidad del solicitante y antecedentes"),
        P("F4", "calcular_plazo", {"fecha_inicio": "$h.fecha_solicitud_completa", "dias": 5, "tipo": "habiles"}, 2,
          ["F3"], guardar={"fecha_limite_respuesta": "fecha_limite"},
          proposito="Plazo de entrega: 5 dias habiles desde la solicitud formal completa (PRO-006 sec. 3)"),
        _prioridad("F5", ["F4"]),
        P("F6", "crear_tarea", {"folio": "$folio", "unidad": "Archivo de fichas", "fecha": "$fecha",
                                "descripcion": "Preparar copia de ficha en formato digital cifrado o impreso con cargo",
                                "fecha_limite": "$h.fecha_limite_respuesta", "prioridad": "$prioridad"}, 2, ["F5"],
          proposito="Derivar la preparacion de la copia"),
        P("F7", "redactar_documento", {"folio": "$folio", "tipo_documento": "respuesta_ficha", "fecha": "$fecha",
                                       "contexto": "$ctx:respuesta_ficha"}, 3, ["F6"],
          proposito="Informar al solicitante la fecha de entrega"),
        P("F8", "actualizar_estado_caso", {"folio": "$folio", "estado": "respondido", "fecha": "$fecha",
                                           "prioridad": "$prioridad", "nota": "copia en preparacion"}, 3, ["F7"],
          proposito="Dejar el caso respondido con la copia en preparacion"),
    ]


def _plan_rescate(c: dict, datos: dict) -> list[dict]:
    plan = [_registrar()]
    if int(datos.get("inasistencias_consecutivas", 0) or 0) < 3:
        # Decision en tiempo de planificacion: el protocolo no aplica.
        plan.append(P("N0", "actualizar_estado_caso", {"folio": "$folio", "estado": "cerrado", "fecha": "$fecha",
                                                       "nota": "menos de 3 inasistencias consecutivas: no activa rescate (PRO-007 sec. 3)"},
                      2, ["R1"], proposito="El criterio de activacion del protocolo no se cumple"))
        return plan
    return plan + [
        P("N2", "buscar_normativa", {"consulta": "protocolo de rescate por tres inasistencias consecutivas en programas cronicos"},
          1, guardar={"normativa": "+"}, proposito="Plazos de rescate (PRO-007 sec. 3)"),
        P("N3", "calcular_plazo", {"fecha_inicio": "$fecha", "dias": 5, "tipo": "habiles"}, 1, ["N2"],
          guardar={"fecha_limite_llamada": "fecha_limite", "fecha_limite_respuesta": "fecha_limite"},
          proposito="Llamada telefonica dentro de 5 dias habiles"),
        _prioridad("N4", ["N3"]),
        P("N5", "crear_tarea", {"folio": "$folio", "unidad": "Equipo de sector", "fecha": "$fecha",
                                "descripcion": "Llamada telefonica de rescate (3 inasistencias consecutivas)",
                                "fecha_limite": "$h.fecha_limite_llamada", "prioridad": "$prioridad"}, 1, ["N4"]),
        P("N6", "actualizar_estado_caso", {"folio": "$folio", "estado": "en_seguimiento", "fecha": "$fecha",
                                           "prioridad": "$prioridad", "nota": "esperando resultado de la llamada"}, 2, ["N5"],
          proposito="El caso queda a la espera del resultado del rescate telefonico"),
    ]


def _plan_consulta(c: dict, datos: dict) -> list[dict]:
    return [
        _registrar(),
        P("C2", "calcular_plazo", {"fecha_inicio": "$h.fecha_ingreso", "dias": 10, "tipo": "habiles"}, 1,
          guardar={"fecha_limite_respuesta": "fecha_limite"}, proposito="Consultas: 10 dias habiles (MAN-003 sec. 2)"),
        P("C3", "buscar_normativa", {"consulta": "$texto"}, 1, guardar={"normativa": "+"}, exige_respaldo=True,
          proposito="Responder con respaldo documental o abstenerse"),
        P("C4", "redactar_documento", {"folio": "$folio", "tipo_documento": "respuesta_consulta", "fecha": "$fecha",
                                       "contexto": "$ctx:respuesta_consulta"}, 2, ["C2", "C3"]),
        P("C5", "actualizar_estado_caso", {"folio": "$folio", "estado": "respondido", "fecha": "$fecha",
                                           "nota": "consulta respondida con respaldo"}, 3, ["C4"],
          proposito="Cerrar la consulta como respondida"),
    ]


PLANTILLAS = {"reclamo": _plan_reclamo, "solicitud_ficha": _plan_ficha,
              "rescate_nsp": _plan_rescate, "consulta": _plan_consulta}


def plan_inicial(clasificacion: dict, datos: dict, memoria_recuperada: dict | None = None) -> tuple[list[dict], list[str]]:
    """Construye el plan inicial y aplica ajustes derivados de la memoria de largo plazo."""
    plan = PLANTILLAS[clasificacion["tipo"]](clasificacion, datos)
    notas = [f"plantilla '{clasificacion['tipo']}' con {len(plan)} pasos"]
    # --- Aprendizaje desde memoria de largo plazo -------------------------------
    for lec in (memoria_recuperada or {}).get("lecciones", []):
        meta = lec.get("metadata", {})
        if (meta.get("evento") == "incumplimiento_ges" and clasificacion["tipo"] == "reclamo"
                and not any(p["id"] == "G2" for p in plan)):
            extra = _pasos_ges(origen="memoria")
            idx = next(i for i, p in enumerate(plan) if p["accion"] == "redactar_documento")
            plan[idx:idx] = extra
            plan[idx + len(extra)]["depende_de"] += ["G1", "G2"]
            notas.append(f"memoria: leccion similar ({lec['similitud']}) del folio {meta.get('folio')} "
                         "-> se agrega verificacion preventiva de FCIP/GES")
    return plan, notas


# ============================================================ seleccion de pasos


RESUELTOS = {"hecho", "omitido"}


def siguiente_paso(plan: list[dict]) -> dict | None:
    estado = {p["id"]: p["estado"] for p in plan}
    listos = [(p["prioridad"], i, p) for i, p in enumerate(plan)
              if p["estado"] == "pendiente" and all(estado.get(d) in RESUELTOS for d in p["depende_de"])]
    return min(listos, key=lambda x: (x[0], x[1]))[2] if listos else None


def pendientes(plan: list[dict]) -> list[dict]:
    return [p for p in plan if p["estado"] == "pendiente"]


# ======================================================= deteccion de eventos


def detectar_eventos(paso: dict, resultado: dict, estado: dict) -> list[dict]:
    """Reglas que convierten resultados de herramientas en condiciones del caso."""
    ev = []
    a, r = paso["accion"], resultado or {}
    banderas = estado.get("clasificacion", {}).get("banderas", [])
    if r.get("_error"):
        reint = estado.get("reintentos", {}).get(paso["id"], 0)
        return [{"tipo": "reintento" if reint < estado.get("_max_reintentos", 2) else "herramienta_no_disponible",
                 "paso": paso["id"], "detalle": r["_error"]}]
    if a == "buscar_normativa":
        if paso.get("exige_respaldo") and not r.get("respaldo"):
            ev.append({"tipo": "sin_respaldo", "paso": paso["id"],
                       "detalle": "el RAG se abstuvo: no hay evidencia documental suficiente"})
        if paso.get("etiqueta") == "escalamiento" and "MAN-003" in r.get("documentos", []) \
                and {"trato", "negligencia"} & set(banderas):
            ev.append({"tipo": "escalamiento_inmediato", "paso": paso["id"],
                       "detalle": "MAN-003 sec. 5 exige derivar el mismo dia a Direccion y Calidad"})
    elif a == "verificar_cumplimiento" and paso.get("etiqueta") == "fcip":
        if r.get("estado") in ("incumplido", "cumplido_fuera_de_plazo"):
            ev.append({"tipo": "incumplimiento_ges", "paso": paso["id"],
                       "detalle": f"FCIP {r['estado']} (limite {r.get('fecha_limite')}, "
                                  f"{r.get('dias_habiles_de_atraso', 0)} dias habiles de atraso)"})
        elif r.get("estado") == "sin_datos":
            ev.append({"tipo": "dato_faltante", "paso": paso["id"], "detalle": "no hay fecha de sospecha GES"})
    elif a == "verificar_requisitos_ficha":
        if not r.get("cumple"):
            ev.append({"tipo": "faltan_antecedentes", "paso": paso["id"],
                       "detalle": "faltan: " + ", ".join(r.get("faltantes", []))})
    elif a == "evaluar_prioridad":
        if r.get("nivel") == "critica":
            ev.append({"tipo": "prioridad_critica", "paso": paso["id"],
                       "detalle": f"puntaje {r.get('puntaje')}: " + "; ".join(r.get("razones", []))})
    return ev


# ============================================================== replanificacion


def _max_id(plan, prefijo):
    n = [int(m.group(1)) for p in plan if (m := re.fullmatch(prefijo + r"(\d+)", p["id"]))]
    return max(n, default=0) + 1


def replanificar(plan: list[dict], evento: dict, estado: dict) -> tuple[list[dict], list[str], dict]:
    """Ajusta el plan ante un evento. Devuelve (plan, cambios, actualizaciones_de_estado)."""
    plan = [dict(p) for p in plan]
    tipo, cambios, upd = evento["tipo"], [], {}
    por_id = {p["id"]: p for p in plan}
    origen = f"replan:{tipo}"

    def nuevo(prefijo, *a, **kw):
        paso = P(f"{prefijo}{_max_id(plan, prefijo)}", *a, origen=origen, **kw)
        plan.append(paso)
        por_id[paso["id"]] = paso
        cambios.append(f"+ {paso['id']} {paso['accion']} (prio {paso['prioridad']}): {paso['proposito']}")
        return paso

    def suspender(pred, motivo):
        for p in plan:
            if p["estado"] == "pendiente" and pred(p):
                p["estado"], p["motivo"] = "suspendido", motivo
                cambios.append(f"~ {p['id']} {p['accion']} suspendido")

    def omitir(pred, motivo):
        for p in plan:
            if p["estado"] in ("pendiente", "suspendido") and pred(p):
                p["estado"], p["motivo"] = "omitido", motivo
                cambios.append(f"- {p['id']} {p['accion']} omitido ({motivo})")

    if tipo == "reintento":
        p = por_id[evento["paso"]]
        p["estado"] = "pendiente"
        cambios.append(f"↻ {p['id']} {p['accion']} se reintenta")

    elif tipo == "herramienta_no_disponible":
        p = por_id[evento["paso"]]
        p["estado"] = "fallido"
        dependientes = {q["id"] for q in plan if p["id"] in q["depende_de"]}
        omitir(lambda q: q["id"] in dependientes, f"depende de {p['id']} fallido")
        nuevo("X", "crear_tarea", {"folio": "$folio", "unidad": "Jefatura OIRS", "fecha": "$fecha",
                                   "descripcion": f"Gestion manual: la herramienta {p['accion']} no respondio tras reintentos",
                                   "fecha_limite": "$fecha", "prioridad": "alta"}, 0,
              proposito="Escalar a un humano en vez de dejar el caso a medias")
        upd["estado_caso"] = "escalado"

    elif tipo == "escalamiento_inmediato":
        if not any(q.get("etiqueta") == "minuta" for q in plan):
            t = nuevo("E", "crear_tarea", {"folio": "$folio", "unidad": "Direccion + Calidad y Seguridad del Paciente",
                                           "fecha": "$fecha", "fecha_limite": "$fecha", "prioridad": "critica",
                                           "descripcion": "Reclamo con presunto trato vejatorio/negligencia: revisar el mismo dia"},
                      0, proposito="MAN-003 sec. 5: derivacion el mismo dia")
            nuevo("E", "redactar_documento", {"folio": "$folio", "tipo_documento": "minuta_escalamiento", "fecha": "$fecha",
                                              "contexto": "$ctx:minuta_escalamiento"}, 0, [t["id"]], etiqueta="minuta",
                  proposito="Minuta formal para Direccion")
        upd["prioridad"] = "critica"
        upd["medidas"] = ["Derivacion el mismo dia a Direccion y a Calidad y Seguridad del Paciente (MAN-003 sec. 5)."]

    elif tipo == "incumplimiento_ges":
        nuevo("G", "crear_tarea", {"folio": "$folio", "unidad": "Subdireccion Clinica / Encargado GES", "fecha": "$fecha",
                                   "fecha_limite": "$fecha", "prioridad": "critica",
                                   "descripcion": "Emitir/regularizar FCIP de inmediato y registrar en SIGGES; "
                                                  "el plazo de oportunidad se cuenta desde el FCIP"}, 0,
              proposito="Corregir el incumplimiento GES antes de responder")
        upd["prioridad"] = "critica"
        upd["ges"] = True
        upd["medidas"] = ["Regularizacion inmediata del FCIP por Subdireccion Clinica / Encargado GES (PRO-001)."]
        for q in plan:
            if q["estado"] == "pendiente" and q["accion"] == "redactar_documento":
                q["prioridad"] = 1
                cambios.append(f"↑ {q['id']} prioridad 3→1 (caso GES con incumplimiento)")

    elif tipo == "dato_faltante":
        nuevo("D", "crear_tarea", {"folio": "$folio", "unidad": "SOME", "fecha": "$fecha", "fecha_limite": "$h.fecha_limite_respuesta",
                                   "prioridad": "alta", "descripcion": "Verificar en SIGGES si existe FCIP y su fecha de emision"},
              1, proposito="Completar el dato antes de cerrar la respuesta")
        upd["medidas"] = ["Verificacion en SIGGES de la existencia y fecha del FCIP (SOME)."]

    elif tipo == "faltan_antecedentes":
        suspender(lambda q: q["id"] in ("F4", "F5", "F6", "F7", "F8"), "faltan antecedentes del solicitante")
        nuevo("A", "redactar_documento", {"folio": "$folio", "tipo_documento": "solicitud_antecedentes", "fecha": "$fecha",
                                          "contexto": "$ctx:solicitud_antecedentes"}, 1,
              proposito="Pedir los antecedentes faltantes (PRO-006 sec. 2)")
        nuevo("A", "actualizar_estado_caso", {"folio": "$folio", "estado": "pendiente_antecedentes", "fecha": "$fecha",
                                              "nota": evento["detalle"]}, 2, proposito="El caso espera al usuario")
        upd["estado_caso"] = "pendiente_antecedentes"
        upd["esperando"] = "antecedentes"

    elif tipo == "antecedentes_recibidos":
        omitir(lambda q: q["accion"] == "verificar_requisitos_ficha", "reemplazado por nueva verificacion")
        v = nuevo("V", "verificar_requisitos_ficha", {"solicitante": "$d.solicitante", "antecedentes": "$d.antecedentes"},
                  1, guardar={"requisitos": "*"}, proposito="Revalidar con los antecedentes recibidos")
        for q in plan:
            if q["estado"] == "suspendido":
                q["estado"] = "pendiente"
                q["depende_de"] = [v["id"] if d == "F3" else d for d in q["depende_de"]]
                cambios.append(f"↺ {q['id']} {q['accion']} reactivado")
        upd["hechos"] = {"fecha_solicitud_completa": estado.get("fecha_actual")}
        upd["estado_caso"] = "abierto"
        upd["esperando"] = ""

    elif tipo == "sin_respaldo":
        omitir(lambda q: q["accion"] == "redactar_documento" or
               (q["accion"] == "actualizar_estado_caso" and q["args"].get("estado") == "respondido"),
               "no se responde sin respaldo documental")
        t = nuevo("S", "crear_tarea", {"folio": "$folio", "unidad": "Direccion (asignar unidad responsable)", "fecha": "$fecha",
                                       "fecha_limite": "$h.fecha_limite_respuesta", "prioridad": "media",
                                       "descripcion": "Responder consulta sin respaldo en el corpus; evaluar incorporar documento"},
                  1, proposito="Derivar a quien puede responder")
        d = nuevo("S", "redactar_documento", {"folio": "$folio", "tipo_documento": "acuse_derivacion", "fecha": "$fecha",
                                              "contexto": "$ctx:acuse_derivacion"}, 2, [t["id"]],
                  proposito="Acuse al usuario informando la derivacion y el plazo")
        nuevo("S", "actualizar_estado_caso", {"folio": "$folio", "estado": "derivado", "fecha": "$fecha",
                                              "nota": "abstencion por falta de respaldo"}, 3, [d["id"]],
              proposito="El caso queda derivado, no respondido")

    elif tipo == "resultado_llamada":
        if evento.get("valor") == "sin_contacto":
            n = nuevo("N", "calcular_plazo", {"fecha_inicio": "$fecha", "dias": 15, "tipo": "habiles"}, 1,
                      guardar={"fecha_limite_visita": "fecha_limite", "fecha_limite_respuesta": "fecha_limite"},
                      proposito="Sin contacto: visita domiciliaria dentro de 15 dias habiles (PRO-007 sec. 3)")
            pr = nuevo("N", "evaluar_prioridad", {"tipo": "$tipo", "banderas": "$banderas", "fecha_referencia": "$fecha",
                                                  "fecha_limite": "$h.fecha_limite_visita", "edad": "$d.edad"}, 1,
                       [n["id"]], guardar={"prioridad_detalle": "*"}, proposito="Repriorizar con la nueva condicion")
            t = nuevo("N", "crear_tarea", {"folio": "$folio", "unidad": "Equipo de sector", "fecha": "$fecha",
                                           "descripcion": "Visita domiciliaria de rescate (sin contacto telefonico)",
                                           "fecha_limite": "$h.fecha_limite_visita", "prioridad": "$prioridad"}, 1, [pr["id"]],
                      proposito="Programar la visita domiciliaria del equipo de sector")
            nuevo("N", "actualizar_estado_caso", {"folio": "$folio", "estado": "en_seguimiento", "fecha": "$fecha",
                                                  "prioridad": "$prioridad", "cerrar_tareas_con": "Llamada",
                                                  "nota": "llamada sin contacto; se programa visita"}, 2, [t["id"]],
                  proposito="Cerrar la tarea de llamada y mantener el seguimiento")
            upd["banderas_extra"] = ["sin_contacto"]
        else:
            nuevo("N", "actualizar_estado_caso", {"folio": "$folio", "estado": "cerrado", "fecha": "$fecha",
                                                  "cerrar_tareas_con": "", "nota": "paciente contactado y reagendado"}, 2,
                  proposito="Rescate exitoso: se cierra el caso")
        upd["esperando"] = ""

    elif tipo == "feriado_agregado":
        # Los plazos ya calculados quedan obsoletos: se recalculan y se reasignan.
        n = nuevo("H", "calcular_plazo", {"fecha_inicio": "$h.inicio_plazo_respuesta", "dias": "$h.dias_plazo_respuesta",
                                          "tipo": "habiles"}, 0, guardar={"fecha_limite_respuesta": "fecha_limite"},
                  proposito=f"Recalcular plazo por feriado nuevo ({evento.get('valor')})")
        nuevo("H", "actualizar_estado_caso", {"folio": "$folio", "estado": "$estado_caso", "fecha": "$fecha",
                                              "nota": "plazo recalculado por feriado"}, 1, [n["id"]],
              proposito="Dejar constancia del nuevo plazo en el sistema OIRS")

    elif tipo == "prioridad_critica":
        upd["prioridad"] = "critica"
        for q in plan:
            if q["estado"] == "pendiente" and q["prioridad"] > 1 and q["accion"] != "actualizar_estado_caso":
                q["prioridad"] = 1
                cambios.append(f"↑ {q['id']} prioridad →1 (caso critico)")

    if not cambios and tipo not in ("prioridad_critica",):
        cambios.append(f"(sin cambios de plan para '{tipo}')")
    return plan, cambios, upd
