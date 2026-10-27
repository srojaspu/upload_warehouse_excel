"""Dominio puro: normalización de llaves Excel <-> entradaLote.

Sin dependencias de DB/frameworks. Todo determinista y testeable.
"""
from __future__ import annotations

import re

import pandas as pd

SIN_UBICAR = "##SIN_UBICAR##"
_WS = re.compile(r"\s+")


def _is_missing(v) -> bool:
    try:
        return bool(pd.isna(v))
    except Exception:
        return v is None


def norm_text(v) -> str | None:
    """UPPER + trim + colapso de espacios. '' / 'nan' / NaN -> None."""
    if v is None or _is_missing(v):
        return None
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return None
    s = _WS.sub(" ", s).upper()
    return s or None


def norm_import(v) -> str | None:
    """'IMPO 118-26 NORTHCASTLE' -> '118-26 NORTHCASTLE' (normalizado)."""
    s = norm_text(v)
    if s is None:
        return None
    if s == "IMPO":
        return None
    if s.startswith("IMPO "):
        s = s[5:].strip()
    return _WS.sub(" ", s).strip() or None


def norm_codigo(v) -> str | None:
    return norm_text(v)


def norm_lote(v) -> str | None:
    return norm_text(v)


def norm_pallet_raw(v) -> str | None:
    """Normaliza nroPallet de DB: case/espacios. No repara '1P' vs 'P1'."""
    return norm_text(v)


def norm_ubicacion(v) -> str | None:
    """None si pendiente (NULL). Conserva None para INSERT NULL."""
    return norm_text(v)


def ubicacion_key(v) -> str:
    """Clave no-nula para agrupar/comparar: NULL -> SIN_UBICAR."""
    n = norm_ubicacion(v)
    return n if n is not None else SIN_UBICAR


def build_pallet(palet, categoria) -> str | None:
    """Reconstruye 'P{n} CATEGORIA' desde columnas Excel PALET+CATEGORIA.

    PALET no numérico (ej. 'PRIORIDAD'): devuelve normalizado sin inventar.
    """
    pal_missing = palet is None or _is_missing(palet) or str(palet).strip() == ""
    cat_missing = categoria is None or _is_missing(categoria) or str(categoria).strip() == ""
    if pal_missing and cat_missing:
        return None
    c = norm_text(categoria)
    if not pal_missing:
        try:
            n = int(float(str(palet).strip()))
            base = f"P{n}"
            return f"{base} {c}".strip() if c else base
        except (ValueError, TypeError):
            p = norm_text(palet)
            if p and c and c not in p:
                return f"{p} {c}"
            return p or c
    return c
