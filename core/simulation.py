"""Theoretical PXRD simulation from CIF files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from pymatgen.analysis.diffraction.xrd import XRDCalculator
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from core.cif_utils import load_structure_from_cif
from core.models import LibraryEntry, Peak, PeakTable, SimulationParams


def _normalize_intensities(peaks: list[Peak]) -> list[Peak]:
    """Normalize intensities to 0-100."""
    if not peaks:
        return []
    max_intensity = max(max(peak.intensity, 0.0) for peak in peaks)
    if max_intensity <= 0:
        return [Peak(two_theta=peak.two_theta, intensity=0.0, hkl=peak.hkl) for peak in peaks]
    return [
        Peak(
            two_theta=peak.two_theta,
            intensity=(max(peak.intensity, 0.0) / max_intensity) * 100.0,
            hkl=peak.hkl,
        )
        for peak in peaks
    ]


def simulate_peaks_from_structure(structure, params: SimulationParams) -> PeakTable:
    """Simulate theoretical peak list from pymatgen Structure."""
    calculator = XRDCalculator(wavelength=params.wavelength)
    pattern = calculator.get_pattern(
        structure,
        two_theta_range=(params.two_theta_min, params.two_theta_max),
        scaled=params.scaled,
    )

    peaks: list[Peak] = []
    for two_theta, intensity, hkls in zip(pattern.x, pattern.y, pattern.hkls, strict=False):
        if intensity < params.min_relative_intensity:
            continue
        hkl_value = None
        if hkls:
            first_hkl = hkls[0].get("hkl")
            if isinstance(first_hkl, tuple):
                hkl_value = tuple(int(value) for value in first_hkl)
        peaks.append(Peak(two_theta=float(two_theta), intensity=float(intensity), hkl=hkl_value))

    normalized = _normalize_intensities(peaks)
    normalized.sort(key=lambda peak: peak.two_theta)
    return PeakTable(peaks=normalized, source_name=str(getattr(structure, "formula", "structure")))


def build_library_entry_from_cif(
    cif_path: str | Path,
    params: SimulationParams,
    top_peaks_count: int,
    source_id: str | None = None,
    extra_metadata: dict | None = None,
) -> LibraryEntry:
    """Create a precomputed library entry from one CIF."""
    path = Path(cif_path)
    structure = load_structure_from_cif(path)
    peak_table = simulate_peaks_from_structure(structure, params)

    analyzer = SpacegroupAnalyzer(structure, symprec=0.1)
    formula = structure.composition.reduced_formula
    crystal_system = analyzer.get_crystal_system()
    spacegroup = analyzer.get_space_group_symbol()
    elements = sorted({element.symbol for element in structure.composition.elements})
    top_peaks = sorted(peak_table.peaks, key=lambda peak: (-peak.intensity, peak.two_theta))[:top_peaks_count]

    if peak_table.peaks:
        two_theta_min = min(peak.two_theta for peak in peak_table.peaks)
        two_theta_max = max(peak.two_theta for peak in peak_table.peaks)
    else:
        two_theta_min = params.two_theta_min
        two_theta_max = params.two_theta_max

    return LibraryEntry(
        entry_id=None,
        source_id=source_id or path.stem,
        filename=path.name,
        formula=formula,
        crystal_system=crystal_system,
        spacegroup=spacegroup,
        elements=elements,
        two_theta_min=two_theta_min,
        two_theta_max=two_theta_max,
        peaks=peak_table.peaks,
        top_peaks=top_peaks,
        metadata={
            "cif_path": str(path.resolve()),
            "peak_count": len(peak_table.peaks),
            **(extra_metadata or {}),
        },
    )


def library_entry_to_stick_pattern(entry: LibraryEntry) -> pd.DataFrame:
    """Return dataframe suitable for overlaying theoretical peaks as sticks."""
    return pd.DataFrame(
        {
            "two_theta": [peak.two_theta for peak in entry.peaks],
            "intensity": [peak.intensity for peak in entry.peaks],
        }
    )
