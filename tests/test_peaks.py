"""Tests for peak detection."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.models import DiffractionPattern, PeakDetectionParams
from core.peaks import detect_peaks_in_pattern


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
