"""Parametros del agente de gestion de casos (EP2)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..config import BASE_DIR, DATA_DIR

RUNTIME_DIR = Path(os.environ.get("CESFAM_RUNTIME_DIR", BASE_DIR / "runtime"))


@dataclass
class ConfigAgente:
    # --- Persistencia ---
    runtime_dir: Path = RUNTIME_DIR
    db_registro: str = "registro_oirs.sqlite"        # sistema OIRS simulado (escritura)
    db_checkpoints: str = "checkpoints.sqlite"       # memoria de corto plazo (LangGraph)
    db_memoria: str = "memoria_largo_plazo.sqlite"   # memoria semantica de largo plazo
    feriados: Path = DATA_DIR / "operacional" / "feriados_cl.json"

    # --- Control del bucle agentico ---
    max_iteraciones: int = 30        # tope de pasos ejecutados por sesion (anti-bucle)
    max_reintentos: int = 2          # reintentos por herramienta antes de escalar
    recursion_limit: int = 150       # limite de super-pasos del grafo LangGraph

    # --- Memoria de corto plazo ---
    max_bitacora: int = 40           # sobre este largo la bitacora se compacta en un resumen
    bitacora_conservar: int = 10     # entradas recientes que se conservan tras compactar

    # --- Memoria de largo plazo ---
    top_k_memoria: int = 3
    umbral_similitud: float = 0.30   # similitud coseno minima para considerar un caso "similar"

    def ruta(self, nombre: str) -> Path:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        (self.runtime_dir / "salidas").mkdir(exist_ok=True)
        return self.runtime_dir / nombre


CONFIG_AGENTE = ConfigAgente()
