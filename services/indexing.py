"""Indexing workflows for local PXRD reference libraries."""

from __future__ import annotations

from pathlib import Path

from core.models import CodSyncReport, LibraryBuildConfig, LibraryStats
from database.builder import build_reference_library
from database.repository import SQLiteLibraryRepository
from services.cod_sync import sync_cod_incremental


def rebuild_local_library(
    cif_folder: str | Path,
    database_path: str | Path,
    config: LibraryBuildConfig,
) -> LibraryStats:
    """Rebuild local precomputed library from a CIF folder."""
    return build_reference_library(cif_folder=cif_folder, database_path=database_path, config=config)


def get_library_stats(database_path: str | Path) -> LibraryStats:
    """Return stats for local library, creating empty schema if needed."""
    repository = SQLiteLibraryRepository(database_path)
    return repository.get_stats()


def sync_cod_library_incremental(
    sync_root: str | Path,
    database_path: str | Path,
    config: LibraryBuildConfig,
    method: str = "svn",
    perform_remote_sync: bool = True,
) -> CodSyncReport:
    """Sync COD mirror and update local reference library incrementally."""
    return sync_cod_incremental(
        sync_root=sync_root,
        database_path=database_path,
        config=config,
        method=method,
        perform_remote_sync=perform_remote_sync,
    )
