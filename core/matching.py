"""Search & match routines across multiple candidate phases."""

from __future__ import annotations

from core.models import MatchResult, MatchingParams, PeakTable, SimulatedPattern
from core.scoring import score_peak_match


def rank_candidate_patterns(
    experimental_peaks: PeakTable,
    candidates: list[SimulatedPattern],
    params: MatchingParams,
) -> list[MatchResult]:
    """Rank simulated candidate phases by similarity score."""
    results: list[MatchResult] = []
    for candidate in candidates:
        score, breakdown, matches = score_peak_match(experimental_peaks, candidate.peaks, params)
        results.append(
            MatchResult(
                phase_name=candidate.phase_name,
                cif_path=candidate.cif_path,
                score=score,
                breakdown=breakdown,
                matched_peaks=matches,
                simulated_pattern=candidate,
            )
        )

    return sorted(results, key=lambda result: result.score, reverse=True)
