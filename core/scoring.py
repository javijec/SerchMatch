"""Interpretable search & match scoring for experimental vs theoretical peaks."""

from __future__ import annotations

from core.models import MatchBreakdown, MatchingParams, Peak, PeakTable


def _normalize_peak_intensities(peaks: list[Peak]) -> list[Peak]:
    """Return a copy of peaks with relative intensities scaled to 100."""
    if not peaks:
        return []
    max_intensity = max(max(peak.intensity, 0.0) for peak in peaks)
    if max_intensity <= 0:
        return [
            Peak(
                two_theta=peak.two_theta,
                intensity=0.0,
                prominence=peak.prominence,
                width=peak.width,
                hkl=peak.hkl,
            )
            for peak in peaks
        ]
    normalized = []
    for peak in peaks:
        normalized.append(
            Peak(
                two_theta=peak.two_theta,
                intensity=(max(peak.intensity, 0.0) / max_intensity) * 100.0,
                prominence=peak.prominence,
                width=peak.width,
                hkl=peak.hkl,
            )
        )
    return normalized


def score_peak_match(
    experimental: PeakTable,
    theoretical: PeakTable,
    params: MatchingParams,
) -> tuple[float, MatchBreakdown, list[dict[str, float]]]:
    """Score one theoretical phase against the experimental peak list."""
    experimental_peaks = _normalize_peak_intensities(experimental.peaks)
    theoretical_peaks = _normalize_peak_intensities(theoretical.peaks)

    if not experimental_peaks or not theoretical_peaks:
        breakdown = MatchBreakdown(
            matched_peak_fraction=0.0,
            position_score=0.0,
            intensity_score=0.0,
            missing_penalty=1.0,
            matched_peak_count=0,
            important_theoretical_peak_count=0,
        )
        return 0.0, breakdown, []

    candidate_peaks = [
        peak for peak in theoretical_peaks if peak.intensity >= params.min_theoretical_relative_intensity
    ]
    if not candidate_peaks:
        candidate_peaks = theoretical_peaks

    matches: list[dict[str, float]] = []
    used_experimental_indices: set[int] = set()

    for theoretical_peak in candidate_peaks:
        best_index = None
        best_distance = None
        for exp_index, experimental_peak in enumerate(experimental_peaks):
            if exp_index in used_experimental_indices:
                continue
            delta = abs(experimental_peak.two_theta - theoretical_peak.two_theta)
            if delta <= params.two_theta_tolerance and (best_distance is None or delta < best_distance):
                best_distance = delta
                best_index = exp_index

        if best_index is None:
            continue

        experimental_peak = experimental_peaks[best_index]
        used_experimental_indices.add(best_index)
        intensity_similarity = 1.0 - min(
            abs(experimental_peak.intensity - theoretical_peak.intensity) / 100.0,
            1.0,
        )
        position_similarity = 1.0 - min(best_distance / params.two_theta_tolerance, 1.0)
        matches.append(
            {
                "experimental_two_theta": experimental_peak.two_theta,
                "theoretical_two_theta": theoretical_peak.two_theta,
                "delta_two_theta": float(best_distance),
                "experimental_intensity": experimental_peak.intensity,
                "theoretical_intensity": theoretical_peak.intensity,
                "position_similarity": position_similarity,
                "intensity_similarity": intensity_similarity,
            }
        )

    important_count = len(candidate_peaks)
    matched_count = len(matches)
    matched_fraction = matched_count / important_count if important_count else 0.0

    position_score = sum(match["position_similarity"] for match in matches) / matched_count if matched_count else 0.0
    intensity_score = sum(match["intensity_similarity"] for match in matches) / matched_count if matched_count else 0.0
    missing_penalty = 1.0 - matched_fraction

    weight_sum = params.position_weight + params.intensity_weight + params.missing_peak_weight
    if weight_sum <= 0:
        weight_sum = 1.0
    raw_score = (
        params.position_weight * position_score
        + params.intensity_weight * intensity_score
        + params.missing_peak_weight * (1.0 - missing_penalty)
    ) / weight_sum
    score = max(0.0, min(raw_score * 100.0, 100.0))

    breakdown = MatchBreakdown(
        matched_peak_fraction=matched_fraction,
        position_score=position_score,
        intensity_score=intensity_score,
        missing_penalty=missing_penalty,
        matched_peak_count=matched_count,
        important_theoretical_peak_count=important_count,
    )
    return score, breakdown, matches
