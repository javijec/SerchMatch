"""Search & match workflows for indexed PXRD libraries."""

from __future__ import annotations

from pathlib import Path

from core.io import load_diffraction_pattern
from core.matching import PeakMatcher
from core.models import (
    ExperimentalFingerprint,
    LibraryBuildConfig,
    Peak,
    PeakDetectionParams,
    PreprocessingParams,
    SearchArtifacts,
    SearchConfig,
)
from core.peaks import detect_peaks_in_pattern
from core.preprocessing import preprocess_pattern
from database.repository import SQLiteLibraryRepository


def build_experimental_fingerprint(
    pattern_source,
    source_name: str | None,
    preprocessing_params: PreprocessingParams,
    peak_params: PeakDetectionParams,
    top_n_prefilter: int,
):
    """Load, preprocess, and fingerprint an experimental pattern."""
    experimental_raw = load_diffraction_pattern(pattern_source, source_name=source_name)
    experimental_processed = preprocess_pattern(experimental_raw, preprocessing_params)
    detected_peaks = detect_peaks_in_pattern(experimental_processed, peak_params)
    normalized_peaks = _normalize_peak_table(detected_peaks.peaks)

    if normalized_peaks:
        two_theta_min = min(peak.two_theta for peak in normalized_peaks)
        two_theta_max = max(peak.two_theta for peak in normalized_peaks)
    else:
        two_theta_min = float(experimental_processed.two_theta.min())
        two_theta_max = float(experimental_processed.two_theta.max())

    fingerprint = ExperimentalFingerprint(
        source_name=experimental_processed.source_name,
        peaks=normalized_peaks,
        top_peaks=sorted(normalized_peaks, key=lambda peak: (-peak.intensity, peak.two_theta))[:top_n_prefilter],
        two_theta_min=two_theta_min,
        two_theta_max=two_theta_max,
    )
    return experimental_raw, experimental_processed, fingerprint


def _normalize_peak_table(peaks: list[Peak]) -> list[Peak]:
    """Normalize intensities to relative 0-100."""
    if not peaks:
        return []
    maximum = max(max(peak.intensity, 0.0) for peak in peaks)
    if maximum <= 0:
        return [Peak(two_theta=peak.two_theta, intensity=0.0, prominence=peak.prominence, width=peak.width) for peak in peaks]
    return [
        Peak(
            two_theta=peak.two_theta,
            intensity=(max(peak.intensity, 0.0) / maximum) * 100.0,
            prominence=peak.prominence,
            width=peak.width,
            hkl=peak.hkl,
        )
        for peak in peaks
    ]


def run_search_match(
    pattern_source,
    database_path: str | Path,
    library_config: LibraryBuildConfig,
    preprocessing_params: PreprocessingParams,
    peak_params: PeakDetectionParams,
    search_config: SearchConfig,
    source_name: str | None = None,
) -> SearchArtifacts:
    """Run indexed search & match against local precomputed library."""
    experimental_raw, experimental_processed, fingerprint = build_experimental_fingerprint(
        pattern_source=pattern_source,
        source_name=source_name,
        preprocessing_params=preprocessing_params,
        peak_params=peak_params,
        top_n_prefilter=search_config.top_n_prefilter,
    )

    repository = SQLiteLibraryRepository(database_path)
    library_stats = repository.get_stats()
    if library_stats.entry_count == 0:
        raise ValueError("Biblioteca vacía. Construí o reconstruí la biblioteca local antes de buscar.")

    candidates = repository.search_candidates(
        fingerprint=fingerprint,
        config=search_config,
        fingerprint_bin_size=library_config.fingerprint_bin_size,
    )

    matcher = PeakMatcher()
    ranking = matcher.match(fingerprint=fingerprint, candidates=candidates, config=search_config)
    multiphase = matcher.suggest_multiphase(
        fingerprint=fingerprint,
        ranking=ranking,
        candidates=candidates,
        config=search_config,
    )

    return SearchArtifacts(
        experimental_raw=experimental_raw,
        experimental_processed=experimental_processed,
        experimental_fingerprint=fingerprint,
        candidate_ranking=ranking,
        multiphase_candidates=multiphase,
        library_stats=library_stats,
        prefilter_candidate_count=len(candidates),
    )
