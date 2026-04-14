"""Streamlit UI for PXRD/XRD search & match."""

from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.models import MatchingParams, PeakDetectionParams, PreprocessingParams, SimulationParams
from services.workflow import run_analysis, serialize_match_results


st.set_page_config(page_title="XRD Search & Match", layout="wide")


def pattern_figure(two_theta: pd.Series, intensity: pd.Series, title: str) -> go.Figure:
    """Create a line figure for a diffraction pattern."""
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=two_theta,
            y=intensity,
            mode="lines",
            name=title,
            line={"width": 2},
        )
    )
    figure.update_layout(
        title=title,
        xaxis_title="2theta (deg)",
        yaxis_title="Intensidad relativa",
        template="plotly_white",
        height=420,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        legend={"orientation": "h"},
    )
    return figure


def add_peak_markers(figure: go.Figure, peaks_df: pd.DataFrame) -> None:
    """Add peak markers to the pattern figure."""
    if peaks_df.empty:
        return
    figure.add_trace(
        go.Scatter(
            x=peaks_df["two_theta"],
            y=peaks_df["intensity"],
            mode="markers",
            name="Picos detectados",
            marker={"size": 8, "color": "#c43c39", "symbol": "x"},
        )
    )


def overlay_candidates_figure(experimental_df: pd.DataFrame, selected_results) -> go.Figure:
    """Create an overlay chart for the experimental pattern and selected candidates."""
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=experimental_df["two_theta"],
            y=experimental_df["intensity"],
            mode="lines",
            name="Experimental",
            line={"width": 2, "color": "#1f4e79"},
        )
    )

    colors = ["#b85c38", "#3d8361", "#7b5ea7", "#586069", "#d97706"]
    for idx, result in enumerate(selected_results):
        candidate_df = result.simulated_pattern.pattern.to_dataframe()
        figure.add_trace(
            go.Bar(
                x=candidate_df["two_theta"],
                y=candidate_df["intensity"],
                name=result.phase_name,
                marker_color=colors[idx % len(colors)],
                opacity=0.45,
            )
        )

    figure.update_layout(
        title="Superposición experimental vs. candidatos",
        xaxis_title="2theta (deg)",
        yaxis_title="Intensidad relativa",
        template="plotly_white",
        height=520,
        barmode="overlay",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    return figure


def main() -> None:
    """Render the Streamlit application."""
    st.title("PXRD/XRD Search & Match")
    st.caption("Análisis local de difracción de rayos X por polvo con comparación frente a patrones generados desde CIF.")

    with st.sidebar:
        st.header("Entradas")
        experimental_file = st.file_uploader(
            "Difractograma experimental",
            type=["xy", "txt", "csv"],
            help="Archivos de dos columnas con 2theta e intensidad.",
        )
        cif_files = st.file_uploader(
            "Archivos CIF",
            type=["cif"],
            accept_multiple_files=True,
            help="Cargá uno o más CIFs para generar patrones teóricos candidatos.",
        )

        st.header("Preprocesamiento")
        preprocessing_params = PreprocessingParams(
            normalize=st.checkbox("Normalizar intensidad", value=True),
            smoothing_enabled=st.checkbox("Suavizado Savitzky-Golay", value=False),
            smoothing_window=st.slider("Ventana de suavizado", 5, 41, 11, step=2),
            smoothing_polyorder=st.slider("Orden polinomial", 2, 5, 3),
            background_correction_enabled=st.checkbox("Corrección de fondo simple", value=False),
            background_window=st.slider("Ventana de fondo", 11, 201, 51, step=2),
            clip_negative=st.checkbox("Recortar intensidades negativas", value=True),
        )

        st.header("Detección de picos")
        raw_min_width = st.slider("Ancho mínimo", 0.0, 20.0, 0.0, step=0.5)
        peak_params = PeakDetectionParams(
            min_height=st.slider("Altura mínima", 0.0, 100.0, 5.0, step=0.5),
            prominence=st.slider("Prominencia mínima", 0.0, 100.0, 3.0, step=0.5),
            min_distance_points=st.slider("Distancia mínima (puntos)", 1, 50, 5),
            min_width=raw_min_width if raw_min_width > 0 else None,
        )

        st.header("Matching")
        simulation_params = SimulationParams(
            wavelength=st.selectbox("Radiación", ["CuKa", "CuKa1", "MoKa", "CrKa", "FeKa"], index=0),
            two_theta_min=st.number_input("2theta mínimo", value=5.0, min_value=0.0, max_value=180.0),
            two_theta_max=st.number_input("2theta máximo", value=90.0, min_value=1.0, max_value=180.0),
            scaled=True,
        )
        matching_params = MatchingParams(
            two_theta_tolerance=st.slider("Tolerancia 2theta", 0.01, 1.0, 0.20, step=0.01),
            intensity_weight=st.slider("Peso intensidades", 0.0, 1.0, 0.35, step=0.05),
            position_weight=st.slider("Peso posiciones", 0.0, 1.0, 0.45, step=0.05),
            missing_peak_weight=st.slider("Peso penalización faltantes", 0.0, 1.0, 0.20, step=0.05),
            min_theoretical_relative_intensity=st.slider("Intensidad teórica mínima (%)", 0.0, 50.0, 5.0, step=1.0),
            top_n=st.slider("Top N candidatos", 1, 20, 10),
        )

        run_clicked = st.button("Ejecutar análisis", use_container_width=True, type="primary")

    if not experimental_file or not cif_files:
        st.info("Cargá un difractograma experimental y al menos un CIF para ejecutar el search & match.")
        st.markdown(
            f"Ejemplos incluidos: `{PROJECT_ROOT / 'data' / 'examples' / 'sample_experimental.xy'}` y `{PROJECT_ROOT / 'data' / 'cif_library'}`"
        )
        return

    if not run_clicked and "analysis_artifacts" not in st.session_state:
        st.warning("Presioná `Ejecutar análisis` para procesar el patrón con los parámetros actuales.")
        return

    try:
        if run_clicked:
            temp_cif_dir = PROJECT_ROOT / "data" / "_tmp_uploaded_cifs"
            temp_cif_dir.mkdir(parents=True, exist_ok=True)
            cif_paths: list[Path] = []
            for cif_file in cif_files:
                target_path = temp_cif_dir / cif_file.name
                target_path.write_bytes(cif_file.getbuffer())
                cif_paths.append(target_path)

            artifacts = run_analysis(
                pattern_source=BytesIO(experimental_file.getvalue()),
                cif_paths=cif_paths,
                preprocessing_params=preprocessing_params,
                peak_params=peak_params,
                simulation_params=simulation_params,
                matching_params=matching_params,
                source_name=experimental_file.name,
            )
            st.session_state["analysis_artifacts"] = artifacts

        artifacts = st.session_state["analysis_artifacts"]
    except Exception as exc:
        st.error(f"No se pudo completar el análisis: {exc}")
        return

    processed_df = artifacts.experimental_processed.to_dataframe()
    peaks_df = artifacts.detected_peaks.to_dataframe()

    main_col, side_col = st.columns([1.7, 1.0])
    with main_col:
        figure = pattern_figure(
            processed_df["two_theta"],
            processed_df["intensity"],
            title="Difractograma experimental procesado",
        )
        add_peak_markers(figure, peaks_df)
        st.plotly_chart(figure, use_container_width=True)

    with side_col:
        st.subheader("Resumen")
        st.metric("Picos detectados", len(peaks_df))
        if artifacts.candidate_results:
            st.metric("Mejor score", f"{artifacts.candidate_results[0].score:.1f}")
            st.metric("Mejor candidato", artifacts.candidate_results[0].phase_name)

    st.subheader("Picos detectados")
    st.dataframe(peaks_df, use_container_width=True, hide_index=True)

    ranking_rows = serialize_match_results(artifacts)
    ranking_df = pd.DataFrame(ranking_rows)
    st.subheader("Ranking de fases candidatas")
    st.dataframe(ranking_df, use_container_width=True, hide_index=True)

    if not artifacts.candidate_results:
        st.warning("No se encontraron candidatos para mostrar.")
        return

    phase_names = [result.phase_name for result in artifacts.candidate_results]
    selected_phase_names = st.multiselect(
        "Candidatos para superponer",
        options=phase_names,
        default=phase_names[: min(3, len(phase_names))],
    )
    selected_results = [result for result in artifacts.candidate_results if result.phase_name in selected_phase_names]

    if selected_results:
        st.plotly_chart(
            overlay_candidates_figure(processed_df, selected_results),
            use_container_width=True,
        )

    selected_detail_name = st.selectbox("Detalle de candidato", phase_names)
    selected_detail = next(result for result in artifacts.candidate_results if result.phase_name == selected_detail_name)

    detail_col_1, detail_col_2 = st.columns([1.0, 1.2])
    with detail_col_1:
        st.subheader("Desglose del score")
        st.json(
            {
                "score_total": round(selected_detail.score, 3),
                "matched_peak_fraction": round(selected_detail.breakdown.matched_peak_fraction, 3),
                "position_score": round(selected_detail.breakdown.position_score, 3),
                "intensity_score": round(selected_detail.breakdown.intensity_score, 3),
                "missing_penalty": round(selected_detail.breakdown.missing_penalty, 3),
                "matched_peak_count": selected_detail.breakdown.matched_peak_count,
                "important_theoretical_peak_count": selected_detail.breakdown.important_theoretical_peak_count,
                "cif_path": str(selected_detail.cif_path),
            }
        )

    with detail_col_2:
        st.subheader("Picos emparejados")
        st.dataframe(pd.DataFrame(selected_detail.matched_peaks), use_container_width=True, hide_index=True)

    export_col_1, export_col_2 = st.columns(2)
    with export_col_1:
        st.download_button(
            "Descargar ranking CSV",
            data=ranking_df.to_csv(index=False).encode("utf-8"),
            file_name="xrd_search_match_results.csv",
            mime="text/csv",
        )
    with export_col_2:
        st.download_button(
            "Descargar ranking JSON",
            data=json.dumps(ranking_rows, indent=2).encode("utf-8"),
            file_name="xrd_search_match_results.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()
