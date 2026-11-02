"""Ejecutor de pruebas sin dependencias externas.

El proyecto esta escrito para `pytest`. Si el entorno del evaluador no tiene pytest
instalado (o no tiene salida a internet), este script inyecta un stub minimo de la
API usada (`fixture`, `mark.parametrize`) y ejecuta la misma suite, imprimiendo un
resumen equivalente. Uso:  python tests/run_tests.py
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def _instalar_stub_pytest() -> None:
    if importlib.util.find_spec("pytest"):
        return
    pytest = types.ModuleType("pytest")

    def fixture(*a, **kw):
        def deco(fn):
            fn.__is_fixture__ = True
            return fn
        return deco(a[0]) if a and callable(a[0]) else deco

    class _Mark:
        @staticmethod
        def parametrize(nombres, valores):
            def deco(fn):
                fn.__params__ = (nombres, valores)
                return fn
            return deco

    pytest.fixture = fixture
    pytest.mark = _Mark()
    pytest.raises = None
    sys.modules["pytest"] = pytest


def main() -> int:
    _instalar_stub_pytest()
    import importlib

    ok = fallos = 0
    for modulo in ("tests.test_rag_ep1", "tests.test_agente_ep2"):
        print(f"\n## {modulo}")
        o, f = _correr_suite(importlib.import_module(modulo))
        ok, fallos = ok + o, fallos + f
    print(f"\n{ok} passed, {fallos} failed")
    return 1 if fallos else 0


def _correr_suite(suite) -> tuple[int, int]:
    fixtures = {n: f for n, f in vars(suite).items() if getattr(f, "__is_fixture__", False)}
    cache: dict = {}

    def resolver(nombre):
        if nombre not in cache:
            cache[nombre] = fixtures[nombre]()
        return cache[nombre]

    ok = fallos = 0
    for nombre, fn in sorted(vars(suite).items()):
        if not (nombre.startswith("test_") and callable(fn)):
            continue
        params = getattr(fn, "__params__", None)
        casos = []
        if params:
            nombres = [n.strip() for n in params[0].split(",")]
            for valores in params[1]:
                valores = valores if isinstance(valores, (tuple, list)) else (valores,)
                casos.append(dict(zip(nombres, valores)))
        else:
            casos.append({})
        for kwargs in casos:
            firma = fn.__code__.co_varnames[: fn.__code__.co_argcount]
            for arg in firma:
                if arg in fixtures and arg not in kwargs:
                    kwargs[arg] = resolver(arg)
            etiqueta = nombre + (f"[{list(kwargs.values())[0]!r:.40}]" if params else "")
            try:
                fn(**kwargs)
                ok += 1
                print(f"PASS  {etiqueta}")
            except Exception:
                fallos += 1
                print(f"FAIL  {etiqueta}")
                traceback.print_exc(limit=2)
    return ok, fallos


if __name__ == "__main__":
    sys.exit(main())
