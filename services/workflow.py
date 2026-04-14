"""High-level workflow orchestration for analysis sessions."""

from __future__ import annotations

from pathlib import Path

from core.io import export_results_to_csv, export_results_to_json, load_diffraction_pattern
from core.matching import rank_candidate_patterns
from core.models import (
    MatchingParams,
    PeakDetectionParams,
    PreprocessingParams,
    SimulatedPattern,
    SimulationParams,
    WorkflowArtifacts,
)
from core.peaks import detect_peaks_in_pattern
from core.preprocessing import preprocess_pattern
from core.simulation import simulate_pattern_from_cif


def run_analysis(
    pattern_source,
    cif_paths: list[str | Path],
    preprocessing_params: PreprocessingParams,
    peak_params: PeakDetectionParams,
    simulation_params: SimulationParams,
    matching_params: MatchingParams,
    source_name: str | None = None,
) -> WorkflowArtifacts:
    """Run the end-to-end analysis workflow."""
    experimental_raw = load_diffraction_pattern(pattern_source, source_name=source_name)
    experimental_processed = preprocess_pattern(experimental_raw, preprocessing_params)
    detected_peaks = detect_peaks_in_pattern(experimental_processed, peak_params)

    simulated_candidates: list[SimulatedPattern] = [
        simulate_pattern_from_cif(cif_path, simulation_params) for cif_path in cif_paths
    ]
    candidate_results = rank_candidate_patterns(detected_peaks, simulated_candidates, matching_params)

    return WorkflowArtifacts(
        experimental_raw=experimental_raw,
        experimental_processed=experimental_processed,
        detected_peaks=detected_peaks,
        candidate_results=candidate_results[: matching_params.top_n],
    )


def serialize_match_results(artifacts: WorkflowArtifacts) -> list[dict]:
    """Serialize results for export or external use."""
    records: list[dict] = []
    for result in artifacts.candidate_results:
        records.append(
            {
                "phase_name": result.phase_name,
                "cif_path": str(result.cif_path),
                "score": round(result.score, 3),
                "matched_peak_fraction": round(result.breakdown.matched_peak_fraction, 3),
                "position_score": round(result.breakdown.position_score, 3),
                "intensity_score": round(result.breakdown.intensity_score, 3),
                "missing_penalty": round(result.breakdown.missing_penalty, 3),
                "matched_peak_count": result.breakdown.matched_peak_count,
                "important_theoretical_peak_count": result.breakdown.important_theoretical_peak_count,
            }
        )
    return records


def export_analysis_results(artifacts: WorkflowArtifacts, destination: str | Path) -> Path:
    """Export ranking results to CSV or JSON based on filename extension."""
    path = Path(destination)
    records = serialize_match_results(artifacts)
    if path.suffix.lower() == ".csv":
        export_results_to_csv(records, path)
    elif path.suffix.lower() == ".json":
        export_results_to_json(records, path)
    else:
        raise ValueError("Use una extensión .csv o .json para exportar resultados.")
    return path
