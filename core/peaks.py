"""Peak detection utilities."""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks, peak_widths

from core.models import DiffractionPattern, Peak, PeakDetectionParams, PeakTable


def detect_peaks_in_pattern(pattern: DiffractionPattern, params: PeakDetectionParams) -> PeakTable:
    """Detect peaks using scipy.signal.find_peaks."""
    intensity = pattern.intensity.to_numpy(dtype=float)
    kwargs: dict[str, float | int] = {
        "height": params.min_height,
        "prominence": params.prominence,
        "distance": params.min_distance_points,
    }
    if params.min_width is not None:
        kwargs["width"] = params.min_width

    peak_indices, properties = find_peaks(intensity, **kwargs)

    widths = None
    if len(peak_indices) > 0:
        widths = peak_widths(intensity, peak_indices, rel_height=0.5)[0]

    peaks: list[Peak] = []
    for idx, peak_index in enumerate(peak_indices):
        peaks.append(
            Peak(
                two_theta=float(pattern.two_theta.iloc[peak_index]),
                intensity=float(intensity[peak_index]),
                prominence=float(properties["prominences"][idx]) if "prominences" in properties else None,
                width=float(widths[idx]) if widths is not None else None,
            )
        )

    peaks.sort(key=lambda peak: peak.two_theta)
    return PeakTable(peaks=peaks, source_name=pattern.source_name)


def peak_table_to_overlay_dataframe(peak_table: PeakTable) -> tuple[np.ndarray, np.ndarray]:
    """Create stick-pattern arrays for peak overlay charts."""
    x_values = np.array([peak.two_theta for peak in peak_table.peaks], dtype=float)
    y_values = np.array([peak.intensity for peak in peak_table.peaks], dtype=float)
    return x_values, y_values
