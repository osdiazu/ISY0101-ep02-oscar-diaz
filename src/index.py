"""Indice hibrido: recuperador lexico (BM25) + recuperador semantico (denso).

Diseno defensivo: si `sentence-transformers`/`faiss` estan instalados se usan
embeddings densos reales; si no, el sistema degrada a una representacion vectorial
TF-IDF + SVD (LSA) con similitud coseno, de modo que el pipeline es ejecutable y
reproducible por cualquier evaluador sin GPU ni claves de API.
"""
from __future__ import annotations

import math
import pickle
import re
from collections import Counter
from pathlib import Path

import numpy as np

from .config import CONFIG, RAGConfig
from .ingest import Chunk, cargar_corpus

_TOKEN = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)
STOPWORDS = {
    "de", "la", "el", "en", "y", "a", "los", "las", "del", "se", "un", "una", "por",
    "con", "para", "que", "es", "al", "lo", "su", "o", "como", "mas", "sus", "ya",
    "cuando", "sobre", "este", "esta", "entre", "si", "no", "the", "of",
}


def tokenizar(texto: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(texto) if t.lower() not in STOPWORDS and len(t) > 1]


class BM25:
    """Implementacion propia de Okapi BM25 (sin dependencias externas)."""

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = corpus_tokens
        self.N = len(corpus_tokens)
        self.avgdl = sum(len(d) for d in corpus_tokens) / max(self.N, 1)
        self.tf = [Counter(d) for d in corpus_tokens]
        df = Counter()
        for d in corpus_tokens:
            df.update(set(d))
        self.idf = {
            t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()
        }

    def score(self, consulta: list[str]) -> np.ndarray:
        scores = np.zeros(self.N)
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i]) or 1
            s = 0.0
            for t in consulta:
                f = tf.get(t)
                if not f:
                    continue
                s += self.idf.get(t, 0.0) * (f * (self.k1 + 1)) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                )
            scores[i] = s
        return scores


class IndiceHibrido:
    def __init__(self, chunks: list[Chunk], cfg: RAGConfig = CONFIG):
        self.cfg = cfg
        self.chunks = chunks
        self.textos = [f"{c.titulo}. {c.seccion}. {c.texto}" for c in chunks]
        self.bm25 = BM25([tokenizar(t) for t in self.textos])
        self.backend, self.matriz, self._encoder = self._construir_denso()

    # ----- recuperador semantico -----
    def _construir_denso(self):
        try:  # ruta preferente en produccion
            from sentence_transformers import SentenceTransformer  # type: ignore
            modelo = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            emb = modelo.encode(self.textos, normalize_embeddings=True)
            return "sentence-transformers", np.asarray(emb), modelo
        except Exception:
            from sklearn.decomposition import TruncatedSVD
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import Normalizer

            n_comp = max(2, min(128, len(self.textos) - 1))
            pipe = make_pipeline(
                TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True),
                TruncatedSVD(n_components=n_comp, random_state=42),
                Normalizer(copy=False),
            )
            emb = pipe.fit_transform(self.textos)
            return "tfidf-svd (fallback local)", np.asarray(emb), pipe

    def _vector_consulta(self, consulta: str) -> np.ndarray:
        if self.backend.startswith("sentence"):
            return np.asarray(self._encoder.encode([consulta], normalize_embeddings=True))[0]
        return np.asarray(self._encoder.transform([consulta]))[0]

    # ----- busqueda -----
    def buscar(self, consulta: str, fuentes: set[str] | None = None) -> list[tuple[Chunk, float, dict]]:
        """Devuelve chunks ordenados por Reciprocal Rank Fusion de ambos recuperadores."""
        q_tokens = tokenizar(consulta)
        s_sparse = self.bm25.score(q_tokens)
        s_dense = self.matriz @ self._vector_consulta(consulta)

        permitidos = [
            i for i, c in enumerate(self.chunks)
            if fuentes is None or c.fuente in fuentes
        ]
        if not permitidos:
            return []

        def ranking(scores: np.ndarray, k: int) -> list[int]:
            orden = sorted(permitidos, key=lambda i: -scores[i])
            return orden[:k]

        r_sparse = ranking(s_sparse, self.cfg.top_k_sparse)
        r_dense = ranking(s_dense, self.cfg.top_k_dense)

        fusion: dict[int, float] = {}
        for rank, i in enumerate(r_sparse):
            fusion[i] = fusion.get(i, 0.0) + 1.0 / (self.cfg.rrf_k + rank + 1)
        for rank, i in enumerate(r_dense):
            fusion[i] = fusion.get(i, 0.0) + 1.0 / (self.cfg.rrf_k + rank + 1)

        salida = []
        for i, score in sorted(fusion.items(), key=lambda kv: -kv[1]):
            salida.append((self.chunks[i], score, {
                "bm25": float(s_sparse[i]),
                "denso": float(s_dense[i]),
                "rrf": float(score),
                "en_lexico": i in r_sparse,
                "en_semantico": i in r_dense,
            }))
        return salida

    # ----- persistencia -----
    def guardar(self, ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "wb") as fh:
            pickle.dump(self, fh)

    @staticmethod
    def cargar(ruta: Path) -> "IndiceHibrido":
        with open(ruta, "rb") as fh:
            return pickle.load(fh)


def construir_indice(cfg: RAGConfig = CONFIG) -> IndiceHibrido:
    return IndiceHibrido(cargar_corpus(cfg), cfg)


if __name__ == "__main__":
    idx = construir_indice()
    print("Backend denso:", idx.backend, "| chunks:", len(idx.chunks))
    for c, s, d in idx.buscar("plazo para emitir la constancia GES")[:3]:
        print(f"{s:.4f} {c.chunk_id} {c.seccion[:40]}")
