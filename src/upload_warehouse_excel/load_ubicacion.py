"""Caso de uso: Excel -> UbicacionLote (solo escribe UbicacionLote).

- Lee entradaLote/referenciaEntrada (solo SELECT, JOIN por referenciaEntradaId).
- Puente de 4 campos: (imp, pallet, codigo, lote) normalizados.
- Agrega por (puente + ubicacion) sumando Cant; NULL = pendiente.
- Recarga lógica por entradaloteid afectado: soft-delete + insert en transacción.
"""
from __future__ import annotations

import time
import uuid

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text

from .normalize import (
    SIN_UBICAR,
    build_pallet,
    norm_codigo,
    norm_import,
    norm_lote,
    norm_pallet_raw,
    norm_ubicacion,
    ubicacion_key,
)

LOTE_NULL = "##NULL_LOTE##"


def _find_col(df: pd.DataFrame, *cands: str) -> str:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for cand in cands:
        if cand.lower() in lower:
            return lower[cand.lower()]
    # búsqueda parcial (ej. 'import' encuentra 'N° IMPORTACION' / 'N° IMP')
    for cand in cands:
        for low, orig in lower.items():
            if cand.lower() in low:
                return orig
    raise KeyError(f"Columnas {cands} no encontradas en {list(df.columns)}")


def prepare_excel(df_total: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Normaliza y agrega Excel por (imp,pallet,codigo,lote,ubicacion)."""
    col_imp = _find_col(df_total, "N° IMPORTACION", "N° IMP", "IMPORTACION", "IMPORT")
    col_ubi = _find_col(df_total, "UBICACION")
    col_cant = _find_col(df_total, "Cant", "CANT", "CANTIDAD")
    col_palet = _find_col(df_total, "PALET")
    col_cat = _find_col(df_total, "CATEGORIA", "CATEG")
    col_cod = _find_col(df_total, "CODIGO")
    col_lote = _find_col(df_total, "LOTE")

    w = pd.DataFrame()
    w["cant_num"] = pd.to_numeric(df_total[col_cant], errors="coerce")
    w["imp_k"] = df_total[col_imp].map(norm_import)
    w["codigo_k"] = df_total[col_cod].map(norm_codigo)
    w["lote_raw"] = df_total[col_lote].map(norm_lote)
    w["lote_k"] = w["lote_raw"].fillna(LOTE_NULL)
    w["pallet_k"] = [
        norm_pallet_raw(build_pallet(p, c))
        for p, c in zip(df_total[col_palet], df_total[col_cat])
    ]
    w["ubicacion_norm"] = df_total[col_ubi].map(norm_ubicacion)
    w["ubicacion_k"] = df_total[col_ubi].map(ubicacion_key)

    stats = {
        "excel_total": int(len(w)),
        "excel_sin_ubicacion": int(w["ubicacion_norm"].isna().sum()),
        "excel_cant_nula": int(w["cant_num"].isna().sum()),
        "excel_imp_nulo": int(w["imp_k"].isna().sum()),
    }
    w["cant_num"] = w["cant_num"].fillna(0)

    # Filas sin llave mínima no pueden matchear: van a rechazados, no se pierden.
    valid = w["imp_k"].notna() & w["codigo_k"].notna() & w["pallet_k"].notna()
    stats["excel_sin_llave"] = int((~valid).sum())
    wv = w[valid].copy()

    agg = (
        wv.groupby(["imp_k", "pallet_k", "codigo_k", "lote_k", "ubicacion_k"], dropna=False)
        .agg(
            cantidad=("cant_num", "sum"),
            lineas=("cant_num", "size"),
            ubicacion_rep=("ubicacion_norm", "first"),
            pallet_rep=("pallet_k", "first"),
        )
        .reset_index()
    )
    stats["excel_grupos"] = int(len(agg))
    return agg, stats


def load_lote(engine: sa.Engine) -> pd.DataFrame:
    """Solo SELECT sobre otras tablas. JOIN correcto por referenciaEntradaId."""
    q = text(
        """
        SELECT el.id AS lote_id, re.numeroEntrada AS numero_entrada,
               el.nroPallet AS nro_pallet, el.codigoArticuloPu AS codigo,
               el.loteReal AS lote_real
        FROM dbo.entradaLote AS el
        JOIN dbo.referenciaEntrada AS re ON re.id = el.referenciaEntradaId
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(q, conn)
    df["imp_k"] = df["numero_entrada"].map(norm_import)
    df["pallet_k"] = df["nro_pallet"].map(norm_pallet_raw)
    df["codigo_k"] = df["codigo"].map(norm_codigo)
    df["lote_raw"] = df["lote_real"].map(norm_lote)
    df["lote_k"] = df["lote_raw"].fillna(LOTE_NULL)
    return df


def canonical_lote(df_lote: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """1 id canónico (MIN) por llave 4-campos. Reporta duplicados de origen."""
    valid = df_lote["imp_k"].notna() & df_lote["codigo_k"].notna() & df_lote["pallet_k"].notna()
    v = df_lote[valid].copy()
    g = (
        v.groupby(["imp_k", "pallet_k", "codigo_k", "lote_k"], dropna=False)
        .agg(canon_id=("lote_id", "min"), n_ids=("lote_id", "size"))
        .reset_index()
    )
    dup = g[g["n_ids"] > 1].copy()
    return g, dup


def resolve(
    excel_agg: pd.DataFrame, lote_canon: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """INNER por 4 campos. Devuelve (candidato, no_encontrados_excel)."""
    key = ["imp_k", "pallet_k", "codigo_k", "lote_k"]
    m = excel_agg.merge(lote_canon, on=key, how="left", indicator=True)
    matched = m[m["_merge"] == "both"].copy()
    missing = m[m["_merge"] == "left_only"].drop(columns=["_merge"]).copy()
    matched = matched.drop(columns=["_merge"])

    cand = pd.DataFrame()
    cand["entradaloteid"] = matched["canon_id"].astype(int)
    cand["nroPallete"] = matched["pallet_rep"].astype(str).str.slice(0, 50)
    cand["cantidad"] = matched["cantidad"].astype(float)
    cand["ubicacion"] = matched["ubicacion_rep"].where(
        matched["ubicacion_k"] != SIN_UBICAR, None
    )
    cand["ubicacion_k"] = matched["ubicacion_k"]
    # Defensa en profundidad: 1 fila por (lote, ubicacion).
    cand = (
        cand.groupby(["entradaloteid", "ubicacion_k"], dropna=False)
        .agg(
            nroPallete=("nroPallete", "first"),
            cantidad=("cantidad", "sum"),
            ubicacion=("ubicacion", "first"),
        )
        .reset_index()
    )
    dup = int(cand.duplicated(subset=["entradaloteid", "ubicacion_k"]).sum())
    if dup:
        raise ValueError(f"Candidato con {dup} duplicados en (entradaloteid,ubicacion)")
    if (cand["cantidad"] < 0).any() or cand["cantidad"].isna().any():
        raise ValueError("Cantidad negativa o nula en candidato")
    return cand, missing


# Única tabla con permiso de escritura en este proceso (decisión del dueño).
_TARGET_TABLE = "dbo.UbicacionLote"
_INSERT_CHUNK = 200  # filas por sentencia multi-row (200*4=800 params < 2100)


def _multi_row_insert_sql(n: int) -> str:
    """Una sentencia INSERT con n filas: 1 roundtrip por lote."""
    vals = ",".join(f"(:e{j},:p{j},:c{j},:u{j},1)" for j in range(n))
    return (
        f"INSERT INTO {_TARGET_TABLE} "
        "(entradaloteid, nroPallete, cantidad, ubicacion, estado) "
        f"VALUES {vals}"
    )


def upsert(
    engine: sa.Engine,
    cand: pd.DataFrame,
    trace_id: str | None = None,
    progress: bool = False,
) -> dict:
    """Recarga lógica por entradaloteid afectado. Solo escribe UbicacionLote."""
    t0 = time.perf_counter()
    trace_id = trace_id or uuid.uuid4().hex[:12]
    if cand.empty:
        return {"trace_id": trace_id, "insertados": 0, "desactivados": 0, "ms": 0}
    ids = sorted({int(i) for i in cand["entradaloteid"].tolist()})
    rows = [
        {
            "e": int(r.entradaloteid),
            "p": str(r.nroPallete)[:50],
            "c": float(r.cantidad),
            "u": (None if pd.isna(r.ubicacion) else str(r.ubicacion)[:100]),
        }
        for r in cand.itertuples()
    ]
    if any(not (r["c"] >= 0) for r in rows):
        raise ValueError("Cantidad negativa o nula en candidato")
    desactivados = 0
    batches = 0
    with engine.begin() as conn:
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            res = conn.execute(
                text(
                    f"UPDATE {_TARGET_TABLE} SET estado = 0 "
                    "WHERE estado = 1 AND entradaloteid IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": chunk},
            )
            desactivados += int(res.rowcount or 0)
        for i in range(0, len(rows), _INSERT_CHUNK):
            batch = rows[i : i + _INSERT_CHUNK]
            params: dict = {}
            for j, r in enumerate(batch):
                params[f"e{j}"] = r["e"]
                params[f"p{j}"] = r["p"]
                params[f"c{j}"] = r["c"]
                params[f"u{j}"] = r["u"]
            t1 = time.perf_counter()
            conn.execute(text(_multi_row_insert_sql(len(batch))), params)
            batches += 1
            if progress:
                print(
                    f"[{trace_id}] lote {batches}: {len(batch)} filas en "
                    f"{time.perf_counter() - t1:.1f}s",
                    flush=True,
                )
    ms = int((time.perf_counter() - t0) * 1000)
    return {
        "trace_id": trace_id,
        "lotes_afectados": len(ids),
        "insertados": len(rows),
        "desactivados": desactivados,
        "sentencias": batches,
        "ms": ms,
    }


def verify_no_duplicates(cand: pd.DataFrame) -> dict:
    return {
        "filas": int(len(cand)),
        "dup_clave": int(cand.duplicated(subset=["entradaloteid", "ubicacion_k"]).sum()),
        "nulos_ubicacion": int(cand["ubicacion"].isna().sum()),
    }
