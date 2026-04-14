"""Preprocessing utilities for diffraction patterns."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d, minimum_filter1d
from scipy.signal import savgol_filter

from core.models import DiffractionPattern, PreprocessingParams


def normalize_intensity(intensity: pd.Series) -> pd.Series:
    """Scale intensity to [0, 100]."""
    values = intensity.astype(float).to_numpy()
    min_val = float(np.min(values))
    shifted = values - min_val
    max_val = float(np.max(shifted))
    if max_val <= 0:
        return pd.Series(np.zeros_like(values), index=intensity.index, dtype=float)
    return pd.Series((shifted / max_val) * 100.0, index=intensity.index, dtype=float)


def estimate_background(intensity: pd.Series, window: int) -> pd.Series:
    """Estimate a simple rolling background using minimum + Gaussian smoothing."""
    adjusted_window = max(3, window)
    if adjusted_window % 2 == 0:
        adjusted_window += 1
    minima = minimum_filter1d(intensity.astype(float).to_numpy(), size=adjusted_window, mode="nearest")
    sigma = max(adjusted_window / 6.0, 1.0)
    baseline = gaussian_filter1d(minima, sigma=sigma, mode="nearest")
    return pd.Series(baseline, index=intensity.index, dtype=float)


def preprocess_pattern(pattern: DiffractionPattern, params: PreprocessingParams) -> DiffractionPattern:
    """Apply optional background correction, smoothing, and normalization."""
    intensity = pattern.intensity.astype(float).copy()
    metadata = dict(pattern.metadata)

    if params.background_correction_enabled:
        background = estimate_background(intensity, params.background_window)
        intensity = intensity - background
        metadata["background_estimated"] = True

    if params.clip_negative:
        intensity = intensity.clip(lower=0.0)

    if params.smoothing_enabled and len(intensity) >= 7:
        window = min(params.smoothing_window, len(intensity) if len(intensity) % 2 == 1 else len(intensity) - 1)
        window = max(window, params.smoothing_polyorder + 2)
        if window % 2 == 0:
            window += 1
        if window < len(intensity):
            intensity = pd.Series(
                savgol_filter(intensity.to_numpy(), window_length=window, polyorder=params.smoothing_polyorder),
                index=intensity.index,
                dtype=float,
            )
            metadata["smoothed"] = True

    if params.normalize:
        intensity = normalize_intensity(intensity)
        metadata["normalized"] = True

    return DiffractionPattern(
        two_theta=pattern.two_theta.copy(),
        intensity=intensity,
        source_name=pattern.source_name,
        metadata=metadata,
    )
