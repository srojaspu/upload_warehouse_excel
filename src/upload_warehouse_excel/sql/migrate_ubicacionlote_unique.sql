-- Migración SOLO dbo.UbicacionLote (tabla nueva). No toca otras tablas.
-- 1) Consolida duplicados existentes: 1 fila por (entradaloteid, ubicacion_key) sumando cantidad.
-- 2) Crea columna computada + UNIQUE filtrado para blindar recargas.
-- Idempotente: puede correrse N veces.

-- Paso 1: sumar cantidad en el superviviente MIN(id) por grupo activo.
WITH norm AS (
    SELECT id, entradaloteid, cantidad, ubicacion,
           COALESCE(UPPER(LTRIM(RTRIM(ubicacion))), '##SIN_UBICAR##') AS ubi_key
    FROM dbo.UbicacionLote
    WHERE estado = 1
),
sums AS (
    SELECT entradaloteid, ubi_key, SUM(cantidad) AS total, MIN(id) AS keep_id
    FROM norm
    GROUP BY entradaloteid, ubi_key
)
UPDATE u
SET cantidad = s.total
FROM dbo.UbicacionLote AS u
JOIN sums AS s ON s.keep_id = u.id;
GO

-- Paso 2: soft-delete duplicados (conserva MIN(id) por grupo).
WITH norm AS (
    SELECT id, entradaloteid,
           COALESCE(UPPER(LTRIM(RTRIM(ubicacion))), '##SIN_UBICAR##') AS ubi_key
    FROM dbo.UbicacionLote
    WHERE estado = 1
),
keep AS (
    SELECT entradaloteid, ubi_key, MIN(id) AS keep_id
    FROM norm
    GROUP BY entradaloteid, ubi_key
    HAVING COUNT(*) > 1
)
UPDATE u
SET estado = 0
FROM dbo.UbicacionLote AS u
JOIN norm AS n ON n.id = u.id
JOIN keep AS k ON k.entradaloteid = n.entradaloteid AND k.ubi_key = n.ubi_key
WHERE u.id <> k.keep_id AND u.estado = 1;
GO

-- Paso 3: columna computada para unicidad null-safe (solo si no existe).
IF COL_LENGTH('dbo.UbicacionLote', 'ubicacion_key') IS NULL
BEGIN
    ALTER TABLE dbo.UbicacionLote
    ADD ubicacion_key AS (ISNULL(UPPER(LTRIM(RTRIM(ubicacion))), '##SIN_UBICAR##')) PERSISTED;
END;
GO

-- Paso 4: UNIQUE filtrado (solo si no existe).
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UQ_UbicacionLote_Lote_Ubicacion' AND object_id = OBJECT_ID('dbo.UbicacionLote'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UQ_UbicacionLote_Lote_Ubicacion
    ON dbo.UbicacionLote (entradaloteid, ubicacion_key)
    WHERE estado = 1;
END;
GO
