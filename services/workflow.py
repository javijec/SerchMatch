"""Compatibility workflow wrappers for app and exports."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.io import export_results_to_csv, export_results_to_json
from core.models import LibraryBuildConfig, PeakDetectionParams, PreprocessingParams, SearchArtifacts, SearchConfig
from services.search import run_search_match


def run_analysis(
    pattern_source,
    database_path: str | Path,
    library_config: LibraryBuildConfig,
    preprocessing_params: PreprocessingParams,
    peak_params: PeakDetectionParams,
    search_config: SearchConfig,
    source_name: str | None = None,
) -> SearchArtifacts:
    """Run indexed search & match analysis."""
    return run_search_match(
        pattern_source=pattern_source,
        database_path=database_path,
        library_config=library_config,
        preprocessing_params=preprocessing_params,
        peak_params=peak_params,
        search_config=search_config,
        source_name=source_name,
    )


def serialize_match_results(artifacts: SearchArtifacts) -> list[dict]:
    """Serialize ranking for UI and export."""
    return [candidate.to_row() for candidate in artifacts.candidate_ranking]


def export_analysis_results(artifacts: SearchArtifacts, destination: str | Path) -> Path:
    """Export ranking results to CSV or JSON."""
    path = Path(destination)
    records = serialize_match_results(artifacts)
    if path.suffix.lower() == ".csv":
        export_results_to_csv(records, path)
    elif path.suffix.lower() == ".json":
        export_results_to_json(records, path)
    else:
        raise ValueError("Use extensión .csv o .json para exportar resultados.")
    return path


def matched_peaks_to_dataframe(artifacts: SearchArtifacts, candidate_index: int = 0) -> pd.DataFrame:
    """Return matched peaks table for selected candidate."""
    if not artifacts.candidate_ranking:
        return pd.DataFrame()
    candidate = artifacts.candidate_ranking[candidate_index]
    return pd.DataFrame(
        [
            {
                "experimental_two_theta": match.experimental_two_theta,
                "experimental_intensity": match.experimental_intensity,
                "theoretical_two_theta": match.theoretical_two_theta,
                "theoretical_intensity": match.theoretical_intensity,
                "delta_two_theta": match.delta_two_theta,
                "position_similarity": match.position_similarity,
                "intensity_similarity": match.intensity_similarity,
            }
            for match in candidate.matched_peaks
        ]
    )


def multiphase_to_json_rows(artifacts: SearchArtifacts) -> bytes:
    """Return JSON bytes for proposed multifase combinations."""
    payload = [
        {
            "phases": [phase.entry.filename for phase in combination.phases],
            "combined_score": combination.combined_score,
            "explained_fraction": combination.explained_fraction,
        }
        for combination in artifacts.multiphase_candidates
    ]
    return json.dumps(payload, indent=2).encode("utf-8")
