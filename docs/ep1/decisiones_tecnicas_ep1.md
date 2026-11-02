# Bitácora de decisiones de diseño (IL1.4)

Cada decisión se registra con el problema que resuelve, las alternativas evaluadas, el
criterio de elección y su costo o limitación asumida.

---

### D1 — Chunking jerárquico de 900 caracteres con 150 de solape

**Problema.** Un corte arbitrario parte plazos y requisitos en dos, y el modelo termina
citando una regla incompleta.
**Alternativas.** (a) ventana fija de 512 tokens sin estructura; (b) un chunk por documento;
(c) corte por encabezados con respaldo de ventana deslizante.
**Decisión.** (c). Se divide primero por encabezados markdown (`#`, `##`, `###`), que en esta
documentación coinciden con la unidad de sentido normativa (un artículo, un paso de
protocolo), y sólo si la sección excede 900 caracteres se aplica ventana con corte en límite
de oración.
**Costo.** Documentos sin encabezados producirían chunks largos; se mitiga con el respaldo de
ventana. Verificado por prueba `test_chunk_respeta_tamano_maximo`.

---

### D2 — Recuperación híbrida BM25 + denso con Reciprocal Rank Fusion

**Problema.** El dominio mezcla términos exactos que deben coincidir literalmente ("FCIP",
"receta cheque", "C2") con consultas parafraseadas ("qué pasa si el paciente no viene").
**Alternativas.** (a) sólo denso; (b) sólo BM25; (c) híbrido con suma ponderada de scores;
(d) híbrido con RRF.
**Decisión.** (d). RRF fusiona por *posición* y no por score, lo que evita tener que
normalizar dos escalas incomparables (BM25 no acotado vs. coseno en [-1,1]) y elimina un
hiperparámetro de ponderación que habría que recalibrar con cada cambio de corpus.
**Evidencia.** Ablación (`evidencias/ablacion_recuperador.json`): recall@4 = 1.000 en las tres
configuraciones; `precision_chunks@4` = 0.618 (léxico), 0.539 (semántico), 0.605 (híbrido).
**Costo asumido y honesto.** En este corpus, de vocabulario controlado, BM25 puro es
marginalmente más denso que el híbrido (0.618 vs. 0.605). Se mantiene el híbrido porque el
recuperador semántico aporta los aciertos en consultas sin coincidencia literal —el caso real
del usuario de mesón— y porque la pérdida de densidad (1,3 puntos) no afecta el recall ni la
precisión de citas. La decisión se reevaluará cuando el corpus crezca sobre ~500 documentos.

---

### D3 — BM25 implementado en el proyecto, sin dependencias externas

**Problema.** El evaluador debe poder ejecutar el sistema sin red ni claves.
**Decisión.** Implementación propia de Okapi BM25 (k1=1.5, b=0.75) y degradación del
recuperador denso a TF-IDF de n-gramas de caracteres + SVD cuando `sentence-transformers` no
está disponible.
**Beneficio adicional.** El TF-IDF de caracteres (3–5) tolera las variantes con y sin tilde
que abundan en la documentación institucional.
**Costo.** La calidad semántica del *fallback* es inferior a un modelo de embeddings
multilingüe; en producción debe reemplazarse por uno alojado en infraestructura institucional
(R1: los datos no pueden salir de la institución).

---

### D4 — Anonimización obligatoria antes de la llamada al modelo

**Problema.** R1 prohíbe enviar datos identificables de pacientes a un modelo externo, y el
funcionario naturalmente escribe "el paciente Juan Pérez, RUT 12.345.678-9…".
**Decisión.** Capa de guardrail previa a todo el pipeline, con expresiones regulares para RUT
chileno (con y sin puntos), teléfono (+56 9), correo, número de ficha y patrón nominal
precedido de tratamiento ("paciente/Sr./Sra./don/doña"). El texto que viaja al modelo lleva
marcadores `[RUT_ANONIMIZADO]`, y la traza registra cuántos datos se detectaron.
**Evidencia.** 0 fugas en el set dorado; 5 pruebas parametrizadas de detección; prueba de
extremo a extremo `test_agente_no_filtra_pii_en_la_respuesta`.
**Limitación.** Las expresiones regulares no capturan todos los nombres sin tratamiento
previo. Mitigación propuesta: reconocimiento de entidades nombradas local, y política de
formulario que desaconseja escribir nombres.

---

### D5 — Router de intención antes de recuperar

**Problema.** Una pregunta normativa recuperaba protocolos internos y viceversa, y las siglas
("GES", "FCIP") no aparecen escritas en el texto de la norma externa.
**Decisión.** Un clasificador que produce `{categoria, fuentes, reformulacion}`. Con API se
delega al LLM con salida JSON estricta; sin API opera una heurística léxica determinista. La
reformulación **expande las siglas** antes de indexar la consulta, lo que sube el anclaje
léxico de forma medible.
**Costo.** Una llamada adicional al modelo por consulta cuando se usa la ruta LLM;
se acepta por el aumento de precisión y porque el router puede cachearse por patrón.

---

### D6 — Política de abstención con gate de confianza

**Problema.** El comportamiento por defecto de un LLM con contexto débil es responder igual.
En un contexto normativo eso es el peor error posible.
**Decisión.** Doble control: (i) instrucción explícita en el prompt de sistema con la frase
exacta de abstención, y (ii) un gate cuantitativo previo —si el anclaje léxico máximo de la
evidencia recuperada es inferior al umbral (`umbral_bm25 = 4.5`), el generador recibe
`SIN_EVIDENCIA` y no puede construir una respuesta.
**Calibración.** Observada sobre el set dorado: consultas con respaldo obtienen anclaje 8–23;
consultas sin respaldo, 2,0–2,7. El umbral se fijó en el valle entre ambas distribuciones.
**Resultado.** Abstención correcta 3/3 sin degradar el recall (1.000).
**Limitación.** Un umbral absoluto es sensible al tamaño del corpus; debe recalibrarse al
crecer la base documental (procedimiento documentado en `src/evaluate.py`).

---

### D7 — Citas verificadas programáticamente, no sólo pedidas en el prompt

**Problema.** Pedir citas en el prompt no garantiza que existan.
**Decisión.** El agente extrae las etiquetas `[...]` emitidas y las contrasta contra el
conjunto de etiquetas realmente presentes en la evidencia; toda etiqueta no respaldada se
registra en `traza.verificacion.citas_invalidas` y baja la métrica `precision_citas`.
**Resultado.** Precisión de citas 1.000 en el set dorado.

---

### D8 — Temperatura 0 y prompt versionado

**Decisión.** `temperature = 0` porque el requerimiento es reproducibilidad normativa, no
creatividad. Los prompts viven en `src/prompts.py` con `PROMPT_VERSION`, y la versión queda
grabada en cada traza, de modo que una respuesta antigua puede reproducirse exactamente con
el prompt con que fue generada. Se conserva `SYSTEM_RESPUESTA_V1_BASELINE` para comparaciones
A/B documentadas.

---

### D9 — Control de ventana de contexto en 6.000 caracteres / top-k = 4

**Problema.** Más contexto no es mejor contexto: degrada la atención al fragmento correcto y
encarece cada llamada.
**Decisión.** top-k final = 4 chunks y recorte duro a 6.000 caracteres respetando el orden de
relevancia, con marca explícita `[...truncado por control de contexto]` para que el truncado
sea visible en la auditoría.

---

### D10 — Traza auditable como artefacto de primera clase

**Decisión.** Cada respuesta produce un JSON con consulta original y anonimizada, PII
detectada, categoría, reformulación, fuentes consultadas, chunks, scores, versión de prompt,
modo del LLM, latencia, bandera de abstención y verificación de citas. Este objeto es la
evidencia que permite responder a una auditoría interna o a un requerimiento de la
Superintendencia sobre por qué el sistema respondió lo que respondió.

---

## Limitaciones del modelo asumidas explícitamente

1. **Alucinación residual.** Mitigada, no eliminada: prompt de abstención + gate de confianza
   + verificación de citas. Queda como control final la revisión humana en decisiones que
   afecten garantías del paciente.
2. **Desactualización del corpus.** El modelo no sabe qué versión está vigente; lo sabe la
   metadata. Por eso la vigencia viaja en cada chunk y el prompt obliga a declararla.
3. **Sesgo de recuperación.** Si un documento no está en el corpus, el sistema no puede
   saberlo; por eso la abstención debe nombrar la unidad a consultar.
4. **Dependencia de un proveedor externo.** Mitigada por la capa `llm.py`, que aísla el
   proveedor detrás de una interfaz y permite sustituirlo por un modelo local.
