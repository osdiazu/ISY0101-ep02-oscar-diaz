# Bocetos de diseño — EP2

## 1. Esquema del estado del caso (`EstadoCaso`)

```
EstadoCaso
├── folio, sesion, fecha_actual
├── mensajes[]            (append)  ← una entrada por sesión
├── texto, datos, pii               ← entrada anonimizada + formulario
├── clasificacion {tipo, banderas, unidad}
├── prioridad                       ← solo sube: baja < media < alta < crítica
├── plan[] {id, accion, args, prioridad, depende_de, estado, origen, proposito}
├── version_plan
├── hechos {}                       ← memoria de trabajo: plazos, normativa, requisitos…
├── eventos_pendientes[] · eventos_historial[]
├── estado_caso · esperando
├── memoria_recuperada {casos, lecciones}
└── bitacora[]            (reducer con compactación)
```

## 2. Ciclo de vida de un caso

```
            ┌──────────── antecedentes_recibidos ───────────┐
            ▼                                               │
 abierto ──► pendiente_antecedentes ────────────────────────┘
    │
    ├──► en_seguimiento ──(contactado)──► cerrado
    │        │ (sin_contacto / feriado) ↺
    ├──► respondido   (borrador para firma de jefatura)
    ├──► derivado     (sin respaldo documental)
    └──► escalado     (herramienta no disponible tras reintentos)
```

## 3. Interacción por consola (boceto de la demo)

```
$ python -m src.agente.cli escenario escenarios/E2_ficha_tercero_dos_sesiones.json

--- sesion 1 (2026-11-02): Solicito copia de la ficha clinica de mi hermano…
  ◆ [s1 ingreso   ] caso nuevo clasificado como 'solicitud_ficha'
  ▤ [s1 planificar] plan v1: R1 > F2 > F3 > F4 > F5 > F6 > F7 > F8
  ▸ [s1 ejecutar  ] F3 [razonamiento] verificar_requisitos_ficha -> cumple=False
  ⚡ [s1 planificar] faltan_antecedentes: faltan: mandato_notarial
  ↻ [s1 planificar] plan v2: ~F4..F8 suspendidos | +A1 solicitud | +A2 estado
  => estado=pendiente_antecedentes

--- sesion 2 (2026-11-06): Vuelvo con el mandato notarial…
  ◆ [s2 ingreso   ] se retoma el caso desde el checkpoint (plan v2, 12 entradas)
  ↻ [s2 planificar] plan v3: +V1 verificar | ↺ F4..F8 reactivados
  ▸ [s2 ejecutar  ] F4 calcular_plazo -> 2026-11-13
  => estado=respondido
```

Leyenda: ◆ decisión · ▤ plan · ▸ herramienta · ⚡ evento · ↻ replanificación · ◎ memoria

## 4. Plantillas de plan por tipo de caso

| Tipo | Pasos de la plantilla (prioridad) | Ramas condicionales |
|---|---|---|
| reclamo | registrar(1) · plazo 15h(1) · prioridad(1) · normativa(2) · redactar(3) · estado(3) | +GES: normativa FCIP + verificar cumplimiento · +trato/negligencia: normativa escalamiento |
| solicitud_ficha | registrar · normativa PRO-006 · requisitos · plazo 5h · prioridad · tarea archivo · redactar · estado | suspensión si faltan antecedentes |
| rescate_nsp | registrar · normativa PRO-007 · plazo 5h · prioridad · tarea llamada · estado en seguimiento | < 3 inasistencias: no aplica |
| consulta | registrar · plazo 10h · normativa (exige respaldo) · redactar · estado | sin respaldo: derivar |
