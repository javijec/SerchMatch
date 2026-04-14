"""Tests for diffraction data loading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.io import detect_pattern_columns, load_diffraction_pattern


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_diffraction_pattern_from_example_file() -> None:
    """Example pattern should load as sorted two-column dataset."""
    pattern_path = PROJECT_ROOT / "data" / "examples" / "sample_experimental.xy"
    pattern = load_diffraction_pattern(pattern_path)

    assert pattern.source_name == "sample_experimental.xy"
    assert len(pattern.two_theta) == len(pattern.intensity)
    assert pattern.two_theta.iloc[0] < pattern.two_theta.iloc[-1]
    assert pattern.intensity.max() > 0.0


def test_detect_pattern_columns_from_headers() -> None:
    """Known column names should be recognized directly."""
    df = pd.DataFrame({"2theta": [10.0, 20.0, 30.0], "counts": [100, 150, 90]})
    two_theta_col, intensity_col = detect_pattern_columns(df)
    assert two_theta_col == "2theta"
    assert intensity_col == "counts"
