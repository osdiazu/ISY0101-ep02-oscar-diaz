"""Herramienta de razonamiento temporal: dias habiles y corridos (requisito R6 de la EP1).

Dia habil = lunes a viernes que no es feriado nacional. Los feriados se leen de
`data/operacional/feriados_cl.json`, de modo que un feriado nuevo cambia los plazos
sin modificar codigo (condicion cambiante demostrada en las pruebas).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from .config_agente import CONFIG_AGENTE

_EXTRA: set[date] = set()   # feriados agregados en caliente (p. ej. feriado regional)


@lru_cache(maxsize=4)
def _cargar(ruta: str) -> frozenset[date]:
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return frozenset(date.fromisoformat(f) for f in datos["feriados"])


def feriados() -> set[date]:
    return set(_cargar(str(CONFIG_AGENTE.feriados))) | _EXTRA


def agregar_feriado(f: str) -> None:
    _EXTRA.add(date.fromisoformat(f))


def limpiar_feriados_extra() -> None:
    _EXTRA.clear()


def es_habil(d: date) -> bool:
    return d.weekday() < 5 and d not in feriados()


def sumar_dias(inicio: str, dias: int, tipo: str = "habiles") -> str:
    """Fecha limite contando `dias` desde el dia siguiente a `inicio`."""
    d = date.fromisoformat(inicio)
    if tipo == "corridos":
        return (d + timedelta(days=dias)).isoformat()
    n = 0
    while n < dias:
        d += timedelta(days=1)
        if es_habil(d):
            n += 1
    return d.isoformat()


def dias_habiles_entre(desde: str, hasta: str) -> int:
    """Dias habiles transcurridos entre dos fechas (excluye `desde`, incluye `hasta`).
    Negativo si `hasta` es anterior a `desde`."""
    a, b = date.fromisoformat(desde), date.fromisoformat(hasta)
    signo = 1
    if b < a:
        a, b, signo = b, a, -1
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if es_habil(d):
            n += 1
    return n * signo
