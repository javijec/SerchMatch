"""Tests for peak detection and fingerprint extraction."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.models import DiffractionPattern, PeakDetectionParams, PreprocessingParams
from core.peaks import detect_peaks_in_pattern
from services.search import build_experimental_fingerprint


def test_detect_peaks_in_synthetic_pattern() -> None:
    """Peak finder should recover obvious maxima."""
    x = np.linspace(10, 40, 301)
    y = (
        0.1
        + 1.0 * np.exp(-0.5 * ((x - 18.0) / 0.35) ** 2)
        + 0.7 * np.exp(-0.5 * ((x - 31.5) / 0.45) ** 2)
    )
    pattern = DiffractionPattern(
        two_theta=pd.Series(x),
        intensity=pd.Series(y * 100.0),
        source_name="synthetic",
    )
    peaks = detect_peaks_in_pattern(
        pattern,
        PeakDetectionParams(min_height=20.0, prominence=10.0, min_distance_points=20),
    )

    assert len(peaks.peaks) == 2
    assert abs(peaks.peaks[0].two_theta - 18.0) < 0.2
    assert abs(peaks.peaks[1].two_theta - 31.5) < 0.2


def test_build_experimental_fingerprint_normalizes_top_peaks() -> None:
    """Fingerprint should keep normalized intensities and top peaks."""
    x = np.linspace(10, 50, 401)
    y = (
        5.0
        + 150.0 * np.exp(-0.5 * ((x - 17.5) / 0.3) ** 2)
        + 80.0 * np.exp(-0.5 * ((x - 32.0) / 0.4) ** 2)
        + 40.0 * np.exp(-0.5 * ((x - 41.0) / 0.45) ** 2)
    )
    buffer = "\n".join(f"{theta:.4f},{intensity:.4f}" for theta, intensity in zip(x, y, strict=False)).encode("utf-8")

    from io import BytesIO

    _, _, fingerprint = build_experimental_fingerprint(
        pattern_source=BytesIO(buffer),
        source_name="synthetic.csv",
        preprocessing_params=PreprocessingParams(normalize=True),
        peak_params=PeakDetectionParams(min_height=10.0, prominence=5.0, min_distance_points=20),
        top_n_prefilter=2,
    )

    assert len(fingerprint.peaks) >= 3
    assert len(fingerprint.top_peaks) == 2
    assert abs(max(peak.intensity for peak in fingerprint.peaks) - 100.0) < 1e-6
