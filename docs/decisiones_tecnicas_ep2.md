# Bitácora de decisiones de diseño — EP2

Continúa la bitácora de la EP1 (D1–D10 en el repositorio de la EP1). Cada entrada registra el
problema, las alternativas, la decisión, la evidencia y el costo asumido.

> Nota para el autor: esta bitácora documenta *qué* se decidió y con qué evidencia. La
> justificación técnica del informe debe redactarse con palabras propias (pauta, uso de IA).

---

### D1 — LangGraph como framework de orquestación

**Problema.** El flujo OIRS tiene etapas, bifurcaciones, esperas de días y reanudación.
**Alternativas.** (a) `AgentExecutor`/ReAct clásico de LangChain; (b) AutoGen multiagente;
(c) Haystack Agents; (d) LangGraph.
**Decisión.** (d). Modela el flujo como máquina de estados explícita (nodos + aristas
condicionales), trae *checkpointing* por hilo para retomar casos y *reducers* para controlar
cómo crece el estado. Un ReAct puro deja el control de flujo dentro del prompt, lo que es difícil
de auditar; AutoGen agrega coordinación entre agentes que el caso no necesita.
**Compatibilidad y escalabilidad.** `SqliteSaver` se cambia por `PostgresSaver` sin tocar los
nodos; las *tools* de `langchain_core` son portables a cualquier agente LangChain/LangGraph o a
un servidor MCP. El CI prueba Python 3.10 y 3.12.
**Costo.** Dependencia de un ecosistema que cambia rápido: versiones acotadas en `requirements.txt`.

### D2 — Herramientas tipadas en tres familias

**Decisión.** 11 herramientas `@tool` con firma tipada, *docstring* y salida JSON. Separar
consulta, razonamiento y escritura permite auditar qué acciones tienen efectos laterales: solo
las de escritura tocan el sistema OIRS y solo ellas pasan por el inyector de fallas.
**Evidencia.** `test_catalogo_cubre_las_tres_familias` y pruebas unitarias por herramienta.

### D3 — Razonamiento temporal en código, no en el LLM

**Problema.** Contar días hábiles con feriados es un cálculo exacto; un LLM se equivoca.
**Decisión.** `calendario.py` + `feriados_cl.json` editable. El agente decide *cuándo* calcular,
pero el cálculo es determinista.
**Evidencia.** Pruebas de fin de semana, feriado y feriado agregado en caliente (E5: 30-11 → 01-12).

### D4 — Planificador basado en reglas con replanificación por eventos

**Alternativas.** (a) El LLM genera el plan en cada paso (ReAct); (b) plan fijo; (c) plantillas
por tipo de caso + reglas de eventos que modifican el plan.
**Decisión.** (c). En salud pública el flujo debe ser **reproducible y explicable**: cada paso
tiene `proposito` y `origen` (plantilla, memoria o `replan:<evento>`) y cada cambio queda en la
bitácora. La autonomía está en que el agente detecta las condiciones y reordena su trabajo sin
intervención humana.
**Costo.** No generaliza a tipos de caso no previstos. Extensión propuesta: que el LLM proponga
pasos y el planificador los valide contra el catálogo antes de agregarlos.

### D5 — Prioridad + dependencias para secuenciar

**Decisión.** Siguiente paso = pendiente de menor prioridad con dependencias resueltas (orden
topológico estable). Permite insertar pasos críticos que se adelantan sin reescribir el plan.
**Evidencia.** `test_siguiente_paso_respeta_prioridad_y_dependencias`, E3 (la minuta se ejecuta antes que la respuesta).

### D6 — Memoria en dos niveles

**Corto plazo.** `SqliteSaver` por folio: cada super-paso queda persistido y el caso sobrevive al
cierre del proceso. Bitácora con *reducer* propio y compactación sobre 40 entradas.
**Largo plazo.** Almacén vectorial SQLite con espacios `casos` y `lecciones` e interfaz tipo
`BaseStore` (put/get/search). Se eligió SQLite por la restricción de bajo presupuesto (R5) y para
que el evaluador lo ejecute sin servicios externos; es reemplazable por `PostgresStore` + pgvector.
**Embeddings.** `HashingVectorizer` de n-gramas de caracteres como respaldo: no requiere
entrenamiento, por lo que los vectores guardados hoy siguen siendo comparables mañana (un TF-IDF
ajustado al corpus cambiaría su espacio al reentrenarse).
**Evidencia.** `test_checkpoint_permite_retomar_en_otro_proceso`, `test_memoria_largo_plazo_...`, E6.

### D7 — Solo memoria anonimizada

**Decisión.** El guardrail de la EP1 se aplica en el nodo `ingreso`, antes de clasificar,
planificar o guardar. Ni los documentos ni la memoria de largo plazo contienen PII.
**Evidencia.** `test_e1_no_filtra_pii_a_documentos_ni_memoria`.

### D8 — Fallas de herramientas como eventos

**Decisión.** `ejecutar` captura excepciones y las convierte en eventos: hasta 2 reintentos y
luego escalamiento a Jefatura OIRS, omitiendo los pasos dependientes. El grafo nunca queda a medias.
**Evidencia.** E7 y `test_falla_persistente_escala_a_humano`.

### D9 — Corrección del motor extractivo heredado

Se detectó que el motor extractivo de la EP1 fusionaba la línea de cita con la primera oración
y descartaba frases cortas como "Reclamo: 15 días hábiles". Se corrigió el corte de oraciones.
**Efecto medido.** Cobertura del dato clave 0,737 → **0,947**; recall@4, MRR, precisión de citas,
abstención y fugas de PII sin cambios (`python -m src.evaluate`).
