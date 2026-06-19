from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd


@dataclass
class MemoryTermRecord:
    field_name: str
    raw_term: str
    normalized_term: str
    mapped_term: str
    source_type: str          # prior_table / deterministic / llm / manual_review
    run_version: str
    confidence: str = ""
    notes: str = ""


class MemoryV2:
    """
    Simple file-backed memory store.
    Can be upgraded later to DuckDB/SQLite.
    """

    def __init__(self, memory_dir: Path):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.term_registry_path = self.memory_dir / "term_registry.parquet"
        self.error_registry_path = self.memory_dir / "error_registry.parquet"
        self.repair_registry_path = self.memory_dir / "repair_registry.parquet"

        self.term_df = self._load_or_empty(
            self.term_registry_path,
            columns=["field_name", "raw_term", "normalized_term", "mapped_term", "source_type", "run_version", "confidence", "notes"]
        )
        self.error_df = self._load_or_empty(
            self.error_registry_path,
            columns=["run_version", "module", "error_type", "raw_input", "resolution", "notes"]
        )
        self.repair_df = self._load_or_empty(
            self.repair_registry_path,
            columns=["run_version", "module", "pattern", "repair_action", "success", "notes"]
        )

    def _load_or_empty(self, path: Path, columns: List[str]) -> pd.DataFrame:
        if path.exists():
            return pd.read_parquet(path)
        return pd.DataFrame(columns=columns)

    def save(self) -> None:
        self.term_df.to_parquet(self.term_registry_path, index=False)
        self.error_df.to_parquet(self.error_registry_path, index=False)
        self.repair_df.to_parquet(self.repair_registry_path, index=False)

    def add_term_record(
        self,
        field_name: str,
        raw_term: str,
        normalized_term: str,
        mapped_term: str,
        source_type: str,
        run_version: str,
        confidence: str = "",
        notes: str = "",
    ) -> None:
        row = MemoryTermRecord(
            field_name=field_name,
            raw_term=raw_term,
            normalized_term=normalized_term,
            mapped_term=mapped_term,
            source_type=source_type,
            run_version=run_version,
            confidence=confidence,
            notes=notes,
        )
        self.term_df = pd.concat([self.term_df, pd.DataFrame([asdict(row)])], ignore_index=True)

    def add_error(
        self,
        run_version: str,
        module: str,
        error_type: str,
        raw_input: str,
        resolution: str,
        notes: str = "",
    ) -> None:
        row = {
            "run_version": run_version,
            "module": module,
            "error_type": error_type,
            "raw_input": raw_input,
            "resolution": resolution,
            "notes": notes,
        }
        self.error_df = pd.concat([self.error_df, pd.DataFrame([row])], ignore_index=True)

    def add_repair(
        self,
        run_version: str,
        module: str,
        pattern: str,
        repair_action: str,
        success: bool,
        notes: str = "",
    ) -> None:
        row = {
            "run_version": run_version,
            "module": module,
            "pattern": pattern,
            "repair_action": repair_action,
            "success": success,
            "notes": notes,
        }
        self.repair_df = pd.concat([self.repair_df, pd.DataFrame([row])], ignore_index=True)

    def get_prior_term_mapping(self, field_name: str, normalized_term: str) -> Optional[str]:
        sub = self.term_df[
            (self.term_df["field_name"] == field_name) &
            (self.term_df["normalized_term"] == normalized_term)
        ]
        if sub.empty:
            return None
        # latest match
        return str(sub.iloc[-1]["mapped_term"])