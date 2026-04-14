"""Theoretical diffraction pattern simulation from CIF files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.cif_utils import infer_phase_name, load_structure_from_cif
from core.models import DiffractionPattern, Peak, PeakTable, SimulatedPattern, SimulationParams


def simulate_pattern_from_cif(cif_path: str | Path, params: SimulationParams) -> SimulatedPattern:
    """Generate a theoretical powder XRD pattern with pymatgen."""
    from pymatgen.analysis.diffraction.xrd import XRDCalculator

    path = Path(cif_path)
    structure = load_structure_from_cif(path)
    calculator = XRDCalculator(wavelength=params.wavelength)
    pattern = calculator.get_pattern(
        structure,
        scaled=params.scaled,
        two_theta_range=(params.two_theta_min, params.two_theta_max),
    )

    two_theta = pd.Series(pattern.x, dtype=float)
    intensity = pd.Series(pattern.y, dtype=float)
    phase_name = infer_phase_name(path, structure=structure)

    peak_entries: list[Peak] = []
    for idx, angle in enumerate(pattern.x):
        hkls = pattern.hkls[idx]
        hkl_tuple = None
        if hkls:
            hkl_data = hkls[0].get("hkl")
            if hkl_data is not None:
                hkl_tuple = tuple(int(value) for value in hkl_data)
        peak_entries.append(
            Peak(
                two_theta=float(angle),
                intensity=float(pattern.y[idx]),
                hkl=hkl_tuple,
            )
        )

    return SimulatedPattern(
        pattern=DiffractionPattern(two_theta=two_theta, intensity=intensity, source_name=phase_name),
        peaks=PeakTable(peaks=peak_entries, source_name=phase_name),
        cif_path=path,
        phase_name=phase_name,
    )
