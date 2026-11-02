# Evidencias de pruebas y funcionamiento

Todo lo de esta carpeta se regenera con los comandos indicados (ver README principal, sección 3).

## Capturas (`capturas/`)

| Archivo | Qué muestra | Indicador |
|---|---|---|
| `01_pruebas.png` | 49/49 pruebas aprobadas (21 RAG EP1 + 28 agente EP2) | IE1–IE5 |
| `02_escenario_E2.png` | Caso en dos sesiones: se suspende por falta de antecedentes y se retoma desde el checkpoint | IE3, IE5 |
| `03_escenario_E3.png` | Reclamo por trato: el RAG cita MAN-003 §5 y el agente inserta un escalamiento que se ejecuta primero | IE1, IE4, IE5 |
| `04_escenario_E5.png` | Tres sesiones con condiciones cambiantes: llamada sin contacto y feriado nuevo | IE5 |
| `05_estado_checkpoint.png` | Estado persistido del folio: plan con origen de cada paso y bitácora | IE3 |
| `06_memoria_largo_plazo.png` | Búsqueda semántica en la memoria de largo plazo | IE4 |

## Salidas de texto y datos

| Archivo | Comando que lo genera |
|---|---|
| `salida_pruebas.txt` | `python -m pytest tests/ -v` |
| `demo_escenarios.txt` | `python -m src.agente.cli reiniciar` y `python -m src.agente.cli todos` |
| `escenarios/E*.json` | ídem: traza por escenario (sesiones, bitácora, plan final, hechos y registro OIRS) |
| `documentos_generados/<folio>/` | documentos que redactó el agente (respuestas OIRS, minuta, solicitud de antecedentes, acuse) |
| `estado_checkpoint_E2.txt` | `python -m src.agente.cli estado --folio OIRS-2026-0102` |
| `busqueda_memoria_largo_plazo.txt` | `python -m src.agente.cli memoria --buscar "sospecha de cancer sin formulario"` |
| `salida_evaluacion_rag.txt`, `resultados_evaluacion.json` | `python -m src.evaluate` (métricas del RAG) |
| `ablacion_recuperador.json` | `python -m src.ablacion` |

La integración continua (`.github/workflows/pruebas.yml`) vuelve a ejecutar pruebas, escenarios y
métricas con LangGraph instalado desde PyPI en cada push; el resultado queda en la pestaña *Actions*.
