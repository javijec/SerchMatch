"""Peak-based search & match implementation."""

from __future__ import annotations

from dataclasses import replace

from core.models import (
    BaseMatcher,
    CandidateMatch,
    ExperimentalFingerprint,
    LibraryEntry,
    MatchedPeak,
    Peak,
    PhaseCombination,
    ScoreBreakdown,
    SearchConfig,
)


def _normalize_peaks(peaks: list[Peak]) -> list[Peak]:
    """Scale peak intensities to relative 0-100."""
    if not peaks:
        return []
    maximum = max(max(peak.intensity, 0.0) for peak in peaks)
    if maximum <= 0:
        return [replace(peak, intensity=0.0) for peak in peaks]
    return [replace(peak, intensity=(max(peak.intensity, 0.0) / maximum) * 100.0) for peak in peaks]


class PeakMatcher(BaseMatcher):
    """Interpretable peak-based matcher with simple multifase helper."""

    def match(
        self,
        fingerprint: ExperimentalFingerprint,
        candidates: list[LibraryEntry],
        config: SearchConfig,
    ) -> list[CandidateMatch]:
        """Rank candidates using peak-position and intensity agreement."""
        results = [self._match_single(fingerprint, candidate, config) for candidate in candidates]
        return sorted(results, key=lambda item: item.score, reverse=True)

    def _match_single(
        self,
        fingerprint: ExperimentalFingerprint,
        candidate: LibraryEntry,
        config: SearchConfig,
    ) -> CandidateMatch:
        experimental_peaks = _normalize_peaks(fingerprint.peaks)
        theoretical_peaks = _normalize_peaks(candidate.peaks)

        if not experimental_peaks or not theoretical_peaks:
            breakdown = ScoreBreakdown(
                position_score=0.0,
                intensity_score=0.0,
                matched_fraction=0.0,
                missing_penalty=1.0 if theoretical_peaks else 0.0,
                extra_penalty=1.0 if experimental_peaks else 0.0,
                matched_peak_count=0,
                theoretical_peak_count=len(theoretical_peaks),
                experimental_peak_count=len(experimental_peaks),
                explained_experimental_count=0,
            )
            return CandidateMatch(
                entry=candidate,
                score=0.0,
                breakdown=breakdown,
                matched_peaks=[],
                explained_peak_indices=[],
                missing_theoretical_peaks=theoretical_peaks,
                extra_experimental_peaks=experimental_peaks,
            )

        used_experimental: set[int] = set()
        matched_peaks: list[MatchedPeak] = []
        explained_peak_indices: list[int] = []
        missing_theoretical: list[Peak] = []

        for theoretical_peak in theoretical_peaks:
            best_index = None
            best_delta = None
            for exp_index, experimental_peak in enumerate(experimental_peaks):
                if exp_index in used_experimental:
                    continue
                delta = abs(experimental_peak.two_theta - theoretical_peak.two_theta)
                if delta <= config.two_theta_tolerance and (best_delta is None or delta < best_delta):
                    best_delta = delta
                    best_index = exp_index

            if best_index is None:
                missing_theoretical.append(theoretical_peak)
                continue

            experimental_peak = experimental_peaks[best_index]
            used_experimental.add(best_index)
            explained_peak_indices.append(best_index)
            position_similarity = max(0.0, 1.0 - (best_delta / config.two_theta_tolerance))
            intensity_similarity = max(
                0.0,
                1.0 - abs(experimental_peak.intensity - theoretical_peak.intensity) / 100.0,
            )
            matched_peaks.append(
                MatchedPeak(
                    experimental_two_theta=experimental_peak.two_theta,
                    experimental_intensity=experimental_peak.intensity,
                    theoretical_two_theta=theoretical_peak.two_theta,
                    theoretical_intensity=theoretical_peak.intensity,
                    delta_two_theta=float(best_delta),
                    position_similarity=position_similarity,
                    intensity_similarity=intensity_similarity,
                )
            )

        extra_experimental = [
            experimental_peaks[index]
            for index in range(len(experimental_peaks))
            if index not in used_experimental
        ]
        matched_count = len(matched_peaks)
        theoretical_count = len(theoretical_peaks)
        experimental_count = len(experimental_peaks)

        position_score = (
            sum(match.position_similarity for match in matched_peaks) / matched_count if matched_count else 0.0
        )
        intensity_score = (
            sum(match.intensity_similarity for match in matched_peaks) / matched_count if matched_count else 0.0
        )
        matched_fraction = matched_count / max(theoretical_count, 1)
        missing_penalty = len(missing_theoretical) / max(theoretical_count, 1)
        extra_penalty = len(extra_experimental) / max(experimental_count, 1)

        weights = config.weights
        raw_score = (
            weights.position * position_score
            + weights.intensity * intensity_score
            + weights.matched_fraction * matched_fraction
            - weights.missing_penalty * missing_penalty
            - weights.extra_penalty * extra_penalty
        )
        normalized_score = max(0.0, min(100.0, raw_score * 100.0))

        breakdown = ScoreBreakdown(
            position_score=position_score,
            intensity_score=intensity_score,
            matched_fraction=matched_fraction,
            missing_penalty=missing_penalty,
            extra_penalty=extra_penalty,
            matched_peak_count=matched_count,
            theoretical_peak_count=theoretical_count,
            experimental_peak_count=experimental_count,
            explained_experimental_count=len(explained_peak_indices),
        )
        return CandidateMatch(
            entry=candidate,
            score=normalized_score,
            breakdown=breakdown,
            matched_peaks=matched_peaks,
            explained_peak_indices=explained_peak_indices,
            missing_theoretical_peaks=missing_theoretical,
            extra_experimental_peaks=extra_experimental,
        )

    def suggest_multiphase(
        self,
        fingerprint: ExperimentalFingerprint,
        ranking: list[CandidateMatch],
        candidates: list[LibraryEntry],
        config: SearchConfig,
    ) -> list[PhaseCombination]:
        """Build simple 2-phase proposals from residual unmatched peaks."""
        if not config.enable_multiphase or not ranking:
            return []

        primary = ranking[0]
        residual_peaks = [
            peak
            for index, peak in enumerate(fingerprint.peaks)
            if index not in set(primary.explained_peak_indices)
        ]
        if len(residual_peaks) < config.min_peak_matches:
            return []

        residual_fingerprint = ExperimentalFingerprint(
            source_name=f"{fingerprint.source_name} residual",
            peaks=residual_peaks,
            top_peaks=sorted(residual_peaks, key=lambda peak: (-peak.intensity, peak.two_theta))[
                : config.top_n_prefilter
            ],
            two_theta_min=min(peak.two_theta for peak in residual_peaks),
            two_theta_max=max(peak.two_theta for peak in residual_peaks),
        )

        remaining_candidates = [
            candidate
            for candidate in candidates
            if candidate.source_id != primary.entry.source_id
        ]
        if not remaining_candidates:
            return []

        secondary_ranking = self.match(residual_fingerprint, remaining_candidates, config)
        combinations: list[PhaseCombination] = []
        total_peak_count = max(len(fingerprint.peaks), 1)

        for secondary in secondary_ranking[: config.multifase_max_results]:
            explained_union = set(primary.explained_peak_indices)
            for match in secondary.matched_peaks:
                for exp_index, peak in enumerate(fingerprint.peaks):
                    if (
                        abs(peak.two_theta - match.experimental_two_theta) <= 1e-6
                        and abs(peak.intensity - match.experimental_intensity) <= 1e-6
                    ):
                        explained_union.add(exp_index)
            explained_fraction = len(explained_union) / total_peak_count
            combined_score = min(100.0, 0.55 * primary.score + 0.45 * secondary.score + 10.0 * explained_fraction)
            combinations.append(
                PhaseCombination(
                    phases=[primary, secondary],
                    combined_score=combined_score,
                    explained_fraction=explained_fraction,
                )
            )

        return sorted(combinations, key=lambda item: item.combined_score, reverse=True)
