CREATE TABLE dbo.UbicacionLote (
    id INT IDENTITY(1,1) NOT NULL,
    entradaloteid INT NOT NULL,
    nroPallete VARCHAR(50) NOT NULL,
    cantidad DECIMAL(18,2) NOT NULL,
    ubicacion VARCHAR(100) NULL, -- NULL = pendiente de migrar (Excel sin ubicación)
    
    -- Columna para Soft Delete (1: Activo, 0: Inactivo/Eliminado)
    estado BIT NOT NULL CONSTRAINT DF_UbicacionLote_Estado DEFAULT (1),

    -- Clave null-safe para unicidad (NULL -> ##SIN_UBICAR##)
    ubicacion_key AS (ISNULL(UPPER(LTRIM(RTRIM(ubicacion))), '##SIN_UBICAR##')) PERSISTED,

    -- Llave Primaria
    CONSTRAINT PK_UbicacionLote PRIMARY KEY CLUSTERED (id),

    -- Llave Foránea hacia la tabla entradalote
    CONSTRAINT FK_UbicacionLote_EntradaLote 
        FOREIGN KEY (entradaloteid) 
        REFERENCES dbo.entradalote (id),

    -- Regla de integridad
    CONSTRAINT CK_UbicacionLote_Cantidad CHECK (cantidad >= 0)
);
GO

-- 1. Índice por nroPallete para búsquedas rápidas por Pallet
CREATE NONCLUSTERED INDEX IX_UbicacionLote_NroPallete 
ON dbo.UbicacionLote (nroPallete)
WHERE estado = 1;
GO

-- 2. Índice filtrado para consultas de lotes activos
CREATE NONCLUSTERED INDEX IX_UbicacionLote_EntradaLoteID_Activos 
ON dbo.UbicacionLote (entradaloteid)
INCLUDE (nroPallete, cantidad, ubicacion)
WHERE estado = 1;
GO

-- 3. Unicidad por (lote, ubicación) null-safe: 1 fila por lote+ubicación (NULL=sumado).
CREATE UNIQUE NONCLUSTERED INDEX UQ_UbicacionLote_Lote_Ubicacion
ON dbo.UbicacionLote (entradaloteid, ubicacion_key)
WHERE estado = 1;
GO