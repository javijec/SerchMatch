"""Tests for indexed peak matching."""

from __future__ import annotations

from core.matching import PeakMatcher
from core.models import ExperimentalFingerprint, LibraryEntry, Peak, SearchConfig


def _entry(name: str, positions: list[float], intensities: list[float]) -> LibraryEntry:
    peaks = [Peak(two_theta=tt, intensity=intensity) for tt, intensity in zip(positions, intensities, strict=False)]
    return LibraryEntry(
        entry_id=None,
        source_id=name,
        filename=f"{name}.cif",
        formula=name,
        crystal_system="cubic",
        spacegroup="Fm-3m",
        elements=["Na", "Cl"],
        two_theta_min=min(positions),
        two_theta_max=max(positions),
        peaks=peaks,
        top_peaks=sorted(peaks, key=lambda peak: peak.intensity, reverse=True)[:3],
        metadata={},
    )


def test_peak_matcher_ranks_best_candidate_first() -> None:
    """Closest theoretical peak set should rank first."""
    fingerprint = ExperimentalFingerprint(
        source_name="exp",
        peaks=[
            Peak(two_theta=27.45, intensity=100.0),
            Peak(two_theta=45.50, intensity=82.0),
            Peak(two_theta=56.52, intensity=25.0),
        ],
        top_peaks=[
            Peak(two_theta=27.45, intensity=100.0),
            Peak(two_theta=45.50, intensity=82.0),
        ],
        two_theta_min=27.45,
        two_theta_max=56.52,
    )

    good = _entry("good", [27.40, 45.45, 56.50], [100.0, 80.0, 22.0])
    poor = _entry("poor", [22.10, 37.00, 62.20], [100.0, 85.0, 35.0])

    matcher = PeakMatcher()
    results = matcher.match(fingerprint, [poor, good], SearchConfig(two_theta_tolerance=0.2))

    assert results[0].entry.source_id == "good"
    assert results[0].score > results[1].score
    assert results[0].breakdown.matched_peak_count == 3
