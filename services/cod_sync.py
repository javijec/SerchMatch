"""Incremental COD synchronization and selective reindexing."""

from __future__ import annotations

import json
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from core.models import CodSyncReport, LibraryBuildConfig
from core.simulation import build_library_entry_from_cif
from database.builder import _chemistry_matches
from database.repository import SQLiteLibraryRepository


COD_SVN_URL = "svn://www.crystallography.net/cod"
COD_SVN_CIF_URL = "svn://www.crystallography.net/cod/cif"
COD_RSYNC_URL = "rsync://www.crystallography.net/cif/"
DEFAULT_MANIFEST_NAME = ".cod_sync_manifest.json"


@dataclass(slots=True)
class FileSnapshot:
    """Lightweight snapshot of one CIF file for incremental diffing."""

    relative_path: str
    size: int
    modified_time_ns: int


def _manifest_path(sync_root: str | Path) -> Path:
    return Path(sync_root) / DEFAULT_MANIFEST_NAME


def _load_manifest(sync_root: str | Path) -> dict[str, FileSnapshot]:
    path = _manifest_path(sync_root)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        relative_path: FileSnapshot(
            relative_path=relative_path,
            size=int(snapshot["size"]),
            modified_time_ns=int(snapshot["modified_time_ns"]),
        )
        for relative_path, snapshot in payload.items()
    }


def _save_manifest(sync_root: str | Path, snapshots: dict[str, FileSnapshot]) -> None:
    path = _manifest_path(sync_root)
    payload = {
        relative_path: {
            "size": snapshot.size,
            "modified_time_ns": snapshot.modified_time_ns,
        }
        for relative_path, snapshot in snapshots.items()
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _scan_cif_snapshots(sync_root: str | Path) -> dict[str, FileSnapshot]:
    root = Path(sync_root)
    if not root.exists():
        raise FileNotFoundError(f"No existe raíz local COD: {root}")
    snapshots: dict[str, FileSnapshot] = {}
    for path in sorted(root.rglob("*.cif")):
        if not path.is_file():
            continue
        stat = path.stat()
        relative_path = path.relative_to(root).as_posix()
        snapshots[relative_path] = FileSnapshot(
            relative_path=relative_path,
            size=int(stat.st_size),
            modified_time_ns=int(stat.st_mtime_ns),
        )
    return snapshots


def _diff_snapshots(
    previous: dict[str, FileSnapshot],
    current: dict[str, FileSnapshot],
) -> tuple[list[str], list[str], list[str]]:
    """Return added, modified, deleted relative CIF paths."""
    previous_keys = set(previous)
    current_keys = set(current)
    added = sorted(current_keys - previous_keys)
    deleted = sorted(previous_keys - current_keys)
    modified = sorted(
        relative_path
        for relative_path in (current_keys & previous_keys)
        if (
            current[relative_path].size != previous[relative_path].size
            or current[relative_path].modified_time_ns != previous[relative_path].modified_time_ns
        )
    )
    return added, modified, deleted


def _run_command(command: list[str], cwd: str | Path | None = None) -> None:
    completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"Fallo comando {' '.join(command)}: {detail}")


def _perform_remote_sync(sync_root: str | Path, method: str) -> None:
    root = Path(sync_root)
    root.parent.mkdir(parents=True, exist_ok=True)
    normalized_method = method.lower()

    if normalized_method == "svn":
        if shutil.which("svn") is None:
            raise RuntimeError("`svn` no está instalado o no está en PATH.")
        if (root / ".svn").exists():
            info = subprocess.run(
                ["svn", "info", "--show-item", "url"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            checkout_url = (info.stdout or "").strip()
            if checkout_url and not checkout_url.rstrip("/").endswith("/cif"):
                raise RuntimeError(
                    "El mirror actual SVN apunta al repositorio completo y no solo a `cif/`. "
                    "Usá una carpeta nueva para recrearlo o eliminá ese checkout."
                )
            _run_command(["svn", "update"], cwd=root)
        else:
            if root.exists() and any(root.iterdir()):
                raise RuntimeError("Carpeta destino SVN no está vacía. Usá una carpeta nueva o limpiá destino.")
            _run_command(["svn", "checkout", COD_SVN_CIF_URL, str(root)])
        return

    if normalized_method == "rsync":
        if shutil.which("rsync") is None:
            raise RuntimeError("`rsync` no está instalado o no está en PATH.")
        root.mkdir(parents=True, exist_ok=True)
        destination = str(root).rstrip("\\/") + "/"
        _run_command(["rsync", "-av", "--delete", COD_RSYNC_URL, destination])
        return

    raise ValueError("Método COD no soportado. Usá `svn` o `rsync`.")


def sync_cod_incremental(
    sync_root: str | Path,
    database_path: str | Path,
    config: LibraryBuildConfig,
    method: str = "svn",
    perform_remote_sync: bool = True,
) -> CodSyncReport:
    """Sync COD mirror and reindex only added/changed/removed CIFs."""
    root = Path(sync_root)
    if perform_remote_sync:
        _perform_remote_sync(root, method)
    elif not root.exists():
        raise FileNotFoundError(f"No existe raíz local COD: {root}")

    previous_manifest = _load_manifest(root)
    current_manifest = _scan_cif_snapshots(root)
    added, modified, deleted = _diff_snapshots(previous_manifest, current_manifest)
    changed_paths = added + modified
    reindex_targets = [relative_path for relative_path in changed_paths if _chemistry_matches(root / relative_path, config)]
    filtered_out_paths = [relative_path for relative_path in changed_paths if relative_path not in set(reindex_targets)]

    repository = SQLiteLibraryRepository(database_path)
    updated_entries = _build_entries_parallel(root, reindex_targets, config, method.lower())

    repository.upsert_entries(updated_entries, config.fingerprint_bin_size)
    repository.delete_entries_by_source_ids(deleted + filtered_out_paths)
    library_stats = repository.get_stats()
    _save_manifest(root, current_manifest)

    return CodSyncReport(
        sync_root=root,
        method=method.lower(),
        remote_sync_performed=perform_remote_sync,
        added_count=len(added),
        modified_count=len(modified),
        deleted_count=len(deleted),
        filtered_out_count=len(filtered_out_paths),
        reindexed_count=len(reindex_targets),
        total_cif_count=len(current_manifest),
        library_stats=library_stats,
    )


def _build_entry_for_sync(
    root: Path,
    relative_path: str,
    config: LibraryBuildConfig,
    method: str,
):
    """Worker-safe builder for one COD CIF."""
    absolute_path = root / relative_path
    snapshot = absolute_path.stat()
    return build_library_entry_from_cif(
        absolute_path,
        params=config.simulation,
        top_peaks_count=config.top_peaks_count,
        source_id=relative_path,
        extra_metadata={
            "source_path": relative_path,
            "file_size": snapshot.st_size,
            "modified_time_ns": snapshot.st_mtime_ns,
            "cod_sync_method": method,
        },
    )


def _build_entries_parallel(
    root: Path,
    relative_paths: list[str],
    config: LibraryBuildConfig,
    method: str,
):
    """Build entries sequentially or in parallel depending on config."""
    if not relative_paths:
        return []
    if config.parallel_workers > 1:
        with ProcessPoolExecutor(max_workers=config.parallel_workers) as executor:
            return list(
                executor.map(
                    _build_entry_for_sync,
                    [root] * len(relative_paths),
                    relative_paths,
                    [config] * len(relative_paths),
                    [method] * len(relative_paths),
                )
            )
    return [_build_entry_for_sync(root, relative_path, config, method) for relative_path in relative_paths]
