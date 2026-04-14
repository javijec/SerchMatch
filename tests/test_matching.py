"""Tests for ranking and scoring candidate phases."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.matching import rank_candidate_patterns
from core.models import DiffractionPattern, MatchingParams, Peak, PeakTable, SimulatedPattern


def _simulated_pattern(name: str, positions: list[float], intensities: list[float]) -> SimulatedPattern:
    peak_table = PeakTable(
        peaks=[Peak(two_theta=tt, intensity=intensity) for tt, intensity in zip(positions, intensities)],
        source_name=name,
    )
    pattern = DiffractionPattern(
        two_theta=pd.Series(positions),
        intensity=pd.Series(intensities),
        source_name=name,
    )
    return SimulatedPattern(
        pattern=pattern,
        peaks=peak_table,
        cif_path=Path(f"{name}.cif"),
        phase_name=name,
    )


def test_matching_ranks_best_candidate_first() -> None:
    """The closest candidate should win the ranking."""
    experimental = PeakTable(
        peaks=[
            Peak(two_theta=27.45, intensity=100.0),
            Peak(two_theta=45.50, intensity=82.0),
            Peak(two_theta=56.52, intensity=25.0),
        ],
        source_name="exp",
    )

    good = _simulated_pattern("good", [27.40, 45.45, 56.50], [100.0, 80.0, 22.0])
    poor = _simulated_pattern("poor", [22.10, 37.00, 62.20], [100.0, 85.0, 35.0])

    results = rank_candidate_patterns(
        experimental,
        [poor, good],
        MatchingParams(two_theta_tolerance=0.2, min_theoretical_relative_intensity=1.0),
    )

    assert results[0].phase_name == "good"
    assert results[0].score > results[1].score
    assert results[0].breakdown.matched_peak_count == 3
