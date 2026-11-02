# Propuesta de caso organizacional

## 1. Organización

**Centro de Salud Familiar (CESFAM) de la red de Atención Primaria de Salud (APS) municipal.**

- **Rubro:** salud pública, atención primaria.
- **Tamaño:** población inscrita ≈ 28.000 personas; dotación ≈ 120 funcionarios
  (médicos, enfermería, TENS, matronería, farmacia, SOME, OIRS, administrativos).
- **Contexto:** el CESFAM depende de un Servicio de Salud y opera bajo la normativa del
  Ministerio de Salud. Su documentación institucional está compuesta por protocolos clínicos
  y administrativos, circulares de dirección, manuales de procedimiento y un banco de
  preguntas frecuentes de la Oficina de Informaciones, Reclamos y Sugerencias (OIRS).

## 2. Problema / desafío

La documentación normativa y procedimental está **dispersa** (carpetas compartidas, correos,
impresos en mesón) y **versionada de forma irregular**. El personal de contacto —SOME, OIRS,
admisión y box— debe responder a diario consultas que requieren precisión normativa: plazos
de garantías GES, requisitos para entregar copia de ficha clínica, plazos de respuesta OIRS,
condiciones de teleconsulta, retiro de recetas por terceros.

Consecuencias observadas:

- **Respuestas heterogéneas** para una misma pregunta según quién atienda.
- **Reclamos evitables**: una fracción relevante de los reclamos OIRS se origina en
  información entregada de forma incompleta o incorrecta en el mesón.
- **Riesgo normativo**: contar mal el plazo de una garantía de oportunidad GES puede derivar
  en incumplimiento reclamable ante la Superintendencia de Salud.
- **Costo de inducción**: la rotación de personal administrativo obliga a reentrenar
  permanentemente sobre documentos que cambian de versión.
- **Tiempo**: el personal invierte del orden de 10–20 minutos en localizar el documento
  vigente cuando la consulta es poco frecuente.

## 3. Objetivos de la intervención

| # | Objetivo | Indicador | Meta |
|---|---|---|---|
| O1 | Reducir el tiempo de búsqueda documental | minutos promedio por consulta | < 1 min |
| O2 | Asegurar que toda respuesta tenga respaldo | % de respuestas con cita verificable | ≥ 95 % |
| O3 | Evitar respuestas sin respaldo (alucinación) | % de abstención correcta en consultas sin fuente | 100 % |
| O4 | Proteger datos personales de pacientes | fugas de PII hacia el modelo | 0 |
| O5 | Homogeneizar el criterio de respuesta | % de coincidencia con el dato normativo esperado | ≥ 90 % con LLM |
| O6 | Habilitar auditoría | % de interacciones con traza completa | 100 % |

## 4. Datos disponibles / simulables

**Internos (8 documentos, simulados con estructura real):** protocolo de ingreso y
notificación GES (PRO-001), protocolo de derivación SAPU → urgencia (PRO-002), manual de
respuesta OIRS (MAN-003), procedimiento de farmacia y receta retenida (PRO-004), circular de
teleconsulta (CIR-005), política de protección de datos y acceso a ficha (PRO-006),
procedimiento de agendamiento y rescate (PRO-007), banco de preguntas frecuentes (FAQ-008).
Todos con *front matter* de versión, vigencia y unidad responsable.

**Externos (4 documentos):** extractos de trabajo de la Ley 19.966 (Régimen GES), Ley 20.584
(derechos y deberes de las personas en atención de salud), Ley 21.719 (protección de datos
personales) y síntesis del procedimiento de reclamo ante la Superintendencia de Salud.

**No se utilizan** fichas clínicas, registros de pacientes ni bases con datos identificables.

## 5. Restricciones y requerimientos

- **R1.** Prohibido enviar datos identificables de pacientes a un modelo alojado fuera de la
  institución (política interna PRO-006 y Ley 21.719 sobre datos sensibles de salud).
- **R2.** Toda respuesta debe ser trazable al documento, versión y sección de origen.
- **R3.** El asistente no entrega orientación clínica individual ni diagnósticos.
- **R4.** Ante contradicción, prevalece la jerarquía normativa (ley > reglamento > protocolo
  interno) y, a igual jerarquía, la versión más reciente.
- **R5.** Debe operar con bajo presupuesto y sin GPU dedicada.
- **R6.** Debe distinguir explícitamente días hábiles de días corridos.

## 6. Por qué agentes de IA, LLM y RAG

Un buscador por palabra clave no resuelve el problema: el funcionario pregunta en lenguaje
natural y con siglas ("¿cuánto tengo para el FCIP?"), mientras que la respuesta está en un
párrafo específico de un documento versionado. Un LLM sin recuperación tampoco sirve: no
conoce los protocolos internos y, si los desconoce, los inventa —el riesgo más caro en un
contexto normativo.

RAG resuelve exactamente esa brecha: aporta el conocimiento institucional actualizado como
evidencia en el contexto, permite citar el origen y hace que actualizar el sistema sea
actualizar un documento, no reentrenar un modelo. La capa de **agente** añade lo que RAG puro
no cubre: enrutar la consulta a la fuente correcta (interna vs. normativa), expandir siglas
antes de recuperar, aplicar guardrails de datos personales, decidir abstenerse cuando la
evidencia es débil y verificar sus propias citas antes de entregar la respuesta.

## 7. Referencias y anexos

- Biblioteca del Congreso Nacional de Chile. *Ley 19.966, Régimen General de Garantías en
  Salud.* https://www.bcn.cl/leychile/navegar?idNorma=229834
- Biblioteca del Congreso Nacional de Chile. *Ley 20.584, Derechos y deberes de las personas
  en atención de salud.* https://www.bcn.cl/leychile/navegar?idNorma=1039348
- Biblioteca del Congreso Nacional de Chile. *Ley 21.719, Protección y tratamiento de datos
  personales.* https://www.bcn.cl/leychile/navegar?idNorma=1208650
- Superintendencia de Salud de Chile. *Reclamos y garantías GES.* https://www.superdesalud.gob.cl/
- Anexos del repositorio: `data/`, `docs/arquitectura.png`, `evidencias/`.
