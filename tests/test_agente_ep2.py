"""Pruebas del agente de gestion de casos (EP2).

Cubren las cuatro capacidades evaluadas: herramientas (IE1), memoria de contenido y
recuperacion semantica (IE3, IE4), planificacion y decisiones adaptativas (IE5) y la
orquestacion de extremo a extremo con LangGraph sobre los escenarios de la demo.
Cada prueba que escribe en disco usa un directorio `runtime/` temporal y aislado.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agente import calendario, planificador, registro  # noqa: E402
from src.agente.config_agente import CONFIG_AGENTE  # noqa: E402
from src.agente.herramientas import (CATALOGO, FAMILIA, memoria,  # noqa: E402
                                     reiniciar_singletons)
from src.agente.memoria import (RESET, MemoriaLargoPlazo,  # noqa: E402
                                compactar_bitacora, reducer_bitacora)

ESC = Path(__file__).resolve().parents[1] / "escenarios"


def _entorno_limpio() -> Path:
    reiniciar_singletons()
    calendario.limpiar_feriados_extra()
    registro.INYECTOR.limpiar()
    CONFIG_AGENTE.runtime_dir = Path(tempfile.mkdtemp(prefix="cesfam_ep2_"))
    return CONFIG_AGENTE.runtime_dir


def _agente():
    from src.agente.grafo import AgenteCasos

    return AgenteCasos()


def _correr(nombre, agente=None):
    esc = json.loads((ESC / f"{nombre}.json").read_text(encoding="utf-8"))
    agente = agente or _agente()
    for h, n in esc.get("simular_fallo", {}).items():
        registro.INYECTOR.programar(h, n)
    finales = [agente.procesar(esc["folio"], s["texto"], s["fecha"], s.get("datos")) for s in esc["sesiones"]]
    return esc, finales


def _t(nombre, **args):
    return CATALOGO[nombre].invoke(args)


# ================================================================ HERRAMIENTAS (IE1)

def test_catalogo_cubre_las_tres_familias():
    assert set(FAMILIA.values()) == {"consulta", "razonamiento", "escritura"}
    assert set(CATALOGO) == set(FAMILIA)
    for t in CATALOGO.values():
        assert t.description, f"{t.name} sin descripcion"


def test_plazo_habil_salta_fin_de_semana():
    assert _t("calcular_plazo", fecha_inicio="2026-11-06", dias=1)["fecha_limite"] == "2026-11-09"


def test_plazo_habil_salta_feriado():
    calendario.limpiar_feriados_extra()
    assert _t("calcular_plazo", fecha_inicio="2026-12-07", dias=1)["fecha_limite"] == "2026-12-09"


def test_plazo_corridos_no_salta_nada():
    assert _t("calcular_plazo", fecha_inicio="2026-11-06", dias=3, tipo="corridos")["fecha_limite"] == "2026-11-09"


def test_feriado_nuevo_cambia_el_plazo():
    calendario.limpiar_feriados_extra()
    antes = calendario.sumar_dias("2026-11-09", 15)
    calendario.agregar_feriado("2026-11-20")
    despues = calendario.sumar_dias("2026-11-09", 15)
    calendario.limpiar_feriados_extra()
    assert (antes, despues) == ("2026-11-30", "2026-12-01")


def test_verificar_cumplimiento_estados():
    inc = _t("verificar_cumplimiento", fecha_hito="2026-10-20", dias_plazo=1, fecha_referencia="2026-11-02")
    ok = _t("verificar_cumplimiento", fecha_hito="2026-10-20", dias_plazo=1, fecha_referencia="2026-11-02",
            fecha_cumplimiento="2026-10-21")
    curso = _t("verificar_cumplimiento", fecha_hito="2026-11-02", dias_plazo=5, fecha_referencia="2026-11-03")
    sin = _t("verificar_cumplimiento", fecha_hito="", dias_plazo=1, fecha_referencia="2026-11-03")
    assert inc["estado"] == "incumplido" and inc["dias_habiles_de_atraso"] > 0
    assert ok["estado"] == "cumplido"
    assert curso["estado"] == "en_plazo"
    assert sin["estado"] == "sin_datos"


def test_prioridad_explicable_y_ordenada():
    crit = _t("evaluar_prioridad", tipo="reclamo", banderas=["trato", "negligencia"], fecha_referencia="2026-11-02")
    baja = _t("evaluar_prioridad", tipo="consulta", banderas=[], fecha_referencia="2026-11-02")
    mayor = _t("evaluar_prioridad", tipo="rescate_nsp", banderas=[], fecha_referencia="2026-11-02", edad=85)
    assert crit["nivel"] == "critica" and crit["razones"]
    assert baja["nivel"] == "baja"
    assert any("mayor_80" in r for r in mayor["razones"])


def test_requisitos_ficha_segun_pro006():
    falta = _t("verificar_requisitos_ficha", solicitante="tercero", antecedentes=["cedula_identidad"])
    ok = _t("verificar_requisitos_ficha", solicitante="titular", antecedentes=["cedula_identidad"])
    raro = _t("verificar_requisitos_ficha", solicitante="vecino", antecedentes=[])
    assert falta == {**falta, "cumple": False, "faltantes": ["mandato_notarial"]}
    assert ok["cumple"] is True
    assert raro["cumple"] is False


def test_escritura_y_consulta_en_sistema_oirs():
    _entorno_limpio()
    _t("registrar_caso", folio="T-1", tipo="reclamo", fecha_ingreso="2026-11-02", resumen="prueba")
    _t("crear_tarea", folio="T-1", unidad="SOME", descripcion="Llamada", fecha_limite="2026-11-09",
       prioridad="alta", fecha="2026-11-02")
    _t("actualizar_estado_caso", folio="T-1", estado="en_seguimiento", fecha="2026-11-03", cerrar_tareas_con="Llamada")
    caso = _t("consultar_caso", folio="T-1")["caso"]
    assert caso["estado"] == "en_seguimiento"
    assert caso["tareas"][0]["estado"] == "cerrada"


def test_respuesta_oirs_tiene_estructura_man003():
    rt = _entorno_limpio()
    r = _t("redactar_documento", folio="T-2", tipo_documento="respuesta_oirs", fecha="2026-11-02",
           contexto={"tipo": "reclamo", "sintesis": "x", "fecha_ingreso": "2026-11-02", "fecha_limite": "2026-11-23"})
    texto = (rt / "salidas" / "T-2" / Path(r["ruta"]).name).read_text(encoding="utf-8")
    for seccion in ("1. Identificacion", "2. Sintesis", "3. Antecedentes", "4. Respuesta de fondo",
                    "5. Medidas", "6. Via de apelacion"):
        assert seccion in texto


def test_buscar_normativa_respaldo_y_abstencion():
    si = _t("buscar_normativa", consulta="plazo de emision del FCIP ante sospecha GES")
    no = _t("buscar_normativa", consulta="tarifa mensual del estacionamiento para visitas")
    assert si["respaldo"] and "PRO-001" in si["documentos"]
    assert not no["respaldo"] and no["citas"] == []


# ================================================================ PLANIFICACION (IE5)

def test_clasificacion_por_tipo_y_banderas():
    assert planificador.clasificar("Solicito copia de la ficha clinica", {})["tipo"] == "solicitud_ficha"
    assert planificador.clasificar("tres inasistencias seguidas", {})["tipo"] == "rescate_nsp"
    c = planificador.clasificar("Reclamo: me grito el guardia", {})
    assert c["tipo"] == "reclamo" and "trato" in c["banderas"]
    assert planificador.clasificar("horario de farmacia", {})["tipo"] == "consulta"


def test_siguiente_paso_respeta_prioridad_y_dependencias():
    P = planificador.P
    plan = [P("A", "registrar_caso", {}, 1), P("B", "calcular_plazo", {}, 0, ["A"]), P("C", "crear_tarea", {}, 2)]
    assert planificador.siguiente_paso(plan)["id"] == "A"      # B es prioritaria pero depende de A
    plan[0]["estado"] = "hecho"
    assert planificador.siguiente_paso(plan)["id"] == "B"      # ahora B se adelanta a C


def test_replan_incumplimiento_ges_inserta_paso_critico_primero():
    c = {"tipo": "reclamo", "banderas": ["ges"]}
    plan, _ = planificador.plan_inicial(c, {})
    for p in plan:
        if p["id"] in ("R1", "R2", "R3", "G1", "G2"):
            p["estado"] = "hecho"
    nuevo, cambios, upd = planificador.replanificar(plan, {"tipo": "incumplimiento_ges", "detalle": "x"}, {})
    sig = planificador.siguiente_paso(nuevo)
    assert sig["accion"] == "crear_tarea" and sig["prioridad"] == 0 and sig["origen"].startswith("replan")
    assert upd["prioridad"] == "critica"


def test_replan_faltan_antecedentes_suspende_rama():
    plan, _ = planificador.plan_inicial({"tipo": "solicitud_ficha", "banderas": []}, {})
    nuevo, _, upd = planificador.replanificar(plan, {"tipo": "faltan_antecedentes", "detalle": "x"}, {})
    estados = {p["id"]: p["estado"] for p in nuevo}
    assert all(estados[i] == "suspendido" for i in ("F4", "F5", "F6", "F7", "F8"))
    assert upd["estado_caso"] == "pendiente_antecedentes"


def test_rescate_no_aplica_con_menos_de_tres_inasistencias():
    plan, _ = planificador.plan_inicial({"tipo": "rescate_nsp", "banderas": []}, {"inasistencias_consecutivas": 2})
    assert [p["accion"] for p in plan] == ["registrar_caso", "actualizar_estado_caso"]


def test_falla_persistente_escala_a_humano():
    _entorno_limpio()
    registro.INYECTOR.programar("redactar_documento", 5)
    _, finales = _correr("E4_consulta_sin_respaldo")
    f = finales[-1]
    assert f["estado_caso"] == "escalado"
    assert "herramienta_no_disponible" in [e["tipo"] for e in f["eventos_historial"]]
    assert any(p["accion"] == "crear_tarea" and p["origen"] == "replan:herramienta_no_disponible" for p in f["plan"])
    registro.INYECTOR.limpiar()


# =================================================================== MEMORIA (IE3, IE4)

def test_reducer_bitacora_agrega_y_compacta():
    assert reducer_bitacora([{"a": 1}], [{"b": 2}]) == [{"a": 1}, {"b": 2}]
    assert reducer_bitacora([{"a": 1}], [{RESET: True}, {"c": 3}]) == [{"c": 3}]


def test_compactacion_conserva_hitos():
    bit = [{"tipo": "tool", "detalle": f"t{i}"} for i in range(45)]
    bit[3] = {"tipo": "replan", "detalle": "plan v2 por X"}
    nueva, resumen = compactar_bitacora(bit)
    assert len(nueva) == CONFIG_AGENTE.bitacora_conservar + 1
    assert nueva[0]["tipo"] == "resumen" and "plan v2 por X" in resumen


def test_memoria_largo_plazo_persiste_y_recupera_por_similitud():
    _entorno_limpio()
    m = MemoriaLargoPlazo()
    m.put("casos", "A", "reclamo: sospecha de cancer sin formulario FCIP entregado", {"tipo": "reclamo"})
    m.put("casos", "B", "consulta: horario de atencion de farmacia los sabados", {"tipo": "consulta"})
    m.cerrar()
    m2 = MemoriaLargoPlazo()                       # nueva instancia: lee desde disco
    res = m2.search("casos", "no me entregaron el FCIP por sospecha de cancer", umbral=0.0)
    assert res[0]["clave"] == "A" and res[0]["similitud"] > res[1]["similitud"]
    m2.cerrar()


def test_checkpoint_permite_retomar_en_otro_proceso():
    """Memoria de corto plazo: la sesion 2 la atiende una instancia NUEVA del agente."""
    _entorno_limpio()
    esc = json.loads((ESC / "E2_ficha_tercero_dos_sesiones.json").read_text(encoding="utf-8"))
    s1, s2 = esc["sesiones"]
    r1 = _agente().procesar(esc["folio"], s1["texto"], s1["fecha"], s1["datos"])
    assert r1["estado_caso"] == "pendiente_antecedentes"
    reiniciar_singletons()
    r2 = _agente().procesar(esc["folio"], s2["texto"], s2["fecha"], s2["datos"])   # otra instancia
    assert r2["sesion"] == 2 and r2["estado_caso"] == "respondido"
    assert r2["hechos"]["fecha_limite_respuesta"] == "2026-11-13"
    assert any(e["sesion"] == 1 for e in r2["bitacora"])           # conserva lo ocurrido en la sesion 1


# ============================================================ EXTREMO A EXTREMO (grafo)

def test_e1_incumplimiento_ges_eleva_a_critica():
    _entorno_limpio()
    _, (f,) = _correr("E1_reclamo_ges_incumplido")
    assert f["estado_caso"] == "respondido" and f["prioridad"] == "critica"
    assert "incumplimiento_ges" in [e["tipo"] for e in f["eventos_historial"]]
    caso = registro.obtener_caso("OIRS-2026-0101")
    assert any("FCIP" in t["descripcion"] for t in caso["tareas"])


def test_e1_no_filtra_pii_a_documentos_ni_memoria():
    rt = _entorno_limpio()
    _correr("E1_reclamo_ges_incumplido")
    textos = [p.read_text(encoding="utf-8") for p in (rt / "salidas").rglob("*.md")]
    textos += [r["texto"] for r in memoria().search("casos", "reclamo", umbral=0.0)]
    for t in textos:
        assert "12.345.678-9" not in t and "Gonzalez" not in t and "8765" not in t


def test_e3_escalamiento_se_ejecuta_antes_que_la_respuesta():
    _entorno_limpio()
    _, (f,) = _correr("E3_reclamo_trato_escalamiento")
    orden = [b["detalle"].split(" ")[0] for b in f["bitacora"] if b["tipo"] == "tool"]
    assert orden.index("E1") < orden.index("R5")


def test_e4_sin_respaldo_deriva_y_no_responde():
    _entorno_limpio()
    _, (f,) = _correr("E4_consulta_sin_respaldo")
    assert f["estado_caso"] == "derivado"
    assert {p["id"]: p["estado"] for p in f["plan"]}["C4"] == "omitido"


def test_e5_tres_sesiones_con_condiciones_cambiantes():
    _entorno_limpio()
    _, finales = _correr("E5_rescate_nsp_tres_sesiones")
    assert [f["estado_caso"] for f in finales] == ["en_seguimiento"] * 3
    assert finales[1]["hechos"]["fecha_limite_visita"] == "2026-11-30"
    assert finales[2]["hechos"]["fecha_limite_respuesta"] == "2026-12-01"   # feriado nuevo
    assert finales[2]["version_plan"] == 3
    calendario.limpiar_feriados_extra()


def test_e6_memoria_de_largo_plazo_modifica_el_plan():
    _entorno_limpio()
    ag = _agente()
    _correr("E1_reclamo_ges_incumplido", ag)
    _, (f,) = _correr("E6_memoria_largo_plazo", ag)
    assert "ges" not in planificador.clasificar(f["texto"], {})["banderas"]   # el texto no dice GES
    assert any(p["origen"] == "memoria" for p in f["plan"])                   # pero la memoria lo agrega
    assert f["hechos"]["cumplimiento_fcip"]["estado"] == "cumplido"


def test_e7_falla_transitoria_se_reintenta():
    _entorno_limpio()
    _, (f,) = _correr("E7_falla_y_reintento")
    assert f["estado_caso"] == "respondido"
    assert "reintento" in [e["tipo"] for e in f["eventos_historial"]]
