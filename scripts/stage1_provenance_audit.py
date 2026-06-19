#!/usr/bin/env python3
"""
GEOMeta Stage 1 provenance workbook builder.

This module consolidates the Stage 1 provenance layers produced by the
fully automated Mode A pipeline:

- Stage1_Raw
- Stage1_Raw_With_Info
- Stage1_QA1_Corrected
- Stage1_QA2_Report / Issues
- Stage1_QA3_Corrected
- Stage1_Final_For_Stage2
- QA1/QA2/QA3 reports and applied-change logs

The workbook is an audit artifact. It should not replace the individual
stage output files, parquet files, or review queues. For very large runs,
Excel sheet row limits may prevent writing every full layer into a single
workbook; in that case the function writes the manifest and change tables
and points to the complete external files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import pandas as pd

from geo_annotation_agent.excel_safe import add_long_text_part_columns_for_excel


EXCEL_MAX_ROWS = 1_048_576
EXCEL_MAX_SHEET_NAME = 31
DEFAULT_STAGE1_ID_COLS = ("GSE_ID", "GSM_ID")

# Canonical Stage 1 annotation fields. Keeping this local avoids an import cycle
# with stage1_annotate.py when this file is used from scripts/run_pipeline.py.
STAGE1_ANNOTATION_FIELDS = [
    "Seq_Type",
    "Organism",
    "Strain",
    "Genotype",
    "RNA_Library",
    "RNA_Source",
    "Tissue",
    "Experimental_Setting",
    "Model_Type",
    "Disease",
    "GSE_Pert",
    "GSM_Pert",
    "Pert",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
    "SampleType",
    "Specimen_Type",
    "Race",
    "Ethnicity",
    "Age",
    "Sex",
    "Timepoint",
    "Outcome",
]

LONG_TEXT_COLUMNS = ("GSE_Info", "GSM_Info")


def _clean_text(x: Any) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, float) and x != x:
            return ""
    except Exception:
        pass
    return str(x).strip()


def _sheet_name(name: str, used: set[str]) -> str:
    base = str(name).strip()[:EXCEL_MAX_SHEET_NAME] or "Sheet"
    out = base
    i = 1
    while out in used:
        suffix = f"_{i}"
        out = base[: EXCEL_MAX_SHEET_NAME - len(suffix)] + suffix
        i += 1
    used.add(out)
    return out


def _read_table_if_exists(path: Any, sheet_name: str | int = 0) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    try:
        suffix = p.suffix.lower()
        if suffix in {".xlsx", ".xlsm", ".xls"}:
            return pd.read_excel(p, sheet_name=sheet_name, dtype=str, keep_default_na=False)
        if suffix == ".csv":
            return pd.read_csv(p, dtype=str, keep_default_na=False)
        if suffix in {".tsv", ".txt"}:
            return pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
        if suffix == ".parquet":
            return pd.read_parquet(p)
    except Exception as e:
        return pd.DataFrame({"Read_Error": [repr(e)], "Path": [str(p)]})
    return pd.DataFrame()


def _excel_safe(df: pd.DataFrame, part_limit: int) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    has_long = any(c in out.columns for c in LONG_TEXT_COLUMNS)
    if has_long:
        out = add_long_text_part_columns_for_excel(
            out,
            long_text_columns=LONG_TEXT_COLUMNS,
            part_limit=part_limit,
            keep_preview_column=True,
        )
    return out


def _write_sheet(
    writer: pd.ExcelWriter,
    sheet_name: str,
    df: pd.DataFrame,
    *,
    used_sheet_names: set[str],
    part_limit: int,
    max_rows_per_sheet: int,
    manifest_rows: list[dict[str, Any]],
    source_path: str = "",
    allow_truncate: bool = False,
) -> None:
    safe_name = _sheet_name(sheet_name, used_sheet_names)
    df = pd.DataFrame() if df is None else df.copy()
    n_rows = int(df.shape[0])
    n_cols = int(df.shape[1])

    status = "written"
    written_rows = n_rows

    if n_rows > max_rows_per_sheet:
        if allow_truncate:
            df = df.head(max_rows_per_sheet).copy()
            status = "truncated_in_workbook"
            written_rows = int(df.shape[0])
        else:
            status = "not_written_too_many_rows"
            written_rows = 1
            df = pd.DataFrame(
                [
                    {
                        "Sheet": safe_name,
                        "Status": status,
                        "Rows": n_rows,
                        "Columns": n_cols,
                        "Reason": (
                            "This table exceeds the configured Excel row limit for the "
                            "provenance workbook. Use the complete external file listed "
                            "in the Manifest sheet."
                        ),
                        "Source_Path": source_path,
                    }
                ]
            )

    df = _excel_safe(df, part_limit=part_limit)
    df.to_excel(writer, sheet_name=safe_name, index=False)

    manifest_rows.append(
        {
            "Sheet": safe_name,
            "Original_Label": sheet_name,
            "Rows": n_rows,
            "Columns": n_cols,
            "Written_Rows": written_rows,
            "Status": status,
            "Source_Path": source_path,
        }
    )


def _normalize_for_compare(df: pd.DataFrame, gse_col: str, gsm_col: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=[gse_col, gsm_col])
    out = df.copy()
    for c in [gse_col, gsm_col]:
        if c not in out.columns:
            out[c] = ""
        out[c] = out[c].map(_clean_text)
    out = out.drop_duplicates(subset=[gse_col, gsm_col], keep="first")
    return out


def build_stage1_cell_change_trace(
    *,
    stage1_raw: pd.DataFrame,
    stage1_qa1_corrected: pd.DataFrame,
    stage1_qa3_corrected: pd.DataFrame,
    stage1_final_for_stage2: pd.DataFrame,
    gse_col: str = "GSE_ID",
    gsm_col: str = "GSM_ID",
    fields: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """Create a cell-level change trace across Stage 1 QA layers."""
    fields = list(fields or STAGE1_ANNOTATION_FIELDS)

    raw = _normalize_for_compare(stage1_raw, gse_col, gsm_col)
    qa1 = _normalize_for_compare(stage1_qa1_corrected, gse_col, gsm_col)
    qa3 = _normalize_for_compare(stage1_qa3_corrected, gse_col, gsm_col)
    final = _normalize_for_compare(stage1_final_for_stage2, gse_col, gsm_col)

    keys = pd.concat(
        [
            raw[[gse_col, gsm_col]],
            qa1[[gse_col, gsm_col]],
            qa3[[gse_col, gsm_col]],
            final[[gse_col, gsm_col]],
        ],
        ignore_index=True,
    ).drop_duplicates()

    def prep_layer(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
        keep_cols = [gse_col, gsm_col] + [c for c in fields if c in df.columns]
        tmp = df[keep_cols].copy() if keep_cols else pd.DataFrame(columns=[gse_col, gsm_col])
        rename = {c: f"{prefix}_{c}" for c in tmp.columns if c not in {gse_col, gsm_col}}
        return tmp.rename(columns=rename)

    merged = keys.merge(prep_layer(raw, "Raw"), on=[gse_col, gsm_col], how="left")
    merged = merged.merge(prep_layer(qa1, "QA1"), on=[gse_col, gsm_col], how="left")
    merged = merged.merge(prep_layer(qa3, "QA3"), on=[gse_col, gsm_col], how="left")
    merged = merged.merge(prep_layer(final, "Final"), on=[gse_col, gsm_col], how="left")

    rows: list[dict[str, Any]] = []
    for _, r in merged.iterrows():
        for field in fields:
            raw_v = _clean_text(r.get(f"Raw_{field}", ""))
            qa1_v = _clean_text(r.get(f"QA1_{field}", raw_v))
            qa3_v = _clean_text(r.get(f"QA3_{field}", qa1_v))
            final_v = _clean_text(r.get(f"Final_{field}", qa3_v))

            changed_qa1 = qa1_v != raw_v
            changed_qa3 = qa3_v != qa1_v
            changed_final = final_v != raw_v

            if not (changed_qa1 or changed_qa3 or changed_final):
                continue

            if changed_qa3:
                source = "Stage1_QA3_Evidence_Verifier"
            elif changed_qa1:
                source = "Stage1_QA1_Rule_Based_Fill"
            else:
                source = "Stage1_Final_For_Stage2"

            rows.append(
                {
                    "GSE_ID": _clean_text(r.get(gse_col, "")),
                    "GSM_ID": _clean_text(r.get(gsm_col, "")),
                    "Field": field,
                    "Raw_Value": raw_v,
                    "QA1_Value": qa1_v,
                    "QA3_Value": qa3_v,
                    "Final_Value": final_v,
                    "Changed_QA1_From_Raw": bool(changed_qa1),
                    "Changed_QA3_From_QA1": bool(changed_qa3),
                    "Final_Changed_From_Raw": bool(changed_final),
                    "Final_Source_Inferred": source,
                }
            )

    return pd.DataFrame(rows)


def summarize_stage1_changes(change_trace_df: pd.DataFrame) -> pd.DataFrame:
    if change_trace_df is None or change_trace_df.empty:
        return pd.DataFrame(
            columns=[
                "Field",
                "Changed_QA1_From_Raw",
                "Changed_QA3_From_QA1",
                "Final_Changed_From_Raw",
                "Unique_GSMs_Changed_Final",
            ]
        )

    grouped = (
        change_trace_df.groupby("Field", dropna=False)
        .agg(
            Changed_QA1_From_Raw=("Changed_QA1_From_Raw", "sum"),
            Changed_QA3_From_QA1=("Changed_QA3_From_QA1", "sum"),
            Final_Changed_From_Raw=("Final_Changed_From_Raw", "sum"),
            Unique_GSMs_Changed_Final=("GSM_ID", lambda s: int(s.nunique())),
        )
        .reset_index()
        .sort_values(["Final_Changed_From_Raw", "Field"], ascending=[False, True])
    )
    return grouped


def write_stage1_provenance_workbook(
    *,
    output_path: str | Path,
    run_version: str,
    stage1_raw: pd.DataFrame,
    stage1_raw_with_info: pd.DataFrame,
    stage1_qa1_corrected: pd.DataFrame,
    stage1_qa3_corrected: pd.DataFrame,
    stage1_final_for_stage2: pd.DataFrame,
    qa1_summary_df: pd.DataFrame | None = None,
    qa1_candidates_df: pd.DataFrame | None = None,
    qa1_review_df: pd.DataFrame | None = None,
    qa2_issues_df: pd.DataFrame | None = None,
    qa3_outputs: Mapping[str, Any] | None = None,
    file_manifest: Mapping[str, Any] | None = None,
    gse_col: str = "GSE_ID",
    gsm_col: str = "GSM_ID",
    part_limit: int = 32000,
    max_rows_per_sheet: int = EXCEL_MAX_ROWS - 1,
) -> Path:
    """Write a consolidated Stage 1 provenance workbook."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    qa3_outputs = dict(qa3_outputs or {})
    file_manifest = dict(file_manifest or {})

    qa3_tasks_df = _read_table_if_exists(qa3_outputs.get("tasks"))
    qa3_recommendations_df = _read_table_if_exists(qa3_outputs.get("recommendations"))
    qa3_applied_df = _read_table_if_exists(qa3_outputs.get("applied_changes"))
    qa3_human_df = _read_table_if_exists(qa3_outputs.get("human_review"))

    change_trace_df = build_stage1_cell_change_trace(
        stage1_raw=stage1_raw,
        stage1_qa1_corrected=stage1_qa1_corrected,
        stage1_qa3_corrected=stage1_qa3_corrected,
        stage1_final_for_stage2=stage1_final_for_stage2,
        gse_col=gse_col,
        gsm_col=gsm_col,
    )
    change_summary_df = summarize_stage1_changes(change_trace_df)

    layer_counts = pd.DataFrame(
        [
            {
                "Layer": "Stage1_Raw",
                "Rows": int(stage1_raw.shape[0]),
                "Unique_GSM": int(stage1_raw[gsm_col].astype(str).nunique()) if gsm_col in stage1_raw.columns else 0,
            },
            {
                "Layer": "Stage1_Raw_With_Info",
                "Rows": int(stage1_raw_with_info.shape[0]),
                "Unique_GSM": int(stage1_raw_with_info[gsm_col].astype(str).nunique()) if gsm_col in stage1_raw_with_info.columns else 0,
            },
            {
                "Layer": "Stage1_QA1_Corrected",
                "Rows": int(stage1_qa1_corrected.shape[0]),
                "Unique_GSM": int(stage1_qa1_corrected[gsm_col].astype(str).nunique()) if gsm_col in stage1_qa1_corrected.columns else 0,
            },
            {
                "Layer": "Stage1_QA3_Corrected",
                "Rows": int(stage1_qa3_corrected.shape[0]),
                "Unique_GSM": int(stage1_qa3_corrected[gsm_col].astype(str).nunique()) if gsm_col in stage1_qa3_corrected.columns else 0,
            },
            {
                "Layer": "Stage1_Final_For_Stage2",
                "Rows": int(stage1_final_for_stage2.shape[0]),
                "Unique_GSM": int(stage1_final_for_stage2[gsm_col].astype(str).nunique()) if gsm_col in stage1_final_for_stage2.columns else 0,
            },
        ]
    )

    policy_df = pd.DataFrame(
        [
            {
                "Policy": "Mode A automated release",
                "Rule": "Human-review cases do not block the pipeline. They are saved as review queues and carried forward with flags.",
            },
            {
                "Policy": "QA1",
                "Rule": "Only high-confidence missing-cell corrections are auto-applied.",
            },
            {
                "Policy": "QA2",
                "Rule": "Cross-agent validation produces issues/review signals only; it does not directly overwrite Stage 1 values.",
            },
            {
                "Policy": "QA3",
                "Rule": "Only accepted high-confidence evidence-supported missing-cell rescue corrections are auto-applied by default.",
            },
            {
                "Policy": "Final Stage1 for Stage2",
                "Rule": "Stage1_Final_For_Stage2 is the only Stage 1 layer passed to Stage 2.",
            },
        ]
    )

    manifest_rows: list[dict[str, Any]] = []
    used_sheet_names: set[str] = set()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        _write_sheet(
            writer,
            "README",
            policy_df,
            used_sheet_names=used_sheet_names,
            part_limit=part_limit,
            max_rows_per_sheet=max_rows_per_sheet,
            manifest_rows=manifest_rows,
        )
        _write_sheet(
            writer,
            "Layer_Counts",
            layer_counts,
            used_sheet_names=used_sheet_names,
            part_limit=part_limit,
            max_rows_per_sheet=max_rows_per_sheet,
            manifest_rows=manifest_rows,
        )
        _write_sheet(
            writer,
            "Change_Summary",
            change_summary_df,
            used_sheet_names=used_sheet_names,
            part_limit=part_limit,
            max_rows_per_sheet=max_rows_per_sheet,
            manifest_rows=manifest_rows,
        )
        _write_sheet(
            writer,
            "Cell_Change_Trace",
            change_trace_df,
            used_sheet_names=used_sheet_names,
            part_limit=part_limit,
            max_rows_per_sheet=max_rows_per_sheet,
            manifest_rows=manifest_rows,
            allow_truncate=False,
        )

        # Full layer sheets. These are included when they fit the configured Excel row limit.
        _write_sheet(writer, "Stage1_Raw", stage1_raw, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(file_manifest.get("stage1_raw", "")))
        _write_sheet(writer, "Stage1_Raw_With_Info", stage1_raw_with_info, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(file_manifest.get("stage1_raw_with_info", "")))
        _write_sheet(writer, "Stage1_QA1_Corrected", stage1_qa1_corrected, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(file_manifest.get("stage1_qa1_corrected", "")))
        _write_sheet(writer, "Stage1_QA3_Corrected", stage1_qa3_corrected, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(file_manifest.get("stage1_qa3_corrected", "")))
        _write_sheet(writer, "Stage1_Final_For_Stage2", stage1_final_for_stage2, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(file_manifest.get("stage1_final_for_stage2", "")))

        # QA report sheets.
        _write_sheet(writer, "QA1_Field_Summary", qa1_summary_df if qa1_summary_df is not None else pd.DataFrame(), used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(file_manifest.get("stage1_qa1_report", "")))
        _write_sheet(writer, "QA1_Cell_Candidates", qa1_candidates_df if qa1_candidates_df is not None else pd.DataFrame(), used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(file_manifest.get("stage1_qa1_candidates", "")))
        _write_sheet(writer, "QA1_Review_Queue", qa1_review_df if qa1_review_df is not None else pd.DataFrame(), used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(file_manifest.get("stage1_qa1_report", "")))
        _write_sheet(writer, "QA2_Issues", qa2_issues_df if qa2_issues_df is not None else pd.DataFrame(), used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(file_manifest.get("stage1_qa2_report", "")))
        _write_sheet(writer, "QA3_Tasks", qa3_tasks_df, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(qa3_outputs.get("tasks", "")))
        _write_sheet(writer, "QA3_Recommendations", qa3_recommendations_df, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(qa3_outputs.get("recommendations", "")))
        _write_sheet(writer, "QA3_Applied_Changes", qa3_applied_df, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(qa3_outputs.get("applied_changes", "")))
        _write_sheet(writer, "QA3_Human_Review", qa3_human_df, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=manifest_rows, source_path=str(qa3_outputs.get("human_review", "")))

        # Write manifest last, now that every sheet has recorded its status.
        manifest_df = pd.DataFrame(manifest_rows)
        if file_manifest:
            files_df = pd.DataFrame([{"Artifact": k, "Path": str(v)} for k, v in file_manifest.items()])
        else:
            files_df = pd.DataFrame(columns=["Artifact", "Path"])
        _write_sheet(writer, "Workbook_Manifest", manifest_df, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=[])
        _write_sheet(writer, "File_Manifest", files_df, used_sheet_names=used_sheet_names, part_limit=part_limit, max_rows_per_sheet=max_rows_per_sheet, manifest_rows=[])

    # Save a JSON sidecar for machine-readable provenance pointers.
    sidecar = output_path.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "run_version": run_version,
                "provenance_workbook": str(output_path),
                "file_manifest": {k: str(v) for k, v in file_manifest.items()},
                "qa3_outputs": {k: str(v) for k, v in qa3_outputs.items()},
                "change_trace_rows": int(change_trace_df.shape[0]),
                "change_summary_rows": int(change_summary_df.shape[0]),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return output_path
