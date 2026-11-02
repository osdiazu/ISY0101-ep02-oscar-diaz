"""Genera el corpus documental simulado (fuentes internas y externas) del caso CESFAM.

Los documentos internos emulan la base documental real de un centro de atencion
primaria chileno (protocolos, circulares, manuales de orientacion al usuario).
Los documentos externos emulan extractos de normativa publica vigente.
"""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "data"
INT = BASE / "internos"
EXT = BASE / "externos"
INT.mkdir(parents=True, exist_ok=True)
EXT.mkdir(parents=True, exist_ok=True)

INTERNOS = {
"PRO-001_protocolo_ingreso_ges.md": """---
id: PRO-001
titulo: Protocolo de ingreso y notificacion de garantias GES
version: 4.2
vigencia_desde: 2025-03-01
vigencia_hasta: 2027-03-01
unidad_responsable: Subdireccion Clinica
clasificacion: interno-publicable
---

# Protocolo de ingreso y notificacion de garantias GES

## 1. Alcance
Aplica a todo el personal de admision, orientacion medica (OIRS) y box clinico del
CESFAM que detecte una sospecha o confirmacion diagnostica asociada a alguno de los
problemas de salud garantizados.

## 2. Regla operativa central
Toda sospecha GES debe quedar registrada en el Formulario de Constancia de Informacion
al Paciente GES (FCIP) **dentro de las mismas 24 horas habiles** de la atencion en que se
formula la sospecha. El FCIP se emite en tres copias: paciente, ficha clinica y
respaldo digital en el repositorio SIGGES.

## 3. Flujo paso a paso
1. El profesional clinico registra la sospecha en la ficha electronica con el codigo
   del problema de salud correspondiente.
2. Admision genera el FCIP y obtiene la firma del paciente o de su representante legal.
3. Si el paciente rechaza la firma, se deja constancia escrita del rechazo y se notifica
   a la Subdireccion Clinica el mismo dia.
4. La derivacion a nivel secundario se cursa por interconsulta electronica (SIC) con
   prioridad GES y el plazo de atencion se cuenta desde la fecha del FCIP, no desde la
   fecha de la interconsulta.

## 4. Plazos internos de gestion
- Emision del FCIP: 24 horas habiles desde la sospecha.
- Digitalizacion en SIGGES: 48 horas habiles desde la emision.
- Auditoria muestral de FCIP por Calidad: mensual, muestra minima de 30 casos.

## 5. Errores frecuentes detectados en auditoria 2025
- Contar el plazo de la garantia de oportunidad desde la interconsulta y no desde el FCIP.
- Emitir FCIP sin codigo de problema de salud, lo que impide el seguimiento en SIGGES.
- No registrar el rechazo de firma del paciente.
""",

"PRO-002_protocolo_derivacion_urgencia.md": """---
id: PRO-002
titulo: Protocolo de derivacion desde SAPU a urgencia hospitalaria
version: 2.7
vigencia_desde: 2024-11-15
vigencia_hasta: 2026-11-15
unidad_responsable: Jefatura SAPU
clasificacion: interno
---

# Protocolo de derivacion desde SAPU a urgencia hospitalaria

## 1. Categorizacion
Se utiliza la escala de categorizacion de 5 niveles (C1 a C5). La categorizacion la
realiza personal de enfermeria capacitado dentro de los primeros 10 minutos del ingreso.

- C1 (Emergencia vital): atencion medica inmediata, traslado con movil avanzado.
- C2 (Emergencia): atencion medica en un maximo de 30 minutos.
- C3 (Urgencia): atencion medica en un maximo de 90 minutos.
- C4 y C5 (Menor urgencia): pueden ser resueltos en el mismo SAPU o reagendados a
  morbilidad del dia siguiente.

## 2. Criterios de derivacion obligatoria a urgencia hospitalaria
- Dolor toracico con alteracion electrocardiografica o sospecha de sindrome coronario.
- Deficit neurologico focal de inicio menor a 4,5 horas.
- Trauma con compromiso de conciencia, Glasgow menor o igual a 13.
- Embarazada con metrorragia o con presion arterial mayor o igual a 160/110.
- Saturacion de oxigeno menor a 90% que no responde a oxigenoterapia inicial.

## 3. Traslado
El traslado C1 y C2 se solicita al SAMU por el fono de coordinacion regional. El registro
del traslado debe incluir hora de solicitud, hora de llegada del movil y hora de entrega
en el establecimiento receptor.

## 4. Contrarreferencia
El hospital receptor debe emitir contrarreferencia dentro de 7 dias corridos. Si no llega,
la unidad de gestion de pacientes del CESFAM debe reclamarla y dejar registro.
""",

"MAN-003_manual_oirs.md": """---
id: MAN-003
titulo: Manual de respuesta OIRS (solicitudes ciudadanas)
version: 3.1
vigencia_desde: 2025-01-02
vigencia_hasta: 2027-01-02
unidad_responsable: OIRS / Participacion Social
clasificacion: interno-publicable
---

# Manual de respuesta OIRS

## 1. Tipologia de solicitudes
Reclamo, sugerencia, felicitacion, consulta y solicitud de informacion (SFRCS).

## 2. Plazos de respuesta comprometidos
- Reclamo: 15 dias habiles desde el ingreso.
- Consulta y solicitud de informacion: 10 dias habiles.
- Sugerencia y felicitacion: acuse de recibo en 5 dias habiles.
Cuando la respuesta requiere informe de una unidad clinica, esta dispone de 7 dias habiles
para responder a OIRS; el plazo total con el usuario no se suspende.

## 3. Estructura obligatoria de la respuesta
1. Identificacion del folio y fecha de ingreso.
2. Sintesis de lo planteado por el usuario.
3. Antecedentes recabados (unidad consultada, ficha, registros).
4. Respuesta de fondo con fundamento normativo o de protocolo.
5. Medidas adoptadas y responsable.
6. Via de apelacion o derivacion a la Superintendencia de Salud cuando corresponda.

## 4. Lenguaje
Se exige lenguaje claro, sin siglas no explicadas, sin juicios sobre el usuario y sin
entregar datos clinicos de terceros. No se entregan diagnosticos por escrito a personas
distintas del titular o su representante acreditado.

## 5. Escalamiento
Reclamos que involucren presunta negligencia, trato vejatorio o dano fisico se derivan
el mismo dia a la Direccion y a Calidad y Seguridad del Paciente.
""",

"PRO-004_farmacia_y_recetas.md": """---
id: PRO-004
titulo: Procedimiento de entrega de farmacos y receta retenida
version: 1.9
vigencia_desde: 2025-06-01
vigencia_hasta: 2027-06-01
unidad_responsable: Quimico Farmaceutico
clasificacion: interno
---

# Procedimiento de entrega de farmacos y receta retenida

## 1. Recetas cronicas
Los pacientes en programa cardiovascular retiran mensualmente. La receta cronica tiene
vigencia de 6 meses, con control medico obligatorio antes de su renovacion.

## 2. Receta cheque y receta retenida
Los psicotropicos de la lista I y II requieren receta cheque emitida por medico con
registro vigente. La farmacia retiene el original y registra folio, RUT del paciente,
nombre del profesional y cantidad dispensada en el libro de control.

## 3. Quiebre de stock
Ante quiebre de stock se ofrece alternativa terapeutica solo con autorizacion escrita del
medico tratante. Se registra el quiebre en la planilla de disponibilidad y se informa a la
Direccion cuando supera 5 dias habiles.

## 4. Entrega a terceros
Un tercero puede retirar medicamentos presentando su cedula de identidad y la del paciente,
o poder simple firmado. Para receta cheque el retiro por terceros requiere poder notarial.
""",

"CIR-005_circular_teleconsulta.md": """---
id: CIR-005
titulo: Circular interna 12/2026 - Teleconsulta y registro
version: 1.0
vigencia_desde: 2026-02-10
vigencia_hasta: 2027-12-31
unidad_responsable: Direccion
clasificacion: interno
---

# Circular interna 12/2026: Teleconsulta y registro

1. La teleconsulta de morbilidad se habilita para controles de pacientes cronicos
   compensados y para entrega de resultados de examenes de baja complejidad.
2. No se permite teleconsulta para primera atencion de sospecha GES oncologica, salud
   mental con riesgo suicida, ni control de embarazo.
3. Toda teleconsulta debe registrarse en ficha con la modalidad explicita ("telefonica" o
   "videollamada"), la hora de inicio y de termino, y la identificacion verificada del
   paciente mediante al menos dos datos (RUT y fecha de nacimiento).
4. El consentimiento del paciente para la modalidad remota se registra verbalmente y se
   deja constancia en la ficha.
5. Las grabaciones de teleconsulta estan prohibidas salvo autorizacion escrita previa del
   paciente y de la Direccion.
""",

"PRO-006_proteccion_datos_ficha.md": """---
id: PRO-006
titulo: Politica interna de proteccion de datos y acceso a ficha clinica
version: 2.2
vigencia_desde: 2025-09-01
vigencia_hasta: 2027-09-01
unidad_responsable: Oficial de Datos / Direccion
clasificacion: interno-critico
---

# Politica interna de proteccion de datos y acceso a ficha clinica

## 1. Principio
La ficha clinica es un dato personal sensible. Su acceso se rige por necesidad de saber:
solo accede el personal que participa directamente en la atencion del paciente.

## 2. Quien puede solicitar copia
- El titular, acreditando identidad.
- El representante legal del titular, acreditando calidad.
- Un tercero con mandato expreso otorgado por escritura publica o ante notario.
- Tribunales de justicia, mediante oficio.

## 3. Plazo de entrega
La copia de ficha se entrega en un plazo maximo de 5 dias habiles desde la solicitud
formal, en formato digital cifrado o impreso con cargo de retiro.

## 4. Prohibiciones
- Enviar fichas o informes clinicos por canales de mensajeria personal.
- Usar datos de pacientes en herramientas externas que no cuenten con acuerdo de
  tratamiento de datos aprobado por la Direccion.
- Extraer bases de datos completas sin autorizacion del Oficial de Datos.

## 5. Uso de asistentes de inteligencia artificial
Se autoriza el uso de asistentes conversacionales institucionales solo sobre documentacion
normativa y de procedimientos. Queda prohibido ingresar datos identificables de pacientes
(nombre, RUT, direccion, numero de ficha) en los prompts. El sistema debe anonimizar antes
de enviar cualquier texto a un modelo de lenguaje alojado fuera de la institucion.
""",

"PRO-007_agendamiento_y_rescate.md": """---
id: PRO-007
titulo: Procedimiento de agendamiento, sobrecupo y rescate de inasistentes
version: 3.0
vigencia_desde: 2025-04-15
vigencia_hasta: 2027-04-15
unidad_responsable: SOME
clasificacion: interno
---

# Agendamiento, sobrecupo y rescate

## 1. Canales
Presencial, telefonico (call center comunal) y formulario web. La agenda de morbilidad del
dia se abre a las 08:00 y cierra al completar cupos.

## 2. Sobrecupo
El medico puede autorizar hasta 2 sobrecupos por jornada. La autorizacion queda registrada
con nombre del profesional y motivo.

## 3. Inasistencia (NSP)
Tres inasistencias consecutivas sin aviso en programas cronicos activan el protocolo de
rescate: llamada telefonica dentro de 5 dias habiles, y si no hay contacto, visita
domiciliaria del equipo de sector dentro de 15 dias habiles.

## 4. Priorizacion
Se priorizan adultos mayores de 80 anos, personas con discapacidad acreditada, embarazadas
y pacientes con sospecha GES vigente.
""",

"FAQ-008_preguntas_frecuentes_usuarios.md": """---
id: FAQ-008
titulo: Preguntas frecuentes de usuarios (banco OIRS 2025-2026)
version: 5.4
vigencia_desde: 2026-01-15
vigencia_hasta: 2027-01-15
unidad_responsable: OIRS
clasificacion: interno-publicable
---

# Preguntas frecuentes de usuarios

**Como cambio de CESFAM?**
Con cedula de identidad y un documento que acredite domicilio en el territorio del centro.
El cambio se hace efectivo dentro de 10 dias habiles.

**Cuanto demora una interconsulta a especialista no GES?**
No tiene garantia de plazo. El CESFAM entrega numero de SIC y el hospital prioriza segun
pertinencia clinica. El usuario puede consultar el estado en SOME con su numero de SIC.

**Que hago si perdi mi hora GES?**
Se reagenda sin perder la garantia siempre que la inasistencia se justifique dentro de
5 dias habiles. La garantia de oportunidad no se pierde por inasistencia justificada.

**Puedo atenderme si no estoy inscrito?**
La urgencia se atiende siempre, sin importar inscripcion ni prevision. Para atencion
programada se requiere inscripcion vigente.

**Donde reclamo si no estoy conforme con la respuesta del CESFAM?**
Ante la Superintendencia de Salud, o ante la Direccion de Servicio de Salud, adjuntando el
folio de la respuesta OIRS.
""",
}

EXTERNOS = {
"EXT-LEY19966_regimen_ges.md": """---
id: EXT-LEY19966
titulo: Ley 19.966 - Regimen General de Garantias en Salud (extracto de trabajo)
fuente: Biblioteca del Congreso Nacional de Chile
tipo: normativa-externa
url: https://www.bcn.cl/leychile/navegar?idNorma=229834
fecha_consulta: 2026-09-10
---

# Ley 19.966, Regimen General de Garantias en Salud (extracto)

**Garantias explicitas.** El Regimen establece garantias de acceso, calidad, oportunidad y
proteccion financiera para los problemas de salud definidos por decreto supremo.

**Garantia de acceso.** Obligacion del Fondo Nacional de Salud y de las Isapres de asegurar
las prestaciones garantizadas a sus beneficiarios en la forma y condiciones que determine
el decreto.

**Garantia de oportunidad.** Plazo maximo para el otorgamiento de las prestaciones, el que
se cuenta desde que se cumple el hito que la norma define para cada problema de salud. Si
el prestador designado no cumple, el beneficiario puede reclamar ante el asegurador, que
debe designar un segundo prestador.

**Garantia de proteccion financiera.** Contribucion maxima que el beneficiario debe pagar
por prestacion o grupo de prestaciones, expresada como porcentaje del arancel de referencia.

**Reclamo.** Los beneficiarios pueden reclamar el cumplimiento de las garantias ante la
Superintendencia de Salud, sin perjuicio de las acciones judiciales que procedan.

**Informacion al beneficiario.** El prestador debe informar al beneficiario que tiene
derecho a las garantias explicitas cuando se confirme la sospecha o el diagnostico del
problema de salud garantizado. Esta constancia es un requisito para el ejercicio de la
garantia de oportunidad.
""",

"EXT-LEY20584_derechos_deberes.md": """---
id: EXT-LEY20584
titulo: Ley 20.584 - Derechos y deberes de las personas en atencion de salud (extracto)
fuente: Biblioteca del Congreso Nacional de Chile
tipo: normativa-externa
url: https://www.bcn.cl/leychile/navegar?idNorma=1039348
fecha_consulta: 2026-09-10
---

# Ley 20.584 (extracto de trabajo)

**Trato digno.** Toda persona tiene derecho a recibir un trato digno y respetuoso en todo
momento y en cualquier circunstancia.

**Informacion.** La persona tiene derecho a ser informada en forma oportuna y comprensible
sobre su estado de salud, el posible diagnostico, las alternativas de tratamiento y los
riesgos. La informacion se entrega al titular y, cuando corresponda, a su representante.

**Consentimiento informado.** Toda persona tiene derecho a otorgar o denegar su voluntad
para someterse a cualquier procedimiento o tratamiento, de manera libre, voluntaria,
expresa e informada. La regla general es verbal; debe constar por escrito en intervenciones
quirurgicas, procedimientos invasivos y, en general, en aquellos de riesgo.

**Ficha clinica.** La ficha clinica es un instrumento de dato sensible. Los terceros que no
esten directamente relacionados con la atencion no tienen acceso. Pueden solicitar copia
el titular, su representante legal, un tercero con mandato expreso otorgado por escritura
publica, y los tribunales de justicia.

**Reclamo.** La persona tiene derecho a reclamar ante el prestador y, si no queda conforme,
ante la Superintendencia de Salud.

**Urgencia.** Los prestadores no pueden exigir garantia de pago ni condicionar la atencion
en situaciones de urgencia o emergencia vital.
""",

"EXT-LEY21719_datos_personales.md": """---
id: EXT-LEY21719
titulo: Ley 21.719 - Proteccion de datos personales (extracto de trabajo)
fuente: Biblioteca del Congreso Nacional de Chile
tipo: normativa-externa
url: https://www.bcn.cl/leychile/navegar?idNorma=1208650
fecha_consulta: 2026-09-10
---

# Ley 21.719 sobre proteccion y tratamiento de datos personales (extracto)

**Datos sensibles.** Los datos relativos a la salud y al perfil biologico humano son datos
personales sensibles y su tratamiento requiere consentimiento expreso del titular, salvo
las excepciones legales (entre ellas, fines de salud publica y la atencion sanitaria
prestada por profesionales sujetos a secreto).

**Principios.** Licitud, finalidad, proporcionalidad, calidad, responsabilidad, seguridad,
transparencia e informacion, y confidencialidad.

**Derechos ARCOP.** Acceso, rectificacion, cancelacion o supresion, oposicion y
portabilidad. El responsable debe responder las solicitudes en los plazos que fija la ley.

**Medidas de seguridad.** El responsable debe adoptar medidas tecnicas y organizativas
apropiadas al riesgo, incluyendo control de acceso, cifrado y registro de actividad.

**Encargados de tratamiento.** Cuando un tercero trata datos por cuenta del responsable,
debe existir un contrato que fije la finalidad, el alcance, la confidencialidad y la
prohibicion de uso para fines propios, incluido el entrenamiento de modelos.

**Agencia de Proteccion de Datos Personales.** Fiscaliza y sanciona. Las infracciones se
clasifican en leves, graves y gravisimas, con multas asociadas.
""",

"EXT-SUPERSALUD_reclamos.md": """---
id: EXT-SUPERSALUD
titulo: Superintendencia de Salud - Procedimiento de reclamo GES (sintesis)
fuente: Superintendencia de Salud de Chile
tipo: normativa-externa
url: https://www.superdesalud.gob.cl/
fecha_consulta: 2026-09-10
---

# Reclamo ante la Superintendencia de Salud (sintesis operativa)

1. El beneficiario reclama primero ante su asegurador (FONASA o Isapre) por incumplimiento
   de una garantia explicita. El asegurador debe designar un nuevo prestador.
2. Si persiste el incumplimiento o la respuesta no satisface, el beneficiario presenta
   reclamo ante la Intendencia de Fondos y Seguros Previsionales de Salud.
3. El reclamo puede presentarse en linea, presencialmente en las agencias regionales o por
   carta, adjuntando antecedentes: constancia de informacion al paciente GES, ordenes
   medicas, respuestas del prestador.
4. Tambien existe reclamo por trato o por calidad de la atencion ante la Intendencia de
   Prestadores, que puede derivar en fiscalizacion del establecimiento.
5. La Superintendencia no reemplaza al tribunal: no fija indemnizaciones civiles.
""",
}

for nombre, texto in INTERNOS.items():
    (INT / nombre).write_text(texto, encoding="utf-8")
for nombre, texto in EXTERNOS.items():
    (EXT / nombre).write_text(texto, encoding="utf-8")

print(f"Documentos internos: {len(INTERNOS)} | externos: {len(EXTERNOS)}")
