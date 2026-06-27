-- Migration: rename ingestion tables to assetinfo
-- ingestion_pipeline_runs → assetinfo_pipeline_runs
-- ingestion_sheet_runs    → assetinfo_sheet_runs
--
-- These tables were originally named after the "ingestion" module (疏忽命名).
-- The canonical name is now "assetinfo" to match module/URL/env-var conventions.
-- Data is preserved; only table names and associated indexes change.

-- Step 1: rename tables
ALTER TABLE ingestion_pipeline_runs RENAME TO assetinfo_pipeline_runs;
ALTER TABLE ingestion_sheet_runs    RENAME TO assetinfo_sheet_runs;

-- Step 2: rename indexes on assetinfo_pipeline_runs
ALTER INDEX IF EXISTS idx_ingestion_pipeline_runs_created_by
    RENAME TO idx_assetinfo_pipeline_runs_created_by;
ALTER INDEX IF EXISTS idx_ingestion_pipeline_runs_product_date
    RENAME TO idx_assetinfo_pipeline_runs_product_date;

-- Step 3: rename indexes on assetinfo_sheet_runs
ALTER INDEX IF EXISTS idx_ingestion_sheet_runs_pipeline
    RENAME TO idx_assetinfo_sheet_runs_pipeline;
ALTER INDEX IF EXISTS idx_ingestion_sheet_runs_source
    RENAME TO idx_assetinfo_sheet_runs_source;
ALTER INDEX IF EXISTS idx_ingestion_sheet_runs_product
    RENAME TO idx_assetinfo_sheet_runs_product;
