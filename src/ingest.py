"""Ingesta y segmentacion (chunking) del corpus documental.

Estrategia: segmentacion jerarquica consciente de la estructura del documento
(encabezados markdown) con respaldo por ventana deslizante. Cada chunk conserva la
metadata de trazabilidad exigida por el caso: id de documento, version, vigencia,
unidad responsable, seccion de origen y tipo de fuente (interna/externa).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable

from .config import CONFIG, RAGConfig


@dataclass
class Chunk:
    chunk_id: str
    texto: str
    doc_id: str
    titulo: str
    seccion: str
    fuente: str            # "interno" | "externo"
    archivo: str
    version: str = ""
    vigencia_desde: str = ""
    vigencia_hasta: str = ""
    unidad_responsable: str = ""
    url: str = ""
    clasificacion: str = ""

    def cita(self) -> str:
        """Etiqueta de cita corta que el modelo debe reproducir en su respuesta."""
        partes = [self.doc_id]
        if self.version:
            partes.append(f"v{self.version}")
        if self.seccion:
            partes.append(self.seccion)
        return f"[{' | '.join(partes)}]"

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_frontmatter(texto: str) -> tuple[dict, str]:
    if not texto.startswith("---"):
        return {}, texto
    fin = texto.find("\n---", 3)
    if fin == -1:
        return {}, texto
    bloque = texto[3:fin].strip()
    cuerpo = texto[fin + 4:].lstrip("\n")
    meta = {}
    for linea in bloque.splitlines():
        if ":" in linea:
            k, v = linea.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, cuerpo


def _dividir_por_secciones(cuerpo: str) -> list[tuple[str, str]]:
    """Divide por encabezados markdown (## / #) conservando el titulo de seccion."""
    lineas = cuerpo.splitlines()
    secciones: list[tuple[str, list[str]]] = []
    actual_titulo = "Encabezado"
    actual: list[str] = []
    for linea in lineas:
        if re.match(r"^#{1,3}\s+\S", linea):
            if actual:
                secciones.append((actual_titulo, actual))
            actual_titulo = linea.lstrip("#").strip()
            actual = []
        else:
            actual.append(linea)
    if actual:
        secciones.append((actual_titulo, actual))
    return [(t, "\n".join(c).strip()) for t, c in secciones if "\n".join(c).strip()]


def _ventana(texto: str, size: int, overlap: int) -> Iterable[str]:
    if len(texto) <= size:
        yield texto
        return
    inicio = 0
    while inicio < len(texto):
        fin = min(inicio + size, len(texto))
        # cortar en el limite de oracion mas cercano hacia atras
        if fin < len(texto):
            corte = texto.rfind(". ", inicio + int(size * 0.5), fin)
            if corte != -1:
                fin = corte + 1
        yield texto[inicio:fin].strip()
        if fin >= len(texto):
            break
        inicio = max(fin - overlap, inicio + 1)


def cargar_documento(ruta: Path, fuente: str, cfg: RAGConfig = CONFIG) -> list[Chunk]:
    crudo = ruta.read_text(encoding="utf-8")
    meta, cuerpo = _parse_frontmatter(crudo)
    doc_id = meta.get("id", ruta.stem)
    chunks: list[Chunk] = []
    n = 0
    for seccion, contenido in _dividir_por_secciones(cuerpo):
        for trozo in _ventana(contenido, cfg.chunk_size, cfg.chunk_overlap):
            if len(trozo) < 40:
                continue
            n += 1
            chunks.append(Chunk(
                chunk_id=f"{doc_id}#{n:03d}",
                texto=trozo,
                doc_id=doc_id,
                titulo=meta.get("titulo", ruta.stem),
                seccion=seccion,
                fuente=fuente,
                archivo=ruta.name,
                version=meta.get("version", ""),
                vigencia_desde=meta.get("vigencia_desde", ""),
                vigencia_hasta=meta.get("vigencia_hasta", ""),
                unidad_responsable=meta.get("unidad_responsable", ""),
                url=meta.get("url", ""),
                clasificacion=meta.get("clasificacion", meta.get("tipo", "")),
            ))
    return chunks


def cargar_corpus(cfg: RAGConfig = CONFIG) -> list[Chunk]:
    todos: list[Chunk] = []
    for fuente, carpeta in cfg.fuentes.items():
        if not Path(carpeta).exists():
            continue
        for ruta in sorted(Path(carpeta).glob("*.md")):
            todos.extend(cargar_documento(ruta, fuente, cfg))
    return todos


if __name__ == "__main__":
    c = cargar_corpus()
    print(f"{len(c)} chunks desde {len({x.doc_id for x in c})} documentos")
    for ch in c[:3]:
        print(" -", ch.chunk_id, "|", ch.seccion[:50], "|", len(ch.texto), "chars")
