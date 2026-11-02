"""Procesos de memoria del agente (IL2.2).

Dos niveles, con responsabilidades distintas:

1. Memoria de CORTO PLAZO (de trabajo, por caso)
   - Checkpointer de LangGraph (`SqliteSaver`) indexado por `thread_id = folio`.
     Persiste el estado completo del grafo (plan, hechos, resultados, bitacora) al
     terminar cada super-paso, de modo que un caso que queda "pendiente de
     antecedentes" puede retomarse dias despues, en otra sesion o en otro proceso,
     exactamente donde quedo.
   - Compactacion de la bitacora: cuando supera `max_bitacora` entradas se resume y
     se conservan solo las recientes (control de la ventana de contexto en flujos
     prolongados), sin perder los hechos consolidados.

2. Memoria de LARGO PLAZO (semantica, entre casos)
   - Almacen SQLite con espacios de nombres (`casos`, `lecciones`) y vectores.
   - Recuperacion por similitud coseno: al ingresar un caso nuevo se recuperan casos
     resueltos parecidos y las lecciones aprendidas, que el planificador usa para
     ajustar el plan (p. ej. agregar una verificacion preventiva).
   - Embeddings: `sentence-transformers` multilingue si esta instalado; si no,
     `HashingVectorizer` de n-gramas de caracteres, que no requiere entrenamiento y
     produce vectores estables entre sesiones (requisito para un almacen persistente).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import numpy as np

from .config_agente import CONFIG_AGENTE, ConfigAgente

# ====================================================================== CORTO PLAZO


def crear_checkpointer(cfg: ConfigAgente = CONFIG_AGENTE, en_memoria: bool = False):
    """Devuelve el checkpointer de LangGraph para la memoria de corto plazo.

    `SqliteSaver` (paquete langgraph-checkpoint-sqlite) persiste en disco; si no esta
    disponible o se pide `en_memoria`, se usa `MemorySaver` (volatil, solo pruebas).
    """
    if not en_memoria:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver

            con = sqlite3.connect(cfg.ruta(cfg.db_checkpoints), check_same_thread=False)
            return SqliteSaver(con)
        except ImportError:
            pass
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


RESET = "__reset__"


def reducer_bitacora(actual: list | None, nuevo: list | None) -> list:
    """Reducer de LangGraph para la bitacora: agrega entradas y admite compactacion.

    Si la actualizacion comienza con el marcador RESET, reemplaza la bitacora completa
    (lo usa el nodo de compactacion); en otro caso concatena.
    """
    actual, nuevo = actual or [], nuevo or []
    if nuevo and isinstance(nuevo[0], dict) and nuevo[0].get(RESET):
        return list(nuevo[1:])
    return actual + list(nuevo)


def compactar_bitacora(bitacora: list[dict], cfg: ConfigAgente = CONFIG_AGENTE) -> tuple[list[dict], str] | None:
    """Si la bitacora excede el maximo, devuelve (nueva_bitacora, resumen)."""
    if len(bitacora) <= cfg.max_bitacora:
        return None
    antiguas = bitacora[: -cfg.bitacora_conservar]
    recientes = bitacora[-cfg.bitacora_conservar:]
    conteo: dict[str, int] = {}
    for e in antiguas:
        conteo[e.get("tipo", "?")] = conteo.get(e.get("tipo", "?"), 0) + 1
    hitos = [e["detalle"] for e in antiguas if e.get("tipo") in ("replan", "evento", "decision")]
    resumen = (f"Resumen de {len(antiguas)} entradas anteriores ("
               + ", ".join(f"{k}={v}" for k, v in sorted(conteo.items())) + "). Hitos: "
               + " | ".join(hitos[-8:]))
    nueva = [{"tipo": "resumen", "detalle": resumen}] + recientes
    return nueva, resumen


# ====================================================================== LARGO PLAZO


class Codificador:
    """Embeddings de texto con degradacion controlada (mismo criterio que la EP1)."""

    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._m = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            self.backend = "sentence-transformers"
        except Exception:
            from sklearn.feature_extraction.text import HashingVectorizer

            self._m = HashingVectorizer(analyzer="char_wb", ngram_range=(3, 5), n_features=2 ** 14,
                                        alternate_sign=False, norm="l2", lowercase=True)
            self.backend = "hashing-char-ngrams (fallback local)"

    def codificar(self, texto: str) -> np.ndarray:
        if self.backend.startswith("sentence"):
            return np.asarray(self._m.encode([texto], normalize_embeddings=True)[0], dtype=np.float32)
        return np.asarray(self._m.transform([texto]).toarray()[0], dtype=np.float32)


_CODIFICADOR: Codificador | None = None


def codificador() -> Codificador:
    global _CODIFICADOR
    if _CODIFICADOR is None:
        _CODIFICADOR = Codificador()
    return _CODIFICADOR


class MemoriaLargoPlazo:
    """Almacen semantico persistente con espacios de nombres.

    Interfaz inspirada en `BaseStore` de LangGraph (put / get / search por namespace),
    implementada sobre SQLite para no depender de un servicio vectorial externo
    (restriccion R5 de bajo presupuesto). Reemplazable por `PostgresStore` + pgvector
    sin cambiar a los consumidores.
    """

    def __init__(self, cfg: ConfigAgente = CONFIG_AGENTE):
        self.cfg = cfg
        self.con = sqlite3.connect(cfg.ruta(cfg.db_memoria), check_same_thread=False)
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS memorias (namespace TEXT, clave TEXT, texto TEXT, "
            "metadata TEXT, vector BLOB, creado TEXT, PRIMARY KEY (namespace, clave))"
        )
        self.con.commit()

    def put(self, namespace: str, clave: str, texto: str, metadata: dict | None = None) -> None:
        v = codificador().codificar(texto)
        self.con.execute(
            "INSERT OR REPLACE INTO memorias VALUES (?,?,?,?,?,?)",
            (namespace, clave, texto, json.dumps(metadata or {}, ensure_ascii=False),
             v.tobytes(), datetime.now().isoformat(timespec="seconds")),
        )
        self.con.commit()

    def get(self, namespace: str, clave: str) -> dict | None:
        r = self.con.execute("SELECT texto, metadata FROM memorias WHERE namespace=? AND clave=?",
                             (namespace, clave)).fetchone()
        return {"clave": clave, "texto": r[0], "metadata": json.loads(r[1])} if r else None

    def search(self, namespace: str, consulta: str, k: int | None = None,
               excluir: str | None = None, umbral: float | None = None) -> list[dict]:
        k = k or self.cfg.top_k_memoria
        umbral = self.cfg.umbral_similitud if umbral is None else umbral
        q = codificador().codificar(consulta)
        filas = self.con.execute("SELECT clave, texto, metadata, vector FROM memorias WHERE namespace=?",
                                 (namespace,)).fetchall()
        res = []
        for clave, texto, meta, blob in filas:
            if clave == excluir:
                continue
            v = np.frombuffer(blob, dtype=np.float32)
            if v.shape != q.shape:
                continue  # vector de otro backend: se ignora en vez de fallar
            sim = float(np.dot(q, v) / ((np.linalg.norm(q) * np.linalg.norm(v)) or 1.0))
            if sim >= umbral:
                res.append({"clave": clave, "texto": texto, "metadata": json.loads(meta), "similitud": round(sim, 3)})
        return sorted(res, key=lambda r: -r["similitud"])[:k]

    def contar(self, namespace: str | None = None) -> int:
        if namespace:
            return self.con.execute("SELECT COUNT(*) FROM memorias WHERE namespace=?", (namespace,)).fetchone()[0]
        return self.con.execute("SELECT COUNT(*) FROM memorias").fetchone()[0]

    def cerrar(self) -> None:
        self.con.close()
