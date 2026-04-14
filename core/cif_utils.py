"""Helpers to load and validate CIF files."""

from __future__ import annotations

from pathlib import Path


def load_structure_from_cif(cif_path: str | Path):
    """Load a pymatgen Structure from a CIF path."""
    from pymatgen.core import Structure

    path = Path(cif_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo CIF: {path}")
    try:
        return Structure.from_file(path)
    except Exception as exc:  # pragma: no cover - depends on pymatgen parser internals
        raise ValueError(f"CIF inválido o no interpretable: {path.name}") from exc


def infer_phase_name(cif_path: str | Path, structure=None) -> str:
    """Infer a display name for a phase."""
    path = Path(cif_path)
    if structure is not None:
        formula = getattr(structure.composition, "reduced_formula", None)
        if formula:
            return f"{path.stem} ({formula})"
    return path.stem
