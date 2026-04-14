"""SQLite-backed repository for precomputed PXRD reference libraries."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from core.models import ExperimentalFingerprint, LibraryEntry, LibraryStats, Peak, SearchConfig


class SQLiteLibraryRepository:
    """Persist and query precomputed reference patterns in SQLite."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS library_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    formula TEXT,
                    crystal_system TEXT,
                    spacegroup TEXT,
                    elements_json TEXT NOT NULL,
                    two_theta_min REAL NOT NULL,
                    two_theta_max REAL NOT NULL,
                    top_peaks_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS peaks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id INTEGER NOT NULL,
                    peak_rank INTEGER NOT NULL,
                    two_theta REAL NOT NULL,
                    intensity REAL NOT NULL,
                    hkl_json TEXT,
                    FOREIGN KEY(entry_id) REFERENCES library_entries(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS peak_index (
                    bin INTEGER NOT NULL,
                    entry_id INTEGER NOT NULL,
                    peak_rank INTEGER NOT NULL,
                    two_theta REAL NOT NULL,
                    intensity REAL NOT NULL,
                    FOREIGN KEY(entry_id) REFERENCES library_entries(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_peaks_entry ON peaks(entry_id);
                CREATE INDEX IF NOT EXISTS idx_peak_index_bin ON peak_index(bin);
                CREATE INDEX IF NOT EXISTS idx_library_entries_range ON library_entries(two_theta_min, two_theta_max);
                """
            )

    @staticmethod
    def _serialize_peak(peak: Peak) -> dict[str, float | list[int] | None]:
        return {
            "two_theta": peak.two_theta,
            "intensity": peak.intensity,
            "hkl": None if peak.hkl is None else list(peak.hkl),
        }

    @staticmethod
    def _deserialize_peak(payload: dict) -> Peak:
        hkl = payload.get("hkl")
        return Peak(
            two_theta=float(payload["two_theta"]),
            intensity=float(payload["intensity"]),
            hkl=None if hkl is None else tuple(int(value) for value in hkl),
        )

    def replace_library(self, entries: list[LibraryEntry], fingerprint_bin_size: float) -> LibraryStats:
        """Replace current library contents with new precomputed entries."""
        with self._connect() as connection:
            connection.execute("DELETE FROM peak_index")
            connection.execute("DELETE FROM peaks")
            connection.execute("DELETE FROM library_entries")

            for entry in entries:
                self._insert_entry(connection, entry, fingerprint_bin_size)

        return self.get_stats()

    def _insert_entry(
        self,
        connection: sqlite3.Connection,
        entry: LibraryEntry,
        fingerprint_bin_size: float,
    ) -> int:
        """Insert one library entry plus peaks and top-peak index."""
        cursor = connection.execute(
            """
            INSERT INTO library_entries (
                source_id, filename, formula, crystal_system, spacegroup,
                elements_json, two_theta_min, two_theta_max, top_peaks_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.source_id,
                entry.filename,
                entry.formula,
                entry.crystal_system,
                entry.spacegroup,
                json.dumps(entry.elements),
                entry.two_theta_min,
                entry.two_theta_max,
                json.dumps([self._serialize_peak(peak) for peak in entry.top_peaks]),
                json.dumps(entry.metadata),
            ),
        )
        entry_id = int(cursor.lastrowid)
        entry.entry_id = entry_id

        for peak_rank, peak in enumerate(entry.peaks):
            connection.execute(
                """
                INSERT INTO peaks (entry_id, peak_rank, two_theta, intensity, hkl_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    peak_rank,
                    peak.two_theta,
                    peak.intensity,
                    json.dumps(list(peak.hkl)) if peak.hkl is not None else None,
                ),
            )

        for peak_rank, peak in enumerate(entry.top_peaks):
            peak_bin = int(round(peak.two_theta / fingerprint_bin_size))
            connection.execute(
                """
                INSERT INTO peak_index (bin, entry_id, peak_rank, two_theta, intensity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (peak_bin, entry_id, peak_rank, peak.two_theta, peak.intensity),
            )
        return entry_id

    def _delete_entry_by_source_id(self, connection: sqlite3.Connection, source_id: str) -> None:
        """Delete one entry and cascading child rows by source_id."""
        connection.execute("DELETE FROM library_entries WHERE source_id = ?", (source_id,))

    def _load_entry(self, entry_id: int) -> LibraryEntry:
        with self._connect() as connection:
            header = connection.execute(
                """
                SELECT id, source_id, filename, formula, crystal_system, spacegroup,
                       elements_json, two_theta_min, two_theta_max, top_peaks_json, metadata_json
                FROM library_entries
                WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
            if header is None:
                raise KeyError(f"Library entry not found: {entry_id}")

            peaks_rows = connection.execute(
                """
                SELECT peak_rank, two_theta, intensity, hkl_json
                FROM peaks
                WHERE entry_id = ?
                ORDER BY peak_rank ASC
                """,
                (entry_id,),
            ).fetchall()

        peaks = [
            Peak(
                two_theta=float(row["two_theta"]),
                intensity=float(row["intensity"]),
                hkl=None
                if row["hkl_json"] is None
                else tuple(int(value) for value in json.loads(row["hkl_json"])),
            )
            for row in peaks_rows
        ]
        top_peaks = [self._deserialize_peak(payload) for payload in json.loads(header["top_peaks_json"])]
        return LibraryEntry(
            entry_id=int(header["id"]),
            source_id=str(header["source_id"]),
            filename=str(header["filename"]),
            formula=header["formula"],
            crystal_system=header["crystal_system"],
            spacegroup=header["spacegroup"],
            elements=list(json.loads(header["elements_json"])),
            two_theta_min=float(header["two_theta_min"]),
            two_theta_max=float(header["two_theta_max"]),
            peaks=peaks,
            top_peaks=top_peaks,
            metadata=dict(json.loads(header["metadata_json"])),
        )

    def list_entries(self) -> list[LibraryEntry]:
        """Return all library entries."""
        with self._connect() as connection:
            ids = [int(row["id"]) for row in connection.execute("SELECT id FROM library_entries ORDER BY filename ASC")]
        return [self._load_entry(entry_id) for entry_id in ids]

    def upsert_entries(self, entries: list[LibraryEntry], fingerprint_bin_size: float) -> LibraryStats:
        """Insert or replace a subset of library entries."""
        if not entries:
            return self.get_stats()
        with self._connect() as connection:
            for entry in entries:
                self._delete_entry_by_source_id(connection, entry.source_id)
                self._insert_entry(connection, entry, fingerprint_bin_size)
        return self.get_stats()

    def delete_entries_by_source_ids(self, source_ids: list[str]) -> LibraryStats:
        """Delete library entries by source_id."""
        if not source_ids:
            return self.get_stats()
        with self._connect() as connection:
            for source_id in source_ids:
                self._delete_entry_by_source_id(connection, source_id)
        return self.get_stats()

    def get_stats(self) -> LibraryStats:
        """Return library summary."""
        with self._connect() as connection:
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM library_entries) AS entry_count,
                    (SELECT COUNT(*) FROM peaks) AS peak_count,
                    (SELECT MAX(created_at) FROM library_entries) AS last_updated
                """
            ).fetchone()
        return LibraryStats(
            database_path=self.database_path,
            entry_count=int(counts["entry_count"]),
            peak_count=int(counts["peak_count"]),
            last_updated=counts["last_updated"],
        )

    def search_candidates(
        self,
        fingerprint: ExperimentalFingerprint,
        config: SearchConfig,
        fingerprint_bin_size: float,
    ) -> list[LibraryEntry]:
        """Return prefiltered candidate entries using indexed top-peak bins."""
        if not fingerprint.top_peaks:
            return []

        bins: set[int] = set()
        for peak in fingerprint.top_peaks[: config.top_n_prefilter]:
            center = int(round(peak.two_theta / fingerprint_bin_size))
            tolerance_bins = max(1, int(round(config.two_theta_tolerance / fingerprint_bin_size)))
            for candidate_bin in range(center - tolerance_bins, center + tolerance_bins + 1):
                bins.add(candidate_bin)

        placeholders = ",".join("?" for _ in sorted(bins))
        if not placeholders:
            return []

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    entry_id,
                    COUNT(*) AS matched_bins
                FROM peak_index
                WHERE bin IN ({placeholders})
                GROUP BY entry_id
                """,
                tuple(sorted(bins)),
            ).fetchall()

            compatible_counts: dict[int, int] = defaultdict(int)
            for row in rows:
                compatible_counts[int(row["entry_id"])] = int(row["matched_bins"])

            filtered_ids = [
                entry_id
                for entry_id, compatible_count in compatible_counts.items()
                if compatible_count >= config.min_peak_matches
            ]
            if not filtered_ids:
                return []

            range_placeholders = ",".join("?" for _ in filtered_ids)
            headers = connection.execute(
                f"""
                SELECT id
                FROM library_entries
                WHERE id IN ({range_placeholders})
                  AND two_theta_min <= ?
                  AND two_theta_max >= ?
                ORDER BY filename ASC
                """,
                tuple(filtered_ids) + (fingerprint.two_theta_max, fingerprint.two_theta_min),
            ).fetchall()

        entries = [self._load_entry(int(row["id"])) for row in headers]
        if config.element_filter:
            expected = {element.strip().capitalize() for element in config.element_filter if element.strip()}
            entries = [entry for entry in entries if expected.issubset(set(entry.elements))]

        entries.sort(
            key=lambda entry: compatible_counts.get(entry.entry_id or -1, 0),
            reverse=True,
        )
        return entries[: config.max_candidates]
