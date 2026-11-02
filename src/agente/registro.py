"""Sistema OIRS simulado: destino de las herramientas de ESCRITURA.

Persistencia en SQLite (casos, tareas de derivacion y documentos emitidos) y archivos
markdown en `runtime/salidas/<folio>/`. Representa el sistema transaccional con el que
el agente se integra en el flujo de trabajo organizacional.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config_agente import CONFIG_AGENTE

ESQUEMA = """
CREATE TABLE IF NOT EXISTS casos (
    folio TEXT PRIMARY KEY, tipo TEXT, estado TEXT, prioridad TEXT,
    fecha_ingreso TEXT, fecha_limite TEXT, resumen TEXT, actualizado TEXT
);
CREATE TABLE IF NOT EXISTS tareas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, unidad TEXT, descripcion TEXT,
    fecha_limite TEXT, prioridad TEXT, estado TEXT DEFAULT 'abierta', creada TEXT
);
CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, tipo TEXT, ruta TEXT, creado TEXT
);
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, fecha TEXT, detalle TEXT
);
"""


class FalloSimulado(RuntimeError):
    """Falla inyectada para demostrar la recuperacion ante errores de herramientas."""


class _Inyector:
    """Permite programar fallas transitorias de una herramienta (pruebas y demo)."""

    def __init__(self):
        self.pendientes: dict[str, int] = {}

    def programar(self, herramienta: str, veces: int = 1) -> None:
        self.pendientes[herramienta] = self.pendientes.get(herramienta, 0) + veces

    def verificar(self, herramienta: str) -> None:
        if self.pendientes.get(herramienta, 0) > 0:
            self.pendientes[herramienta] -= 1
            raise FalloSimulado(f"{herramienta}: servicio no disponible (falla simulada)")

    def limpiar(self) -> None:
        self.pendientes.clear()


INYECTOR = _Inyector()


@contextmanager
def conexion():
    con = sqlite3.connect(CONFIG_AGENTE.ruta(CONFIG_AGENTE.db_registro))
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def upsert_caso(folio: str, **campos) -> dict:
    with conexion() as con:
        actual = con.execute("SELECT * FROM casos WHERE folio=?", (folio,)).fetchone()
        datos = dict(actual) if actual else {"folio": folio}
        datos.update({k: v for k, v in campos.items() if v is not None})
        cols = ["folio", "tipo", "estado", "prioridad", "fecha_ingreso", "fecha_limite", "resumen", "actualizado"]
        con.execute(
            f"INSERT OR REPLACE INTO casos ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [datos.get(c) for c in cols],
        )
        return {c: datos.get(c) for c in cols}


def obtener_caso(folio: str) -> dict | None:
    with conexion() as con:
        r = con.execute("SELECT * FROM casos WHERE folio=?", (folio,)).fetchone()
        if not r:
            return None
        caso = dict(r)
        caso["tareas"] = [dict(t) for t in con.execute("SELECT * FROM tareas WHERE folio=? ORDER BY id", (folio,))]
        caso["documentos"] = [dict(d) for d in con.execute("SELECT * FROM documentos WHERE folio=? ORDER BY id", (folio,))]
        return caso


def insertar_tarea(folio, unidad, descripcion, fecha_limite, prioridad, creada) -> int:
    with conexion() as con:
        cur = con.execute(
            "INSERT INTO tareas (folio, unidad, descripcion, fecha_limite, prioridad, creada) VALUES (?,?,?,?,?,?)",
            (folio, unidad, descripcion, fecha_limite, prioridad, creada),
        )
        return int(cur.lastrowid)


def cerrar_tareas(folio: str, patron: str) -> int:
    with conexion() as con:
        cur = con.execute(
            "UPDATE tareas SET estado='cerrada' WHERE folio=? AND estado='abierta' AND descripcion LIKE ?",
            (folio, f"%{patron}%"),
        )
        return cur.rowcount


def guardar_documento(folio: str, tipo: str, contenido: str, creado: str) -> str:
    carpeta = CONFIG_AGENTE.ruta("salidas") / folio
    carpeta.mkdir(parents=True, exist_ok=True)
    with conexion() as con:
        n = con.execute("SELECT COUNT(*) FROM documentos WHERE folio=?", (folio,)).fetchone()[0] + 1
        ruta = carpeta / f"{n:02d}_{tipo}.md"
        ruta.write_text(contenido, encoding="utf-8")
        rel = str(Path("runtime") / "salidas" / folio / ruta.name)
        con.execute("INSERT INTO documentos (folio, tipo, ruta, creado) VALUES (?,?,?,?)", (folio, tipo, rel, creado))
        return rel


def registrar_evento(folio: str, fecha: str, detalle: dict) -> None:
    with conexion() as con:
        con.execute("INSERT INTO eventos (folio, fecha, detalle) VALUES (?,?,?)",
                    (folio, fecha, json.dumps(detalle, ensure_ascii=False)))
