"""Tests for local reference library build and query."""

from __future__ import annotations

import shutil
from pathlib import Path

from core.models import ExperimentalFingerprint, LibraryBuildConfig, Peak, SearchConfig
from database.repository import SQLiteLibraryRepository
from services.indexing import rebuild_local_library, sync_cod_library_incremental


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_rebuild_local_library_creates_entries(tmp_path) -> None:
    """Library rebuild should persist precomputed entries from CIF folder."""
    cif_folder = PROJECT_ROOT / "data" / "cif_library"
    database_path = tmp_path / "reference_library.sqlite"

    stats = rebuild_local_library(cif_folder, database_path, LibraryBuildConfig())

    assert stats.entry_count >= 2
    assert stats.peak_count > 0

    repository = SQLiteLibraryRepository(database_path)
    entries = repository.list_entries()
    assert len(entries) == stats.entry_count
    assert all(entry.peaks for entry in entries)


def test_repository_prefilter_returns_candidates(tmp_path) -> None:
    """Indexed top-peak search should return compatible entries."""
    cif_folder = PROJECT_ROOT / "data" / "cif_library"
    database_path = tmp_path / "reference_library.sqlite"
    config = LibraryBuildConfig(top_peaks_count=10, fingerprint_bin_size=0.2)
    rebuild_local_library(cif_folder, database_path, config)

    repository = SQLiteLibraryRepository(database_path)
    first_entry = repository.list_entries()[0]
    top_peaks = first_entry.top_peaks[:3]
    fingerprint = ExperimentalFingerprint(
        source_name="synthetic",
        peaks=[Peak(two_theta=peak.two_theta + 0.03, intensity=peak.intensity) for peak in top_peaks],
        top_peaks=[Peak(two_theta=peak.two_theta + 0.03, intensity=peak.intensity) for peak in top_peaks],
        two_theta_min=min(peak.two_theta for peak in top_peaks),
        two_theta_max=max(peak.two_theta for peak in top_peaks),
    )

    candidates = repository.search_candidates(
        fingerprint=fingerprint,
        config=SearchConfig(two_theta_tolerance=0.2, min_peak_matches=1, top_n_prefilter=3, max_candidates=10),
        fingerprint_bin_size=config.fingerprint_bin_size,
    )

    assert candidates
    assert any(candidate.source_id == first_entry.source_id for candidate in candidates)


def test_incremental_cod_sync_updates_only_changed_files(tmp_path) -> None:
    """Incremental sync should add, modify and delete entries based on local mirror diff."""
    source_folder = PROJECT_ROOT / "data" / "cif_library"
    sync_root = tmp_path / "cod_mirror"
    sync_root.mkdir()
    shutil.copy2(source_folder / "NaCl.cif", sync_root / "NaCl.cif")

    database_path = tmp_path / "reference_library.sqlite"
    config = LibraryBuildConfig(top_peaks_count=10, fingerprint_bin_size=0.2)

    first_report = sync_cod_library_incremental(
        sync_root=sync_root,
        database_path=database_path,
        config=config,
        method="svn",
        perform_remote_sync=False,
    )
    assert first_report.added_count == 1
    assert first_report.modified_count == 0
    assert first_report.deleted_count == 0
    assert first_report.library_stats.entry_count == 1

    shutil.copy2(source_folder / "Si.cif", sync_root / "Si.cif")
    (sync_root / "NaCl.cif").write_text((source_folder / "NaCl.cif").read_text(encoding="utf-8") + "\n", encoding="utf-8")

    second_report = sync_cod_library_incremental(
        sync_root=sync_root,
        database_path=database_path,
        config=config,
        method="svn",
        perform_remote_sync=False,
    )
    assert second_report.added_count == 1
    assert second_report.modified_count == 1
    assert second_report.deleted_count == 0
    assert second_report.library_stats.entry_count == 2

    (sync_root / "Si.cif").unlink()
    third_report = sync_cod_library_incremental(
        sync_root=sync_root,
        database_path=database_path,
        config=config,
        method="svn",
        perform_remote_sync=False,
    )
    assert third_report.added_count == 0
    assert third_report.modified_count == 0
    assert third_report.deleted_count == 1
    assert third_report.library_stats.entry_count == 1


def test_rebuild_local_library_respects_chemistry_filter(tmp_path) -> None:
    """Chemistry filters should constrain which CIFs enter library."""
    cif_folder = PROJECT_ROOT / "data" / "cif_library"
    database_path = tmp_path / "filtered_library.sqlite"

    stats = rebuild_local_library(
        cif_folder,
        database_path,
        LibraryBuildConfig(include_elements=["Na"], exclude_elements=["Si"]),
    )

    repository = SQLiteLibraryRepository(database_path)
    entries = repository.list_entries()
    assert stats.entry_count >= 1
    assert all("Na" in entry.elements for entry in entries)
    assert all("Si" not in entry.elements for entry in entries)
