"""Configuracion central del asistente RAG del CESFAM."""
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
INTERNOS_DIR = DATA_DIR / "internos"
EXTERNOS_DIR = DATA_DIR / "externos"
EVIDENCIAS_DIR = BASE_DIR / "evidencias"


@dataclass
class RAGConfig:
    # --- Chunking ---
    # 900 caracteres ~ 220 tokens: mantiene una seccion normativa completa
    # (un articulo o un paso de protocolo) sin fragmentar la unidad de sentido.
    chunk_size: int = 900
    chunk_overlap: int = 150

    # --- Recuperacion ---
    top_k_dense: int = 8       # candidatos del recuperador semantico
    top_k_sparse: int = 8      # candidatos del recuperador lexico (BM25)
    top_k_final: int = 4       # evidencia efectivamente enviada al LLM
    rrf_k: int = 60            # constante de Reciprocal Rank Fusion
    umbral_confianza: float = 0.12   # score RRF minimo
    umbral_bm25: float = 4.5         # evidencia lexica minima para NO abstenerse

    # --- Control de contexto ---
    max_chars_contexto: int = 6000
    incluir_externos_por_defecto: bool = True

    # --- Politica de datos ---
    anonimizar_consulta: bool = True
    bloquear_si_pii_no_anonimizable: bool = True

    # --- Modelo ---
    modelo: str = "claude-sonnet-4-5"
    temperatura: float = 0.0
    max_tokens_respuesta: int = 900

    fuentes: dict = field(default_factory=lambda: {
        "interno": INTERNOS_DIR,
        "externo": EXTERNOS_DIR,
    })


CONFIG = RAGConfig()
