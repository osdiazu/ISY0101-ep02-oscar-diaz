# Guion de la presentación (20 min: 10 de exposición + 10 de preguntas)

Presentación individual: Oscar Díaz Ulloa expone y ejecuta la demo.

| Min | Diapositiva | Qué decir / hacer |
|---|---|---|
| 0:00 | 1 Portada | Autor, caso y qué cambia respecto a la EP1 |
| 0:30 | 2 Problema | Un caso dura varios días y exige plazos, prioridades y registro |
| 1:30 | 3 Orquestación | Recorrer los nodos del grafo y la arista condicional de `evaluar` |
| 2:45 | 4 Herramientas | Tres familias; por qué separar escritura y calcular plazos en código |
| 3:45 | 5 Memoria | Checkpoint por folio (E2) y aprendizaje entre casos (E6) |
| 5:00 | 6 Planificación | Prioridad + dependencias; eventos → nueva versión del plan |
| 6:15 | 7 **Demo en vivo** | Ver abajo |
| 8:45 | 8 Resultados | 49/49 pruebas, 7/7 escenarios, cobertura 0,947, 0 fugas |
| 9:30 | 9 Decisiones | Justificación con palabras propias y evidencia |
| 10:15 | 10 Cierre | Limitaciones y próximos pasos; abrir preguntas |

## Demo en vivo (2 min 30 s)

Preparación antes de la clase: entorno virtual activado, `pip install -r requirements.txt` hecho
y la terminal con letra grande. Plan B si algo falla: abrir `evidencias/demo_escenarios.txt`.

```bash
python -m src.agente.cli reiniciar
python -m src.agente.cli escenario escenarios/E2_ficha_tercero_dos_sesiones.json
```
Señalar: (1) en la sesión 1, `verificar_requisitos_ficha` falla, aparece el evento ⚡
`faltan_antecedentes` y el plan v2 **suspende** F4–F8; (2) el caso queda `pendiente_antecedentes`;
(3) en la sesión 2 dice "se retoma el caso desde el checkpoint", aparece el plan v3, la rama se
**reactiva** y el plazo es 13-11-2026 (5 días hábiles desde el 06-11).

```bash
python -m src.agente.cli estado --folio OIRS-2026-0102
```
Señalar la columna `origen`: pasos de la plantilla y pasos agregados por `replan:<evento>`.

```bash
python -m src.agente.cli escenario escenarios/E3_reclamo_trato_escalamiento.json
```
Señalar: el RAG cita MAN-003 §5 → evento `escalamiento_inmediato` → la tarea y la minuta
(prioridad 0) se ejecutan **antes** que la respuesta R5, aunque se agregaron después.

Si sobra tiempo, `E5` (tres sesiones con feriado nuevo) o `memoria --buscar "sospecha de cancer"`.

## Preguntas probables

- ¿Por qué no un agente ReAct donde el LLM decide todo? → auditabilidad y reproducibilidad en salud (D4).
- ¿Qué pasa con un tipo de caso que no está en las plantillas? → cae en "consulta"; extensión: el LLM propone pasos validados.
- ¿Cómo escala? → PostgresSaver y pgvector sin cambiar los nodos (D1, D6).
- ¿Dónde está la memoria y cómo se ve? → `runtime/*.sqlite`, comandos `estado` y `memoria`.
- ¿Cómo evitan bucles infinitos? → tope de 30 iteraciones y `recursion_limit`.
- ¿Qué hace si se cae una herramienta? → E7: reintento; si persiste, escala a Jefatura OIRS (D8).
