"""Shared domain models for PXRD/XRD workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(slots=True)
class DiffractionPattern:
    """Represents a 1D diffraction pattern."""

    two_theta: pd.Series
    intensity: pd.Series
    source_name: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        """Return the pattern as a tidy DataFrame."""
        return pd.DataFrame(
            {
                "two_theta": self.two_theta.to_numpy(),
                "intensity": self.intensity.to_numpy(),
            }
        )


@dataclass(slots=True)
class Peak:
    """Single detected or simulated diffraction peak."""

    two_theta: float
    intensity: float
    prominence: float | None = None
    width: float | None = None
    hkl: tuple[int, int, int] | None = None


@dataclass(slots=True)
class PeakTable:
    """Collection of peaks with convenience conversion helpers."""

    peaks: list[Peak]
    source_name: str

    def to_dataframe(self) -> pd.DataFrame:
        """Return peaks as DataFrame."""
        rows = []
        for peak in self.peaks:
            rows.append(
                {
                    "two_theta": peak.two_theta,
                    "intensity": peak.intensity,
                    "prominence": peak.prominence,
                    "width": peak.width,
                    "hkl": None if peak.hkl is None else str(peak.hkl),
                }
            )
        return pd.DataFrame(rows)


@dataclass(slots=True)
class PreprocessingParams:
    """Controls light-weight signal preprocessing."""

    normalize: bool = True
    smoothing_enabled: bool = False
    smoothing_window: int = 11
    smoothing_polyorder: int = 3
    background_correction_enabled: bool = False
    background_window: int = 51
    clip_negative: bool = True


@dataclass(slots=True)
class PeakDetectionParams:
    """Parameters for experimental peak finding."""

    min_height: float = 0.05
    prominence: float = 0.03
    min_distance_points: int = 5
    min_width: float | None = None


@dataclass(slots=True)
class SimulationParams:
    """Parameters for theoretical pattern simulation."""

    wavelength: str = "CuKa"
    two_theta_min: float = 5.0
    two_theta_max: float = 90.0
    scaled: bool = True


@dataclass(slots=True)
class MatchingParams:
    """Parameters for search & match scoring."""

    two_theta_tolerance: float = 0.2
    intensity_weight: float = 0.35
    position_weight: float = 0.45
    missing_peak_weight: float = 0.20
    min_theoretical_relative_intensity: float = 5.0
    top_n: int = 10


@dataclass(slots=True)
class SimulatedPattern:
    """Theoretical pattern simulated from a CIF."""

    pattern: DiffractionPattern
    peaks: PeakTable
    cif_path: Path
    phase_name: str


@dataclass(slots=True)
class MatchBreakdown:
    """Interpretable score breakdown."""

    matched_peak_fraction: float
    position_score: float
    intensity_score: float
    missing_penalty: float
    matched_peak_count: int
    important_theoretical_peak_count: int


@dataclass(slots=True)
class MatchResult:
    """Comparison between one experimental pattern and one candidate phase."""

    phase_name: str
    cif_path: Path
    score: float
    breakdown: MatchBreakdown
    matched_peaks: list[dict[str, float]]
    simulated_pattern: SimulatedPattern


@dataclass(slots=True)
class WorkflowArtifacts:
    """Reusable outputs from an analysis run."""

    experimental_raw: DiffractionPattern
    experimental_processed: DiffractionPattern
    detected_peaks: PeakTable
    candidate_results: list[MatchResult]
