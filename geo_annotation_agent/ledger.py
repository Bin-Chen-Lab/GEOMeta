from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class ChunkLedgerRow:
    run_version: str
    stage: str
    input_row_index: int
    gse_id: str
    expected_gsm_count: int
    extracted_gsm_count: int
    emitted_row_count: int
    status: str
    reason: str = ""
    recovered: bool = False
    used_placeholder_rows: bool = False
    chunk_id: str = ""


@dataclass
class RunSummary:
    run_version: str
    stage: str
    expected_total_rows: int
    emitted_total_rows: int
    missing_total_rows: int
    recovered_total_rows: int
    unresolved_total_rows: int
    status: str
    notes: str = ""


class LedgerV2:
    def __init__(self, ledger_dir: Path, run_version: str):
        self.ledger_dir = Path(ledger_dir)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self.run_version = run_version
        self._rows: List[ChunkLedgerRow] = []

    def add_chunk_row(
        self,
        stage: str,
        input_row_index: int,
        gse_id: str,
        expected_gsm_count: int,
        extracted_gsm_count: int,
        emitted_row_count: int,
        status: str,
        reason: str = "",
        recovered: bool = False,
        used_placeholder_rows: bool = False,
        chunk_id: str = "",
    ) -> None:
        self._rows.append(
            ChunkLedgerRow(
                run_version=self.run_version,
                stage=stage,
                input_row_index=input_row_index,
                gse_id=gse_id,
                expected_gsm_count=expected_gsm_count,
                extracted_gsm_count=extracted_gsm_count,
                emitted_row_count=emitted_row_count,
                status=status,
                reason=reason,
                recovered=recovered,
                used_placeholder_rows=used_placeholder_rows,
                chunk_id=chunk_id,
            )
        )

    def to_dataframe(self) -> pd.DataFrame:
        if not self._rows:
            return pd.DataFrame(
                columns=[
                    "run_version", "stage", "input_row_index", "gse_id",
                    "expected_gsm_count", "extracted_gsm_count", "emitted_row_count",
                    "status", "reason", "recovered", "used_placeholder_rows", "chunk_id"
                ]
            )
        return pd.DataFrame([asdict(r) for r in self._rows])

    def save_chunk_ledger(self, filename: Optional[str] = None) -> Path:
        if filename is None:
            filename = f"{self.run_version}_chunk_ledger.csv"
        out = self.ledger_dir / filename
        self.to_dataframe().to_csv(out, index=False)
        return out

    def summarize(self, stage: str, expected_total_rows: int) -> RunSummary:
        df = self.to_dataframe()
        if df.empty:
            emitted_total_rows = 0
            recovered_total_rows = 0
            unresolved_total_rows = expected_total_rows
        else:
            emitted_total_rows = int(df["emitted_row_count"].sum())
            recovered_total_rows = int(df.loc[df["recovered"] == True, "emitted_row_count"].sum())
            unresolved_total_rows = int(
                df.loc[df["status"].isin(["failed", "unresolved"]), "expected_gsm_count"].sum()
            )

        missing_total_rows = max(expected_total_rows - emitted_total_rows, 0)
        status = "complete" if missing_total_rows == 0 else "incomplete"

        return RunSummary(
            run_version=self.run_version,
            stage=stage,
            expected_total_rows=expected_total_rows,
            emitted_total_rows=emitted_total_rows,
            missing_total_rows=missing_total_rows,
            recovered_total_rows=recovered_total_rows,
            unresolved_total_rows=unresolved_total_rows,
            status=status,
            notes="",
        )

    def save_summary(self, summary: RunSummary, filename: Optional[str] = None) -> Path:
        if filename is None:
            filename = f"{self.run_version}_{summary.stage}_summary.json"
        out = self.ledger_dir / filename
        out.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
        return out