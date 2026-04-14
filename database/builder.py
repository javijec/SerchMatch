"""Library-building workflow for local CIF folders."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from core.models import LibraryBuildConfig, LibraryStats
from core.simulation import build_library_entry_from_cif
from database.repository import SQLiteLibraryRepository


def discover_cif_files(folder: str | Path) -> list[Path]:
    """Return CIF files from folder recursively."""
    root = Path(folder)
    if not root.exists():
        raise FileNotFoundError(f"No existe carpeta de CIFs: {root}")
    return sorted(path for path in root.rglob("*.cif") if path.is_file())


def _extract_formula_elements(cif_path: Path) -> set[str]:
    """Best-effort lightweight element extraction from CIF text."""
    text = cif_path.read_text(encoding="utf-8", errors="ignore")
    tokens: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.lower().startswith("_chemical_formula_sum"):
            for char in "\"'":
                line = line.replace(char, " ")
            rhs = line.split(maxsplit=1)[1] if " " in line else ""
            token = ""
            for character in rhs:
                if character.isalpha():
                    if character.isupper() and token:
                        tokens.add(token)
                        token = character
                    else:
                        token += character
                else:
                    if token:
                        tokens.add(token)
                        token = ""
            if token:
                tokens.add(token)
    return {token.capitalize() for token in tokens if token and len(token) <= 2}


def _chemistry_matches(cif_path: Path, config: LibraryBuildConfig) -> bool:
    """Cheap prefilter by chemistry before full pymatgen parsing."""
    include_elements = {element.capitalize() for element in (config.include_elements or []) if element}
    exclude_elements = {element.capitalize() for element in (config.exclude_elements or []) if element}
    if not include_elements and not exclude_elements:
        return True
    tokens = _extract_formula_elements(cif_path)
    if include_elements and not include_elements.issubset(tokens):
        return False
    if exclude_elements and tokens.intersection(exclude_elements):
        return False
    return True


def _build_entry_for_folder(cif_folder: Path, cif_path: Path, config: LibraryBuildConfig):
    """Worker-safe entry builder for one CIF."""
    stat = cif_path.stat()
    return build_library_entry_from_cif(
        cif_path,
        params=config.simulation,
        top_peaks_count=config.top_peaks_count,
        source_id=cif_path.relative_to(cif_folder).as_posix(),
        extra_metadata={
            "source_path": cif_path.relative_to(cif_folder).as_posix(),
            "file_size": stat.st_size,
            "modified_time_ns": stat.st_mtime_ns,
        },
    )


def build_reference_library(
    cif_folder: str | Path,
    database_path: str | Path,
    config: LibraryBuildConfig,
) -> LibraryStats:
    """Precompute theoretical patterns and persist local library."""
    cif_files = discover_cif_files(cif_folder)
    if not cif_files:
        raise ValueError("No se encontraron archivos CIF en la carpeta seleccionada.")

    root = Path(cif_folder)
    selected_files = [cif_path for cif_path in cif_files if _chemistry_matches(cif_path, config)]
    if not selected_files:
        raise ValueError("Ningún CIF pasó filtro químico configurado.")

    if config.parallel_workers > 1:
        with ProcessPoolExecutor(max_workers=config.parallel_workers) as executor:
            entries = list(
                executor.map(
                    _build_entry_for_folder,
                    [root] * len(selected_files),
                    selected_files,
                    [config] * len(selected_files),
                )
            )
    else:
        entries = [_build_entry_for_folder(root, cif_path, config) for cif_path in selected_files]

    repository = SQLiteLibraryRepository(database_path)
    return repository.replace_library(entries, fingerprint_bin_size=config.fingerprint_bin_size)
