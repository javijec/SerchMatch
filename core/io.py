"""Input/output helpers for diffraction data and result exports."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import BinaryIO, TextIO

import json

import numpy as np
import pandas as pd

from core.models import DiffractionPattern


SUPPORTED_PATTERN_EXTENSIONS = {".xy", ".txt", ".csv"}


def _read_text_from_filelike(file_obj: BinaryIO | TextIO) -> str:
    """Return decoded text from a path-like upload or file-like object."""
    content = file_obj.read()
    if isinstance(content, bytes):
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("No se pudo decodificar el archivo de difractograma.")
    return content


def _prepare_dataframe(text: str, suffix: str) -> pd.DataFrame:
    """Read a text table while tolerating simple metadata headers."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", ";", "!", "//")):
            continue
        lines.append(stripped)
    if not lines:
        raise ValueError("El archivo no contiene datos numéricos utilizables.")

    clean_text = "\n".join(lines)
    delimiter = "," if suffix == ".csv" else None
    dataframe = pd.read_csv(
        StringIO(clean_text),
        sep=delimiter,
        engine="python",
        comment="#",
    )

    if dataframe.shape[1] == 1:
        dataframe = pd.read_csv(
            StringIO(clean_text),
            sep=r"[\s,;\t]+",
            engine="python",
            header=None,
        )

    dataframe = dataframe.dropna(axis=1, how="all").dropna(axis=0, how="all")
    if dataframe.empty:
        raise ValueError("No se pudieron interpretar columnas numéricas en el archivo.")
    return dataframe


def detect_pattern_columns(dataframe: pd.DataFrame) -> tuple[str | int, str | int]:
    """Infer 2theta and intensity columns from names or numeric behavior."""
    normalized_columns = {col: str(col).strip().lower() for col in dataframe.columns}
    two_theta_aliases = ("2theta", "two_theta", "twotheta", "theta", "2-theta")
    intensity_aliases = ("intensity", "counts", "i", "y", "signal")

    two_theta_col = None
    intensity_col = None

    for col, normalized in normalized_columns.items():
        if two_theta_col is None and any(alias in normalized for alias in two_theta_aliases):
            two_theta_col = col
        if intensity_col is None and any(alias in normalized for alias in intensity_aliases):
            intensity_col = col

    numeric_df = dataframe.apply(pd.to_numeric, errors="coerce")
    usable_columns = [
        col for col in numeric_df.columns if numeric_df[col].notna().sum() >= max(5, len(numeric_df) // 3)
    ]
    if len(usable_columns) < 2:
        raise ValueError("Se necesitan al menos dos columnas numéricas para 2theta e intensidad.")

    if two_theta_col is None:
        monotonic_scores: list[tuple[str | int, float]] = []
        for col in usable_columns:
            series = numeric_df[col].dropna()
            diffs = np.diff(series.to_numpy())
            if len(diffs) == 0:
                continue
            increasing_fraction = float(np.mean(diffs > 0))
            monotonic_scores.append((col, increasing_fraction))
        if not monotonic_scores:
            raise ValueError("No se pudo identificar una columna de 2theta.")
        two_theta_col = max(monotonic_scores, key=lambda item: item[1])[0]

    if intensity_col is None:
        remaining = [col for col in usable_columns if col != two_theta_col]
        if not remaining:
            raise ValueError("No se pudo identificar una columna de intensidad.")
        intensity_col = max(
            remaining,
            key=lambda col: float(numeric_df[col].fillna(0.0).max() - numeric_df[col].fillna(0.0).min()),
        )

    return two_theta_col, intensity_col


def load_diffraction_pattern(source: str | Path | BinaryIO | TextIO, source_name: str | None = None) -> DiffractionPattern:
    """Load an experimental diffraction pattern from a supported flat text format."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_PATTERN_EXTENSIONS:
            raise ValueError(f"Formato no soportado: {suffix}. Use .xy, .txt o .csv.")
        with path.open("rb") as handle:
            text = _read_text_from_filelike(handle)
        resolved_source_name = source_name or path.name
    else:
        resolved_source_name = source_name or getattr(source, "name", "uploaded_pattern")
        suffix = Path(resolved_source_name).suffix.lower()
        text = _read_text_from_filelike(source)

    dataframe = _prepare_dataframe(text, suffix)
    two_theta_col, intensity_col = detect_pattern_columns(dataframe)

    numeric_df = dataframe[[two_theta_col, intensity_col]].apply(pd.to_numeric, errors="coerce").dropna()
    numeric_df.columns = ["two_theta", "intensity"]
    numeric_df = numeric_df.sort_values("two_theta").drop_duplicates(subset=["two_theta"])

    if numeric_df.empty:
        raise ValueError("No hay filas numéricas válidas después de limpiar el archivo.")

    return DiffractionPattern(
        two_theta=numeric_df["two_theta"].reset_index(drop=True),
        intensity=numeric_df["intensity"].reset_index(drop=True),
        source_name=resolved_source_name,
        metadata={"two_theta_column": str(two_theta_col), "intensity_column": str(intensity_col)},
    )


def export_results_to_csv(results: list[dict], destination: str | Path) -> None:
    """Save ranking results to CSV."""
    pd.DataFrame(results).to_csv(destination, index=False)


def export_results_to_json(results: list[dict], destination: str | Path) -> None:
    """Save ranking results to JSON."""
    Path(destination).write_text(json.dumps(results, indent=2), encoding="utf-8")
