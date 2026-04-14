"""Streamlit UI for indexed PXRD/XRD search & match."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.models import LibraryBuildConfig, PeakDetectionParams, PreprocessingParams, SearchConfig, SimulationParams
from core.simulation import library_entry_to_stick_pattern
from services.indexing import get_library_stats, rebuild_local_library, sync_cod_library_incremental
from services.system_tools import get_command_status, install_svn_with_winget
from services.workflow import matched_peaks_to_dataframe, multiphase_to_json_rows, run_analysis, serialize_match_results


DEFAULT_LIBRARY_PATH = PROJECT_ROOT / "data" / "reference_library.sqlite"
DEFAULT_CIF_FOLDER = PROJECT_ROOT / "data" / "cif_library"
DEFAULT_COD_MIRROR = PROJECT_ROOT / "data" / "cod_mirror"

st.set_page_config(page_title="PXRD Search & Match", layout="wide")


def pattern_figure(two_theta: pd.Series, intensity: pd.Series, title: str) -> go.Figure:
    """Create base experimental pattern figure."""
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=two_theta,
            y=intensity,
            mode="lines",
            name="Experimental",
            line={"width": 2, "color": "#1f4e79"},
        )
    )
    figure.update_layout(
        title=title,
        xaxis_title="2theta (deg)",
        yaxis_title="Intensidad relativa",
        template="plotly_white",
        height=440,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    return figure


def add_fingerprint_markers(figure: go.Figure, fingerprint_df: pd.DataFrame) -> None:
    """Overlay detected experimental peaks."""
    if fingerprint_df.empty:
        return
    figure.add_trace(
        go.Scatter(
            x=fingerprint_df["two_theta"],
            y=fingerprint_df["intensity"],
            mode="markers",
            name="Picos experimentales",
            marker={"size": 8, "color": "#c43c39", "symbol": "diamond"},
        )
    )


def overlay_match_figure(processed_df: pd.DataFrame, candidate) -> go.Figure:
    """Overlay experimental profile with theoretical stick pattern."""
    figure = pattern_figure(processed_df["two_theta"], processed_df["intensity"], "Overlay experimental vs. referencia")
    theoretical_df = library_entry_to_stick_pattern(candidate.entry)
    figure.add_trace(
        go.Bar(
            x=theoretical_df["two_theta"],
            y=theoretical_df["intensity"],
            name=f"Teórico: {candidate.entry.filename}",
            marker_color="#3d8361",
            opacity=0.35,
        )
    )

    explained_df = pd.DataFrame(
        [
            {
                "two_theta": match.experimental_two_theta,
                "intensity": match.experimental_intensity,
            }
            for match in candidate.matched_peaks
        ]
    )
    unexplained_df = pd.DataFrame(
        [
            {
                "two_theta": peak.two_theta,
                "intensity": peak.intensity,
            }
            for peak in candidate.extra_experimental_peaks
        ]
    )
    if not explained_df.empty:
        figure.add_trace(
            go.Scatter(
                x=explained_df["two_theta"],
                y=explained_df["intensity"],
                mode="markers",
                name="Picos explicados",
                marker={"size": 9, "color": "#188038", "symbol": "circle"},
            )
        )
    if not unexplained_df.empty:
        figure.add_trace(
            go.Scatter(
                x=unexplained_df["two_theta"],
                y=unexplained_df["intensity"],
                mode="markers",
                name="Picos no explicados",
                marker={"size": 9, "color": "#b3261e", "symbol": "x"},
            )
        )
    figure.update_layout(barmode="overlay", height=520)
    return figure


def _ensure_library_stats(path: Path):
    """Return library stats, creating DB if missing."""
    return get_library_stats(path)


def main() -> None:
    """Render Streamlit application."""
    st.title("PXRD/XRD Search & Match")
    st.caption("Motor peak-based indexado con biblioteca local precomputada, pensado para crecer hacia una herramienta abierta y mantenible.")

    library_db_path = Path(st.session_state.get("library_db_path", str(DEFAULT_LIBRARY_PATH)))
    library_stats = _ensure_library_stats(library_db_path)

    with st.sidebar:
        st.header("Biblioteca local")
        library_db_text = st.text_input("SQLite biblioteca", value=str(library_db_path))
        cif_folder = st.text_input("Carpeta de CIFs", value=str(DEFAULT_CIF_FOLDER))
        top_peaks_count = st.slider("Top picos por referencia", 5, 30, 12)
        fingerprint_bin_size = st.slider("Bin fingerprint (deg)", 0.05, 0.5, 0.2, step=0.05)
        parallel_workers = st.slider("Workers indexación", 1, 8, 1, step=1)
        sim_two_theta_min = st.number_input("2theta min biblioteca", value=5.0, min_value=0.0, max_value=180.0)
        sim_two_theta_max = st.number_input("2theta max biblioteca", value=90.0, min_value=1.0, max_value=180.0)
        wavelength = st.selectbox("Radiación", ["CuKa", "CuKa1", "MoKa", "CrKa", "FeKa"], index=0)
        include_elements_text = st.text_input("Incluir elementos", value="", help="Prefiltro químico antes de indexar. Ej: Na, Cl")
        exclude_elements_text = st.text_input("Excluir elementos", value="", help="Excluir CIFs que contengan estos elementos.")

        library_config = LibraryBuildConfig(
            top_peaks_count=top_peaks_count,
            fingerprint_bin_size=fingerprint_bin_size,
            parallel_workers=parallel_workers,
            include_elements=[value.strip() for value in include_elements_text.split(",") if value.strip()] or None,
            exclude_elements=[value.strip() for value in exclude_elements_text.split(",") if value.strip()] or None,
            simulation=SimulationParams(
                wavelength=wavelength,
                two_theta_min=sim_two_theta_min,
                two_theta_max=sim_two_theta_max,
                scaled=True,
                min_relative_intensity=0.5,
            ),
        )

        if st.button("Reconstruir biblioteca", use_container_width=True):
            try:
                stats = rebuild_local_library(cif_folder, library_db_text, library_config)
                st.session_state["library_db_path"] = str(library_db_text)
                st.success(f"Biblioteca reconstruida: {stats.entry_count} entradas, {stats.peak_count} picos.")
                library_stats = stats
                library_db_path = Path(library_db_text)
            except Exception as exc:
                st.error(f"No se pudo reconstruir biblioteca: {exc}")

        st.subheader("Sync incremental COD")
        svn_status = get_command_status("svn")
        status_text = svn_status.version or svn_status.message
        st.caption(f"SVN: {'disponible' if svn_status.available else 'no disponible'} | {status_text}")
        svn_install_col, svn_verify_col = st.columns(2)
        with svn_install_col:
            if st.button("Instalar SVN", use_container_width=True):
                try:
                    status = install_svn_with_winget()
                    if status.available:
                        st.success(f"SVN instalado: {status.version or status.path}")
                    else:
                        st.info(status.message)
                except Exception as exc:
                    st.error(f"No se pudo instalar SVN: {exc}")
        with svn_verify_col:
            if st.button("Verificar SVN", use_container_width=True):
                status = get_command_status("svn")
                if status.available:
                    st.success(f"SVN OK: {status.version or status.path}")
                else:
                    st.warning(status.message)
        cod_root = st.text_input("Mirror local COD", value=str(DEFAULT_COD_MIRROR))
        cod_method = st.selectbox("Método sync COD", options=["svn", "rsync"], index=0)
        perform_remote_sync = st.checkbox(
            "Ejecutar sync remoto",
            value=False,
            help="Activá esto si ya tenés `svn` o `rsync` instalado. Si no, usa solo scan incremental sobre un mirror local ya descargado.",
        )
        if st.button("Sync COD incremental", use_container_width=True):
            try:
                report = sync_cod_library_incremental(
                    sync_root=cod_root,
                    database_path=library_db_text,
                    config=library_config,
                    method=cod_method,
                    perform_remote_sync=perform_remote_sync,
                )
                st.session_state["library_db_path"] = str(library_db_text)
                library_stats = report.library_stats
                st.success(
                    "COD sync listo. "
                    f"+{report.added_count} nuevos, ~{report.modified_count} modificados, "
                    f"-{report.deleted_count} borrados, {report.filtered_out_count} filtrados, "
                    f"{report.reindexed_count} reindexados."
                )
            except Exception as exc:
                st.error(f"No se pudo sincronizar COD: {exc}")

        st.caption(
            f"Entradas indexadas: {library_stats.entry_count} | picos almacenados: {library_stats.peak_count}"
        )

        st.header("Patrón experimental")
        experimental_file = st.file_uploader(
            "Difractograma experimental",
            type=["xy", "txt", "csv"],
            help="Archivo experimental con columnas 2theta e intensidad.",
        )

        st.header("Preprocesamiento")
        preprocessing_params = PreprocessingParams(
            normalize=st.checkbox("Normalizar intensidad", value=True),
            smoothing_enabled=st.checkbox("Suavizado Savitzky-Golay", value=False),
            smoothing_window=st.slider("Ventana suavizado", 5, 41, 11, step=2),
            smoothing_polyorder=st.slider("Orden polinomial", 2, 5, 3),
            background_correction_enabled=st.checkbox("Corrección fondo", value=False),
            background_window=st.slider("Ventana fondo", 11, 201, 51, step=2),
            clip_negative=st.checkbox("Recortar negativos", value=True),
        )

        st.header("Fingerprint experimental")
        raw_min_width = st.slider("Ancho mínimo", 0.0, 20.0, 0.0, step=0.5)
        peak_params = PeakDetectionParams(
            min_height=st.slider("Altura mínima", 0.0, 100.0, 5.0, step=0.5),
            prominence=st.slider("Prominencia", 0.0, 100.0, 3.0, step=0.5),
            min_distance_points=st.slider("Distancia mínima (pts)", 1, 50, 5),
            min_width=raw_min_width if raw_min_width > 0 else None,
        )

        st.header("Search & Match")
        search_config = SearchConfig(
            two_theta_tolerance=st.slider("Tolerancia 2theta", 0.02, 1.0, 0.20, step=0.01),
            min_peak_matches=st.slider("Mínimo picos compatibles", 1, 8, 2),
            top_n_prefilter=st.slider("Top N picos prefilter", 3, 20, 8),
            max_candidates=st.slider("Máximo candidatos detallados", 5, 200, 50),
            multifase_max_results=st.slider("Máx. combinaciones 2 fases", 1, 10, 5),
            enable_multiphase=st.checkbox("Búsqueda multifase simple", value=True),
        )
        element_filter_text = st.text_input("Filtro opcional elementos", value="", help="Ej: Na, Cl")
        if element_filter_text.strip():
            search_config.element_filter = [value.strip() for value in element_filter_text.split(",") if value.strip()]

        run_clicked = st.button("Ejecutar Search & Match", use_container_width=True, type="primary")

    if not experimental_file:
        st.info("Cargá un difractograma experimental. Si todavía no construiste biblioteca, usá la sección lateral.")
        st.markdown(
            f"Ejemplos incluidos: `{PROJECT_ROOT / 'data' / 'examples' / 'sample_experimental.xy'}` y carpeta `{DEFAULT_CIF_FOLDER}`"
        )
        return

    if library_stats.entry_count == 0:
        st.warning("Biblioteca local vacía. Reconstruí primero desde una carpeta de CIFs.")
        return

    if not run_clicked and "analysis_artifacts" not in st.session_state:
        st.warning("Presioná `Ejecutar Search & Match` para analizar con parámetros actuales.")
        return

    try:
        if run_clicked:
            artifacts = run_analysis(
                pattern_source=experimental_file,
                database_path=library_db_text,
                library_config=library_config,
                preprocessing_params=preprocessing_params,
                peak_params=peak_params,
                search_config=search_config,
                source_name=experimental_file.name,
            )
            st.session_state["analysis_artifacts"] = artifacts
            st.session_state["library_db_path"] = library_db_text
        artifacts = st.session_state["analysis_artifacts"]
    except Exception as exc:
        st.error(f"No se pudo completar search & match: {exc}")
        return

    processed_df = artifacts.experimental_processed.to_dataframe()
    fingerprint_df = artifacts.experimental_fingerprint.to_dataframe()
    ranking_df = pd.DataFrame(serialize_match_results(artifacts))

    summary_col, summary_col_2, summary_col_3, summary_col_4 = st.columns(4)
    with summary_col:
        st.metric("Entradas indexadas", artifacts.library_stats.entry_count)
    with summary_col_2:
        st.metric("Picos experimentales", len(fingerprint_df))
    with summary_col_3:
        st.metric("Candidatos prefiltrados", artifacts.prefilter_candidate_count)
    with summary_col_4:
        best_score = artifacts.candidate_ranking[0].score if artifacts.candidate_ranking else 0.0
        st.metric("Mejor score", f"{best_score:.1f}")

    chart_col, peaks_col = st.columns([1.7, 1.0])
    with chart_col:
        figure = pattern_figure(processed_df["two_theta"], processed_df["intensity"], "Difractograma procesado")
        add_fingerprint_markers(figure, fingerprint_df)
        st.plotly_chart(figure, use_container_width=True)
    with peaks_col:
        st.subheader("Top picos fingerprint")
        top_df = pd.DataFrame(
            [
                {"two_theta": peak.two_theta, "intensity": peak.intensity}
                for peak in artifacts.experimental_fingerprint.top_peaks
            ]
        )
        st.dataframe(top_df, use_container_width=True, hide_index=True)

    st.subheader("Tabla de picos experimentales")
    st.dataframe(fingerprint_df, use_container_width=True, hide_index=True)

    st.subheader("Ranking de candidatos")
    st.dataframe(ranking_df, use_container_width=True, hide_index=True)

    if not artifacts.candidate_ranking:
        st.warning("Prefiltro sin candidatos compatibles. Probá aumentar tolerancia o bajar restricciones.")
        return

    candidate_labels = [
        f"{candidate.entry.filename} | {candidate.entry.formula or 'sin fórmula'} | {candidate.score:.1f}"
        for candidate in artifacts.candidate_ranking
    ]
    selected_label = st.selectbox("Detalle de candidato", options=candidate_labels)
    selected_index = candidate_labels.index(selected_label)
    selected_candidate = artifacts.candidate_ranking[selected_index]

    st.plotly_chart(overlay_match_figure(processed_df, selected_candidate), use_container_width=True)

    detail_col_1, detail_col_2 = st.columns([1.0, 1.2])
    with detail_col_1:
        st.subheader("Desglose score")
        st.json(
            {
                "score_total": round(selected_candidate.score, 3),
                "source_id": selected_candidate.entry.source_id,
                "formula": selected_candidate.entry.formula,
                "crystal_system": selected_candidate.entry.crystal_system,
                "spacegroup": selected_candidate.entry.spacegroup,
                "position_score": round(selected_candidate.breakdown.position_score * 100.0, 2),
                "intensity_score": round(selected_candidate.breakdown.intensity_score * 100.0, 2),
                "matched_fraction": round(selected_candidate.breakdown.matched_fraction * 100.0, 2),
                "missing_penalty": round(selected_candidate.breakdown.missing_penalty * 100.0, 2),
                "extra_penalty": round(selected_candidate.breakdown.extra_penalty * 100.0, 2),
                "matched_peak_count": selected_candidate.breakdown.matched_peak_count,
            }
        )
        st.subheader("Picos faltantes teóricos")
        missing_df = pd.DataFrame(
            [{"two_theta": peak.two_theta, "intensity": peak.intensity} for peak in selected_candidate.missing_theoretical_peaks]
        )
        st.dataframe(missing_df, use_container_width=True, hide_index=True)
    with detail_col_2:
        st.subheader("Picos emparejados")
        st.dataframe(matched_peaks_to_dataframe(artifacts, selected_index), use_container_width=True, hide_index=True)
        st.subheader("Picos experimentales no explicados")
        extra_df = pd.DataFrame(
            [{"two_theta": peak.two_theta, "intensity": peak.intensity} for peak in selected_candidate.extra_experimental_peaks]
        )
        st.dataframe(extra_df, use_container_width=True, hide_index=True)

    st.subheader("Búsqueda multifase simple")
    multiphase_df = pd.DataFrame(
        [
            {
                "phases": combination.label(),
                "combined_score": round(combination.combined_score, 3),
                "explained_fraction": round(combination.explained_fraction * 100.0, 2),
            }
            for combination in artifacts.multiphase_candidates
        ]
    )
    if multiphase_df.empty:
        st.info("Sin propuesta multifase adicional. Caso posiblemente monofásico o residual insuficiente.")
    else:
        st.dataframe(multiphase_df, use_container_width=True, hide_index=True)

    export_col_1, export_col_2, export_col_3 = st.columns(3)
    with export_col_1:
        st.download_button(
            "Descargar ranking CSV",
            data=ranking_df.to_csv(index=False).encode("utf-8"),
            file_name="xrd_search_match_ranking.csv",
            mime="text/csv",
        )
    with export_col_2:
        st.download_button(
            "Descargar ranking JSON",
            data=json.dumps(serialize_match_results(artifacts), indent=2).encode("utf-8"),
            file_name="xrd_search_match_ranking.json",
            mime="application/json",
        )
    with export_col_3:
        st.download_button(
            "Descargar multifase JSON",
            data=multiphase_to_json_rows(artifacts),
            file_name="xrd_search_match_multiphase.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()
