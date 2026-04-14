"""Shared domain models for PXRD/XRD library-based search & match."""

from __future__ import annotations

from abc import ABC, abstractmethod
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
        """Return pattern as a tidy dataframe."""
        return pd.DataFrame(
            {
                "two_theta": self.two_theta.to_numpy(dtype=float),
                "intensity": self.intensity.to_numpy(dtype=float),
            }
        )


@dataclass(slots=True)
class Peak:
    """Single diffraction peak."""

    two_theta: float
    intensity: float
    prominence: float | None = None
    width: float | None = None
    hkl: tuple[int, int, int] | None = None


@dataclass(slots=True)
class PeakTable:
    """Collection of peaks with helpers."""

    peaks: list[Peak]
    source_name: str

    def to_dataframe(self) -> pd.DataFrame:
        """Return peaks as dataframe."""
        return pd.DataFrame(
            [
                {
                    "two_theta": peak.two_theta,
                    "intensity": peak.intensity,
                    "prominence": peak.prominence,
                    "width": peak.width,
                    "hkl": None if peak.hkl is None else str(peak.hkl),
                }
                for peak in self.peaks
            ]
        )

    def top_peaks(self, limit: int) -> list[Peak]:
        """Return top peaks sorted by intensity desc, then 2theta."""
        return sorted(self.peaks, key=lambda peak: (-peak.intensity, peak.two_theta))[:limit]


@dataclass(slots=True)
class PreprocessingParams:
    """Lightweight preprocessing controls."""

    normalize: bool = True
    smoothing_enabled: bool = False
    smoothing_window: int = 11
    smoothing_polyorder: int = 3
    background_correction_enabled: bool = False
    background_window: int = 51
    clip_negative: bool = True


@dataclass(slots=True)
class PeakDetectionParams:
    """Experimental peak finding parameters."""

    min_height: float = 5.0
    prominence: float = 3.0
    min_distance_points: int = 5
    min_width: float | None = None


@dataclass(slots=True)
class SimulationParams:
    """Theoretical pattern simulation parameters."""

    wavelength: str = "CuKa"
    two_theta_min: float = 5.0
    two_theta_max: float = 90.0
    scaled: bool = True
    min_relative_intensity: float = 0.5


@dataclass(slots=True)
class LibraryBuildConfig:
    """Controls local reference-library construction."""

    top_peaks_count: int = 12
    fingerprint_bin_size: float = 0.2
    parallel_workers: int = 1
    include_elements: list[str] | None = None
    exclude_elements: list[str] | None = None
    simulation: SimulationParams = field(default_factory=SimulationParams)


@dataclass(slots=True)
class MatchWeights:
    """Weights for interpretable peak-based scoring."""

    position: float = 0.45
    intensity: float = 0.25
    matched_fraction: float = 0.15
    missing_penalty: float = 0.10
    extra_penalty: float = 0.05


@dataclass(slots=True)
class SearchConfig:
    """Search and match runtime parameters."""

    two_theta_tolerance: float = 0.2
    min_peak_matches: int = 2
    top_n_prefilter: int = 8
    max_candidates: int = 50
    multifase_max_results: int = 5
    enable_multiphase: bool = True
    element_filter: list[str] | None = None
    weights: MatchWeights = field(default_factory=MatchWeights)


@dataclass(slots=True)
class LibraryEntry:
    """Precomputed theoretical reference pattern stored in local library."""

    entry_id: int | None
    source_id: str
    filename: str
    formula: str | None
    crystal_system: str | None
    spacegroup: str | None
    elements: list[str]
    two_theta_min: float
    two_theta_max: float
    peaks: list[Peak]
    top_peaks: list[Peak]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        """Return lightweight serializable metadata."""
        return {
            "entry_id": self.entry_id,
            "source_id": self.source_id,
            "filename": self.filename,
            "formula": self.formula,
            "crystal_system": self.crystal_system,
            "spacegroup": self.spacegroup,
            "elements": self.elements,
            "two_theta_min": self.two_theta_min,
            "two_theta_max": self.two_theta_max,
            "peak_count": len(self.peaks),
        }


@dataclass(slots=True)
class ExperimentalFingerprint:
    """Compact representation of experimental pattern peaks."""

    source_name: str
    peaks: list[Peak]
    top_peaks: list[Peak]
    two_theta_min: float
    two_theta_max: float

    def to_dataframe(self) -> pd.DataFrame:
        """Return fingerprint peaks as dataframe."""
        return PeakTable(peaks=self.peaks, source_name=self.source_name).to_dataframe()


@dataclass(slots=True)
class MatchedPeak:
    """Matched experimental/theoretical peak pair."""

    experimental_two_theta: float
    experimental_intensity: float
    theoretical_two_theta: float
    theoretical_intensity: float
    delta_two_theta: float
    position_similarity: float
    intensity_similarity: float


@dataclass(slots=True)
class ScoreBreakdown:
    """Detailed, interpretable score components."""

    position_score: float
    intensity_score: float
    matched_fraction: float
    missing_penalty: float
    extra_penalty: float
    matched_peak_count: int
    theoretical_peak_count: int
    experimental_peak_count: int
    explained_experimental_count: int


@dataclass(slots=True)
class CandidateMatch:
    """Detailed result for one reference entry."""

    entry: LibraryEntry
    score: float
    breakdown: ScoreBreakdown
    matched_peaks: list[MatchedPeak]
    explained_peak_indices: list[int]
    missing_theoretical_peaks: list[Peak]
    extra_experimental_peaks: list[Peak]

    def to_row(self) -> dict[str, Any]:
        """Return flat row for ranking table."""
        return {
            "entry_id": self.entry.entry_id,
            "source_id": self.entry.source_id,
            "filename": self.entry.filename,
            "formula": self.entry.formula,
            "crystal_system": self.entry.crystal_system,
            "score": round(self.score, 3),
            "position_score": round(self.breakdown.position_score * 100.0, 2),
            "intensity_score": round(self.breakdown.intensity_score * 100.0, 2),
            "matched_fraction": round(self.breakdown.matched_fraction * 100.0, 2),
            "missing_penalty": round(self.breakdown.missing_penalty * 100.0, 2),
            "extra_penalty": round(self.breakdown.extra_penalty * 100.0, 2),
            "matched_peak_count": self.breakdown.matched_peak_count,
        }


@dataclass(slots=True)
class PhaseCombination:
    """Simple 2-phase proposal from iterative residual search."""

    phases: list[CandidateMatch]
    combined_score: float
    explained_fraction: float

    def label(self) -> str:
        """Return human-readable combination label."""
        return " + ".join(match.entry.filename for match in self.phases)


@dataclass(slots=True)
class LibraryStats:
    """Local reference-library summary."""

    database_path: Path
    entry_count: int
    peak_count: int
    last_updated: str | None = None


@dataclass(slots=True)
class CodSyncReport:
    """Summary of one incremental COD synchronization run."""

    sync_root: Path
    method: str
    remote_sync_performed: bool
    added_count: int
    modified_count: int
    deleted_count: int
    filtered_out_count: int
    reindexed_count: int
    total_cif_count: int
    library_stats: LibraryStats


@dataclass(slots=True)
class SearchArtifacts:
    """Outputs from one search & match run."""

    experimental_raw: DiffractionPattern
    experimental_processed: DiffractionPattern
    experimental_fingerprint: ExperimentalFingerprint
    candidate_ranking: list[CandidateMatch]
    multiphase_candidates: list[PhaseCombination]
    library_stats: LibraryStats
    prefilter_candidate_count: int


class BaseMatcher(ABC):
    """Abstract matcher for future peak- and profile-based engines."""

    @abstractmethod
    def match(
        self,
        fingerprint: ExperimentalFingerprint,
        candidates: list[LibraryEntry],
        config: SearchConfig,
    ) -> list[CandidateMatch]:
        """Return ranked matches."""


class ProfileMatcher(BaseMatcher):
    """Reserved interface for future full-profile fitting engines."""

    def match(
        self,
        fingerprint: ExperimentalFingerprint,
        candidates: list[LibraryEntry],
        config: SearchConfig,
    ) -> list[CandidateMatch]:
        """Profile matching intentionally not implemented yet."""
        raise NotImplementedError(
            "ProfileMatcher reserved for future full-profile comparison and fitting workflows."
        )
